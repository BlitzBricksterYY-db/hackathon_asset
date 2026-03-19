"""
Database connection management for Lakebase PostgreSQL.
Uses Databricks SDK for credential generation.
"""
import os
from sqlmodel import SQLModel, create_engine, Session
from collections.abc import Generator
from contextlib import contextmanager
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Endpoint
from sqlalchemy.engine import Engine

from .config import conf
from .logger import logger


def _resolve_project_resource_name(client: WorkspaceClient) -> str:
    """Resolve project display name to its full resource name (projects/<uuid>)."""
    display_name = conf.lakebase_project
    for project in client.postgres.list_projects():
        project_display = (
            project.status.display_name if project.status else None
        )
        if project_display and project_display == display_name:
            if not project.name:
                raise ValueError(
                    f"Project with display_name '{display_name}' has no resource name"
                )
            logger.info(f"Resolved Lakebase project '{display_name}' -> {project.name}")
            return project.name
    raise ValueError(
        f"Lakebase project with display_name '{display_name}' not found in this workspace"
    )


def _resolve_branch_resource_name(client: WorkspaceClient, project_name: str) -> str:
    """Resolve the branch resource name for the given project.

    If ``conf.lakebase_branch`` is set, match by UID or display name.
    Otherwise fall back to the default branch.
    """
    branches = list(client.postgres.list_branches(parent=project_name))
    if not branches:
        raise ValueError(f"No branches found for project {project_name}")

    wanted = conf.lakebase_branch
    if wanted:
        for branch in branches:
            if branch.uid == wanted or (branch.name and branch.name.endswith(f"/{wanted}")):
                if not branch.name:
                    raise ValueError(f"Matched branch '{wanted}' has no resource name")
                logger.info(f"Resolved Lakebase branch '{wanted}' -> {branch.name}")
                return branch.name

        available = [b.uid for b in branches if b.uid]
        raise ValueError(
            f"Branch '{wanted}' not found for {project_name}. Available: {available}"
        )

    # Fall back to default branch
    for branch in branches:
        if branch.status and branch.status.default:
            if not branch.name:
                raise ValueError("Default branch has no resource name")
            logger.info(f"Using default Lakebase branch -> {branch.name}")
            return branch.name

    # Last resort: first branch
    first = branches[0]
    if not first.name:
        raise ValueError("First branch has no resource name")
    logger.info(f"No default branch flagged; using first branch -> {first.name}")
    return first.name


def _resolve_lakebase_endpoint(client: WorkspaceClient) -> tuple[str, str]:
    """Resolve endpoint name and host for configured Lakebase project/branch."""
    project_name = _resolve_project_resource_name(client)
    branch_name = _resolve_branch_resource_name(client, project_name)
    endpoints = list(client.postgres.list_endpoints(parent=branch_name))
    if not endpoints:
        raise ValueError(f"No Lakebase endpoints found for {branch_name}")

    def _endpoint_host(endpoint: Endpoint) -> str | None:
        if endpoint.status and endpoint.status.hosts:
            return endpoint.status.hosts.host
        return None

    required_host = conf.lakebase_endpoint_host
    if required_host:
        for endpoint in endpoints:
            host = _endpoint_host(endpoint)
            if host and host.lower() == required_host.lower():
                if not endpoint.name:
                    raise ValueError(
                        f"Resolved endpoint host {host} has no resource name in SDK response"
                    )
                return endpoint.name, host

        available_hosts = sorted({h for h in (_endpoint_host(e) for e in endpoints) if h})
        raise ValueError(f"Could not find configured Lakebase endpoint host {required_host} under {branch_name}. Available hosts: {available_hosts}")

    # Fallback: select first endpoint with an available host.
    for endpoint in endpoints:
        host = _endpoint_host(endpoint)
        if host and endpoint.name:
            return endpoint.name, host

    raise ValueError(f"No endpoint with a resolved host found for {branch_name}")


def get_databricks_postgres_credential() -> dict[str, str] | None:
    """
    Get PostgreSQL credentials using Databricks SDK.
    Returns dict with host, user, password, database if successful.
    """
    try:
        client = WorkspaceClient()

        endpoint_name, host = _resolve_lakebase_endpoint(client)

        # In Databricks Apps, the DB role maps to app OAuth client id.
        # Prefer DATABRICKS_CLIENT_ID when present, otherwise fall back.
        username = os.environ.get("DATABRICKS_CLIENT_ID")
        if not username:
            current_user = client.current_user.me()
            username = current_user.user_name
        if not username:
            raise ValueError("Current user is missing user_name; cannot build Postgres username")

        # Generate OAuth credential
        cred = client.postgres.generate_database_credential(endpoint=endpoint_name)

        if not cred.token:
            logger.warning("No token in database credential response")
            return None

        logger.info(f"Generated Lakebase credential for {username} @ {host}")

        return {
            "host": host,
            "port": "5432",
            "database": conf.lakebase_database,
            "user": username,
            "password": cred.token,
            "sslmode": conf.lakebase_sslmode,
            "schema": conf.lakebase_schema,
        }

    except Exception as e:
        logger.warning(
            f"Could not get Lakebase credentials via SDK. This workspace may not support SDK-based credential generation yet: {e}"
        )
        return None


def get_postgres_url() -> str:
    """Get PostgreSQL connection URL using SDK credentials."""
    creds = get_databricks_postgres_credential()
    
    if not creds:
        raise ValueError(
            "Could not generate Lakebase PostgreSQL credentials. Ensure you are authenticated to a workspace with Lakebase enabled."
        )
    
    from urllib.parse import quote_plus
    password = quote_plus(creds["password"]) if creds["password"] else ""
    schema = creds.get("schema", "public")
    
    return (
        f"postgresql://{creds['user']}:{password}"
        f"@{creds['host']}:{creds['port']}/{creds['database']}"
        f"?sslmode={creds['sslmode']}&options=-csearch_path%3D{schema}"
    )


# Lazy engine initialization
_engine: Engine | None = None


def get_engine() -> Engine:
    """Get or create the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        url = get_postgres_url()
        logger.info("Creating PostgreSQL engine for Lakebase")
        _engine = create_engine(
            url,
            echo=conf.debug,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10
        )
    return _engine


def reset_engine():
    """Reset the engine (useful when token expires)."""
    global _engine
    if _engine:
        _engine.dispose()
    _engine = None


def init_db():
    """Initialize database tables."""
    from . import db_models  # Import to register SQLModel metadata tables.

    _ = db_models

    engine = get_engine()
    logger.info("Creating database tables if not exist")
    SQLModel.metadata.create_all(engine)

    # Idempotent migration: add owner_user column if missing on pre-existing tables
    from sqlalchemy import text
    with engine.connect() as conn:
        schema = conf.lakebase_schema
        for table in ("optimization_configs", "optimization_runs"):
            try:
                conn.execute(text(
                    f"ALTER TABLE {schema}.{table} "
                    f"ADD COLUMN IF NOT EXISTS owner_user TEXT"
                ))
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS ix_{table}_owner_user "
                    f"ON {schema}.{table} (owner_user)"
                ))
            except Exception as e:
                logger.warning(f"Migration for {table}.owner_user skipped: {e}")
        conn.commit()

    logger.info("Database initialization complete")


def get_session() -> Generator[Session, None, None]:
    """Get a database session (dependency injection for FastAPI)."""
    engine = get_engine()
    with Session(engine) as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    engine = get_engine()
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
