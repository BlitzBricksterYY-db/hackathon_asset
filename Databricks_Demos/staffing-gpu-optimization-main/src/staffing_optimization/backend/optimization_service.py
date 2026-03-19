"""
Service for managing workforce optimization configurations and runs.

Data Model:
- Config: Optimization configuration (1:1 with Databricks job)
- Run: Individual optimization run (many:1 with config)
- Results: Stored in unified Unity Catalog table with run_id column
"""
from sqlmodel import Session, select, delete
from typing import Optional
from datetime import datetime

from .db_models import OptimizationConfigDB, OptimizationRunDB
from .models import (
    OptimizationConfig,
    OptimizationConfigCreate,
    OptimizationConfigOut,
    OptimizationRunCreate,
    OptimizationRunOut,
    OptimizationResultOut,
    AssignmentResult,
    RunStatus,
    RunResultsSummaryOut,
    PaginationMeta,
    PagedAssignmentsOut,
    ShiftAggregateOut,
    PagedShiftAggregatesOut,
    WorkerAggregateOut,
    PagedWorkerAggregatesOut,
    GraphSubsetOut,
    GRAPH_ELEMENT_THRESHOLD,
    VALID_ASSIGNMENT_SORT_FIELDS,
    VALID_AGGREGATE_SORT_FIELDS,
)
from .database import session_scope
from .databricks_service import get_databricks_service
from .config import conf
from .logger import logger


class OptimizationService:
    """Service for managing optimization configurations and runs."""
    
    # ============== Configuration Operations ==============
    
    def create_config(
        self, config: OptimizationConfigCreate, *, owner_user: Optional[str] = None
    ) -> OptimizationConfigOut:
        """Create a new optimization configuration."""
        with session_scope() as session:
            db_config = OptimizationConfigDB(
                name=config.name,
                description=config.description,
                source_catalog=config.source_catalog,
                source_schema=config.source_schema,
                workers_table=config.workers_table,
                shifts_table=config.shifts_table,
                availability_table=config.availability_table,
                worker_name_col=config.worker_name_col,
                worker_pay_col=config.worker_pay_col,
                shift_name_col=config.shift_name_col,
                shift_required_col=config.shift_required_col,
                availability_worker_col=config.availability_worker_col,
                availability_shift_col=config.availability_shift_col,
                max_shifts_per_worker=config.max_shifts_per_worker,
                time_limit_seconds=config.time_limit_seconds,
                target_catalog=config.target_catalog,
                target_schema=config.target_schema,
                results_table=config.results_table,
                owner_user=owner_user,
            )
            session.add(db_config)
            session.commit()
            session.refresh(db_config)
            
            return self._config_to_out(db_config)
    
    def get_config(self, config_id: str) -> Optional[OptimizationConfigOut]:
        """Get a configuration by ID."""
        with session_scope() as session:
            db_config = session.get(OptimizationConfigDB, config_id)
            if db_config:
                return self._config_to_out(db_config)
            return None
    
    def list_configs(self, *, owner_user: Optional[str] = None) -> list[OptimizationConfigOut]:
        """List configurations, scoped to *owner_user* when provided.

        Legacy rows (``owner_user IS NULL``) are hidden when a user filter is active.
        """
        with session_scope() as session:
            statement = select(OptimizationConfigDB).order_by(OptimizationConfigDB.created_at.desc())
            if owner_user:
                statement = statement.where(OptimizationConfigDB.owner_user == owner_user)
            configs = session.exec(statement).all()
            return [self._config_to_out(c) for c in configs]
    
    def update_config(self, config_id: str, config: OptimizationConfigCreate) -> Optional[OptimizationConfigOut]:
        """Update an existing configuration.
        
        Note: If config has a Databricks job, we should update the job parameters too.
        """
        with session_scope() as session:
            db_config = session.get(OptimizationConfigDB, config_id)
            if not db_config:
                return None
            
            # Update fields
            db_config.name = config.name
            db_config.description = config.description
            db_config.source_catalog = config.source_catalog
            db_config.source_schema = config.source_schema
            db_config.workers_table = config.workers_table
            db_config.shifts_table = config.shifts_table
            db_config.availability_table = config.availability_table
            db_config.worker_name_col = config.worker_name_col
            db_config.worker_pay_col = config.worker_pay_col
            db_config.shift_name_col = config.shift_name_col
            db_config.shift_required_col = config.shift_required_col
            db_config.availability_worker_col = config.availability_worker_col
            db_config.availability_shift_col = config.availability_shift_col
            db_config.max_shifts_per_worker = config.max_shifts_per_worker
            db_config.time_limit_seconds = config.time_limit_seconds
            db_config.target_catalog = config.target_catalog
            db_config.target_schema = config.target_schema
            db_config.results_table = config.results_table
            db_config.updated_at = datetime.utcnow()
            
            # If config has a Databricks job, update it
            if db_config.databricks_job_id:
                try:
                    db_service = get_databricks_service()
                    config_dict = self._build_config_dict(db_config)
                    db_service.update_optimization_job(
                        databricks_job_id=db_config.databricks_job_id,
                        config_dict=config_dict,
                        job_name=db_config.name
                    )
                except Exception as e:
                    logger.warning(f"Failed to update Databricks job: {e}")
            
            session.add(db_config)
            session.commit()
            session.refresh(db_config)
            
            return self._config_to_out(db_config)
    
    def delete_config(self, config_id: str) -> bool:
        """Delete a configuration and its associated data.

        Note: Runs reference configs via a foreign key, so we delete all child
        runs first to avoid FK violations in Lakebase/Postgres.
        """
        with session_scope() as session:
            db_config = session.get(OptimizationConfigDB, config_id)
            if not db_config:
                return False
            
            # Delete associated Databricks job if it exists
            if db_config.databricks_job_id:
                try:
                    db_service = get_databricks_service()
                    db_service.delete_job(db_config.databricks_job_id)
                except Exception as e:
                    logger.warning(f"Failed to delete Databricks job: {e}")

            # Delete child runs first with an explicit SQL delete so the DB sees
            # child rows removed before we delete the parent config row.
            session.exec(
                delete(OptimizationRunDB).where(OptimizationRunDB.config_id == config_id)
            )
            session.flush()

            session.delete(db_config)
            session.commit()
            return True
    
    # ============== Run Operations ==============
    
    def create_run(
        self, run_create: OptimizationRunCreate, *, owner_user: Optional[str] = None
    ) -> OptimizationRunOut:
        """Create and submit a new optimization run.

        Uses the shared bundle-deployed Databricks job (configured via
        STAFFING_OPTIMIZATION_DATABRICKS_JOB_ID) when available.  Falls back
        to creating a per-config job if the env var is not set.
        """
        # Get the config and extract all needed values while in session
        # (db_config is detached after block exits; access all attributes inside)
        with session_scope() as session:
            db_config = session.get(OptimizationConfigDB, run_create.config_id)
            if not db_config:
                raise ValueError(f"Configuration {run_create.config_id} not found")
            
            config_dict = self._build_config_dict(db_config)
            results_table = self._get_results_table(db_config)
            config_id = db_config.id
            config_name = db_config.name
            config_databricks_job_id = db_config.databricks_job_id
            
            # Create run record
            db_run = OptimizationRunDB(
                config_id=run_create.config_id,
                run_name=run_create.run_name,
                status=RunStatus.PENDING.value,
                owner_user=owner_user,
            )
            session.add(db_run)
            session.commit()
            session.refresh(db_run)
            
            run_id = db_run.id
        
        db_service = get_databricks_service()

        # Use shared bundle job (injected via STAFFING_OPTIMIZATION_DATABRICKS_JOB_ID)
        databricks_job_id = conf.databricks_job_id or config_databricks_job_id
        if not databricks_job_id:
            raise ValueError(
                "STAFFING_OPTIMIZATION_DATABRICKS_JOB_ID is not set. "
                "Deploy the bundle to inject the shared job ID, or run locally with the env var set."
            )

        try:
            # Submit a run on the job, passing all params at run time
            databricks_run_id = db_service.run_optimization_job(
                databricks_job_id=databricks_job_id,
                run_id=run_id,
                results_table=results_table,
                config_dict=config_dict,
                owner_user=owner_user,
            )
            
            # Update run with databricks_run_id and status
            with session_scope() as session:
                db_run = session.get(OptimizationRunDB, run_id)
                db_run.databricks_run_id = databricks_run_id
                db_run.status = RunStatus.RUNNING.value
                db_run.updated_at = datetime.utcnow()
                session.add(db_run)
                session.commit()
                session.refresh(db_run)
                
                return self._run_to_out(db_run)
                
        except Exception as e:
            # Mark run as failed
            logger.error(f"Failed to create/run optimization: {e}")
            with session_scope() as session:
                db_run = session.get(OptimizationRunDB, run_id)
                db_run.status = RunStatus.FAILED.value
                db_run.error_message = str(e)
                db_run.updated_at = datetime.utcnow()
                session.add(db_run)
                session.commit()
            raise
    
    def get_run(self, run_id: str) -> Optional[OptimizationRunOut]:
        """Get a run by ID, refreshing status from Databricks if running."""
        with session_scope() as session:
            db_run = session.get(OptimizationRunDB, run_id)
            if not db_run:
                return None
            
            # If run is active, check Databricks status
            if db_run.status in (RunStatus.RUNNING.value, RunStatus.PENDING.value) and db_run.databricks_run_id:
                self._refresh_run_status(session, db_run)
            
            return self._run_to_out(db_run)

    def refresh_run_status(self, run_id: str) -> Optional[OptimizationRunOut]:
        """Force-refresh a run status from Databricks."""
        with session_scope() as session:
            db_run = session.get(OptimizationRunDB, run_id)
            if not db_run:
                return None

            if db_run.databricks_run_id:
                self._refresh_run_status(session, db_run)
            elif db_run.status in (RunStatus.RUNNING.value, RunStatus.PENDING.value):
                # If we somehow lost the Databricks run id, fail fast so UI stops spinning.
                db_run.status = RunStatus.FAILED.value
                db_run.error_message = "Run is missing Databricks run id; cannot refresh status."
                db_run.updated_at = datetime.utcnow()
                db_run.completed_at = datetime.utcnow()
                session.add(db_run)
                session.commit()

            return self._run_to_out(db_run)
    
    def list_runs(
        self, config_id: Optional[str] = None, *, owner_user: Optional[str] = None
    ) -> list[OptimizationRunOut]:
        """List runs, optionally filtered by config and scoped to *owner_user*."""
        with session_scope() as session:
            statement = select(OptimizationRunDB).order_by(OptimizationRunDB.created_at.desc())
            if config_id:
                statement = statement.where(OptimizationRunDB.config_id == config_id)
            if owner_user:
                statement = statement.where(OptimizationRunDB.owner_user == owner_user)
            
            runs = session.exec(statement).all()
            
            # Refresh active runs (both RUNNING and PENDING)
            for db_run in runs:
                if db_run.status in (RunStatus.RUNNING.value, RunStatus.PENDING.value) and db_run.databricks_run_id:
                    self._refresh_run_status(session, db_run)
            
            return [self._run_to_out(r) for r in runs]
    
    def cancel_run(self, run_id: str) -> bool:
        """Cancel a running run."""
        with session_scope() as session:
            db_run = session.get(OptimizationRunDB, run_id)
            if not db_run or db_run.status != RunStatus.RUNNING.value:
                return False
            
            if db_run.databricks_run_id:
                try:
                    db_service = get_databricks_service()
                    db_service.cancel_run(db_run.databricks_run_id)
                except Exception as e:
                    logger.error(f"Failed to cancel Databricks run: {e}")
            
            db_run.status = RunStatus.CANCELLED.value
            db_run.updated_at = datetime.utcnow()
            session.add(db_run)
            session.commit()
            return True
    
    # ============== Results Operations ==============
    
    def get_results(self, run_id: str) -> Optional[OptimizationResultOut]:
        """Get optimization results for a run from unified Unity Catalog Delta table."""
        with session_scope() as session:
            db_run = session.get(OptimizationRunDB, run_id)
            if not db_run:
                return None
            
            # Get the config to find results table
            db_config = session.get(OptimizationConfigDB, db_run.config_id)
            
            # If run hasn't completed, return status only
            if db_run.status != RunStatus.COMPLETED.value:
                return OptimizationResultOut(
                    run_id=run_id,
                    status=RunStatus(db_run.status),
                    total_cost=db_run.total_cost,
                    solve_time_seconds=db_run.solve_time_seconds,
                    assignments=[],
                    worker_summary={},
                    shift_summary={}
                )
            
            # Read results from Delta table
            assignments = []
            results_table = self._get_results_table(db_config) if db_config else None
            db_service = get_databricks_service()
            
            if results_table:
                try:
                    # Try unified results table first (with run_id column)
                    logger.info(f"Querying unified table: {results_table} WHERE run_id = '{run_id}'")
                    results_data = db_service.execute_sql(
                        f"SELECT worker_name, shift_name, cost FROM {results_table} WHERE run_id = '{run_id}'"
                    )
                    
                    for row in results_data:
                        assignments.append(
                            AssignmentResult(
                                worker_name=row["worker_name"],
                                shift_name=row["shift_name"],
                                cost=float(row["cost"]) if row["cost"] else 0.0
                            )
                        )
                except Exception as e:
                    logger.warning(f"Unified table query failed for {results_table}: {e}")
            
            # Fallback: Try legacy table patterns
            if not assignments and db_config:
                try:
                    catalog = db_config.target_catalog or conf.default_catalog
                    schema = db_config.target_schema or conf.default_schema
                    
                    # Legacy pattern 1: per-run tables (optimization_results_{run_id})
                    legacy_patterns = [
                        f"{catalog}.{schema}.optimization_results_{run_id.replace('-', '_')}",
                        f"{catalog}.{schema}.optimization_results_{run_id}",
                    ]
                    
                    for legacy_table in legacy_patterns:
                        try:
                            logger.info(f"Trying legacy table: {legacy_table}")
                            results_data = db_service.execute_sql(
                                f"SELECT worker_name, shift_name, cost FROM {legacy_table}"
                            )
                            
                            for row in results_data:
                                assignments.append(
                                    AssignmentResult(
                                        worker_name=row["worker_name"],
                                        shift_name=row["shift_name"],
                                        cost=float(row["cost"]) if row["cost"] else 0.0
                                    )
                                )
                            
                            if assignments:
                                logger.info(f"Found {len(assignments)} assignments in legacy table {legacy_table}")
                                break
                        except Exception as e:
                            logger.debug(f"Legacy table {legacy_table} not found or empty: {e}")
                            continue
                    
                    # Legacy pattern 2: default schema with just table name
                    if not assignments:
                        default_table_patterns = [
                            f"main.default.{db_config.results_table}" if db_config.results_table else None,
                            f"{catalog}.default.results",
                        ]
                        
                        for default_table in default_table_patterns:
                            if not default_table:
                                continue
                            try:
                                logger.info(f"Trying default schema table: {default_table} with run_id filter")
                                results_data = db_service.execute_sql(
                                    f"SELECT worker_name, shift_name, cost FROM {default_table} WHERE run_id = '{run_id}'"
                                )
                                
                                for row in results_data:
                                    assignments.append(
                                        AssignmentResult(
                                            worker_name=row["worker_name"],
                                            shift_name=row["shift_name"],
                                            cost=float(row["cost"]) if row["cost"] else 0.0
                                        )
                                    )
                                
                                if assignments:
                                    logger.info(f"Found {len(assignments)} assignments in {default_table}")
                                    break
                            except Exception as e:
                                logger.debug(f"Default table {default_table} query failed: {e}")
                                continue
                                
                except Exception as e:
                    logger.error(f"Failed to query legacy tables for run {run_id}: {e}")
            
            # Build summaries
            worker_summary = {}
            shift_summary = {}
            
            for a in assignments:
                # Worker summary
                if a.worker_name not in worker_summary:
                    worker_summary[a.worker_name] = {"shifts": [], "total_cost": 0}
                worker_summary[a.worker_name]["shifts"].append(a.shift_name)
                worker_summary[a.worker_name]["total_cost"] += a.cost
                
                # Shift summary
                if a.shift_name not in shift_summary:
                    shift_summary[a.shift_name] = {"workers": [], "assigned": 0}
                shift_summary[a.shift_name]["workers"].append(a.worker_name)
                shift_summary[a.shift_name]["assigned"] += 1
            
            return OptimizationResultOut(
                run_id=run_id,
                status=RunStatus(db_run.status),
                total_cost=db_run.total_cost,
                solve_time_seconds=db_run.solve_time_seconds,
                assignments=assignments,
                worker_summary=worker_summary,
                shift_summary=shift_summary
            )
    
    # ============== Scalable / Paginated Results ==============

    def _resolve_results_table(self, run_id: str) -> Optional[tuple[str, dict]]:
        """Resolve the results table for a run.

        Returns ``(table, run_meta)`` where *run_meta* is a plain dict of
        scalar values extracted while the session is still open, avoiding
        detached-instance errors.
        """
        with session_scope() as session:
            db_run = session.get(OptimizationRunDB, run_id)
            if not db_run:
                return None
            db_config = session.get(OptimizationConfigDB, db_run.config_id)
            results_table = self._get_results_table(db_config) if db_config else None
            if not results_table:
                return None
            run_meta = {
                "status": db_run.status,
                "total_cost": db_run.total_cost,
                "solve_time_seconds": db_run.solve_time_seconds,
                "num_workers_assigned": db_run.num_workers_assigned,
                "num_shifts_covered": db_run.num_shifts_covered,
            }
            return (results_table, run_meta)

    def _run_scoped_sql(self, results_table: str, run_id: str, sql_body: str) -> list[dict]:
        """Execute a SQL query scoped to a run_id against the results table."""
        db_service = get_databricks_service()
        return db_service.execute_sql(
            f"{sql_body}".replace("{TABLE}", results_table).replace("{RUN_ID}", run_id)
        )

    def get_results_summary(self, run_id: str) -> Optional[RunResultsSummaryOut]:
        """Return lightweight KPI summary (no row-level data)."""
        resolved = self._resolve_results_table(run_id)
        if resolved is None:
            return None
        results_table, run_meta = resolved

        if run_meta["status"] != RunStatus.COMPLETED.value:
            return RunResultsSummaryOut(
                run_id=run_id,
                status=RunStatus(run_meta["status"]),
                total_cost=run_meta["total_cost"],
                solve_time_seconds=run_meta["solve_time_seconds"],
                num_workers_assigned=run_meta["num_workers_assigned"],
                num_shifts_covered=run_meta["num_shifts_covered"],
            )

        try:
            rows = self._run_scoped_sql(results_table, run_id, """
                SELECT
                    COUNT(*) AS total_assignments,
                    COUNT(DISTINCT worker_name) AS num_workers,
                    COUNT(DISTINCT shift_name) AS num_shifts,
                    COALESCE(SUM(cost), 0) AS total_cost,
                    AVG(cost) AS avg_cost,
                    MIN(cost) AS min_cost,
                    MAX(cost) AS max_cost
                FROM {TABLE}
                WHERE run_id = '{RUN_ID}'
            """)
            r = rows[0] if rows else {}
            return RunResultsSummaryOut(
                run_id=run_id,
                status=RunStatus(run_meta["status"]),
                total_cost=float(r.get("total_cost", 0) or 0),
                solve_time_seconds=run_meta["solve_time_seconds"],
                num_workers_assigned=int(r.get("num_workers", 0) or 0),
                num_shifts_covered=int(r.get("num_shifts", 0) or 0),
                total_assignments=int(r.get("total_assignments", 0) or 0),
                avg_cost_per_assignment=float(r["avg_cost"]) if r.get("avg_cost") else None,
                min_assignment_cost=float(r["min_cost"]) if r.get("min_cost") else None,
                max_assignment_cost=float(r["max_cost"]) if r.get("max_cost") else None,
            )
        except Exception as e:
            logger.error(f"Failed to get results summary for run {run_id}: {e}")
            return RunResultsSummaryOut(
                run_id=run_id,
                status=RunStatus(run_meta["status"]),
                total_cost=run_meta["total_cost"],
                solve_time_seconds=run_meta["solve_time_seconds"],
                num_workers_assigned=run_meta["num_workers_assigned"],
                num_shifts_covered=run_meta["num_shifts_covered"],
            )

    def get_paged_assignments(
        self,
        run_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        sort: str = "worker_name",
        sort_dir: str = "asc",
        shift_name: Optional[str] = None,
        worker_name: Optional[str] = None,
    ) -> Optional[PagedAssignmentsOut]:
        """Return a page of raw assignment rows with optional entity filter."""
        resolved = self._resolve_results_table(run_id)
        if resolved is None:
            return None
        results_table, _ = resolved

        if sort not in VALID_ASSIGNMENT_SORT_FIELDS:
            sort = "worker_name"
        sort_dir_sql = "DESC" if sort_dir.lower() == "desc" else "ASC"

        where = f"run_id = '{run_id}'"
        if shift_name:
            where += f" AND shift_name = '{shift_name}'"
        if worker_name:
            where += f" AND worker_name = '{worker_name}'"

        db_service = get_databricks_service()

        count_rows = db_service.execute_sql(
            f"SELECT COUNT(*) AS cnt FROM {results_table} WHERE {where}"
        )
        total = int(count_rows[0]["cnt"]) if count_rows else 0

        data_rows = db_service.execute_sql(
            f"SELECT worker_name, shift_name, cost "
            f"FROM {results_table} WHERE {where} "
            f"ORDER BY {sort} {sort_dir_sql} "
            f"LIMIT {limit} OFFSET {offset}"
        )

        assignments = [
            AssignmentResult(
                worker_name=r["worker_name"],
                shift_name=r["shift_name"],
                cost=float(r["cost"]) if r["cost"] else 0.0,
            )
            for r in data_rows
        ]

        return PagedAssignmentsOut(
            run_id=run_id,
            assignments=assignments,
            pagination=PaginationMeta(
                offset=offset, limit=limit, total=total,
                has_more=(offset + limit) < total,
            ),
        )

    def get_shift_aggregates(
        self,
        run_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        sort: str = "name",
        sort_dir: str = "asc",
    ) -> Optional[PagedShiftAggregatesOut]:
        """Return paginated shift-level aggregate rows."""
        resolved = self._resolve_results_table(run_id)
        if resolved is None:
            return None
        results_table, _ = resolved

        sort_map = {"name": "shift_name", "count": "assigned_count", "total_cost": "total_cost"}
        sort_col = sort_map.get(sort, "shift_name")
        sort_dir_sql = "DESC" if sort_dir.lower() == "desc" else "ASC"

        db_service = get_databricks_service()

        count_rows = db_service.execute_sql(
            f"SELECT COUNT(DISTINCT shift_name) AS cnt FROM {results_table} WHERE run_id = '{run_id}'"
        )
        total = int(count_rows[0]["cnt"]) if count_rows else 0

        data_rows = db_service.execute_sql(
            f"SELECT shift_name, COUNT(*) AS assigned_count, COALESCE(SUM(cost), 0) AS total_cost "
            f"FROM {results_table} WHERE run_id = '{run_id}' "
            f"GROUP BY shift_name "
            f"ORDER BY {sort_col} {sort_dir_sql} "
            f"LIMIT {limit} OFFSET {offset}"
        )

        shifts = [
            ShiftAggregateOut(
                shift_name=r["shift_name"],
                assigned_count=int(r["assigned_count"]),
                total_cost=float(r["total_cost"]) if r["total_cost"] else 0.0,
            )
            for r in data_rows
        ]

        return PagedShiftAggregatesOut(
            run_id=run_id,
            shifts=shifts,
            pagination=PaginationMeta(
                offset=offset, limit=limit, total=total,
                has_more=(offset + limit) < total,
            ),
        )

    def get_worker_aggregates(
        self,
        run_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        sort: str = "name",
        sort_dir: str = "asc",
    ) -> Optional[PagedWorkerAggregatesOut]:
        """Return paginated worker-level aggregate rows."""
        resolved = self._resolve_results_table(run_id)
        if resolved is None:
            return None
        results_table, _ = resolved

        sort_map = {"name": "worker_name", "count": "shift_count", "total_cost": "total_cost"}
        sort_col = sort_map.get(sort, "worker_name")
        sort_dir_sql = "DESC" if sort_dir.lower() == "desc" else "ASC"

        db_service = get_databricks_service()

        count_rows = db_service.execute_sql(
            f"SELECT COUNT(DISTINCT worker_name) AS cnt FROM {results_table} WHERE run_id = '{run_id}'"
        )
        total = int(count_rows[0]["cnt"]) if count_rows else 0

        data_rows = db_service.execute_sql(
            f"SELECT worker_name, COUNT(*) AS shift_count, COALESCE(SUM(cost), 0) AS total_cost "
            f"FROM {results_table} WHERE run_id = '{run_id}' "
            f"GROUP BY worker_name "
            f"ORDER BY {sort_col} {sort_dir_sql} "
            f"LIMIT {limit} OFFSET {offset}"
        )

        workers = [
            WorkerAggregateOut(
                worker_name=r["worker_name"],
                shift_count=int(r["shift_count"]),
                total_cost=float(r["total_cost"]) if r["total_cost"] else 0.0,
            )
            for r in data_rows
        ]

        return PagedWorkerAggregatesOut(
            run_id=run_id,
            workers=workers,
            pagination=PaginationMeta(
                offset=offset, limit=limit, total=total,
                has_more=(offset + limit) < total,
            ),
        )

    def get_focused_graph(
        self,
        run_id: str,
        *,
        shift_name: Optional[str] = None,
        worker_name: Optional[str] = None,
        limit: int = 200,
    ) -> Optional[GraphSubsetOut]:
        """Return a bounded subgraph for the graph explorer.

        If no focus entity is given and the graph is small, returns the full
        graph. Otherwise returns only the neighbourhood of the focus entity,
        or an empty graph with total counts so the UI can prompt for focus.
        """
        resolved = self._resolve_results_table(run_id)
        if resolved is None:
            return None
        results_table, _ = resolved

        db_service = get_databricks_service()

        # Get total size to decide strategy
        size_rows = db_service.execute_sql(
            f"SELECT COUNT(*) AS cnt, "
            f"COUNT(DISTINCT worker_name) AS w, "
            f"COUNT(DISTINCT shift_name) AS s "
            f"FROM {results_table} WHERE run_id = '{run_id}'"
        )
        sr = size_rows[0] if size_rows else {}
        total_edges = int(sr.get("cnt", 0) or 0)
        total_workers = int(sr.get("w", 0) or 0)
        total_shifts = int(sr.get("s", 0) or 0)
        total_nodes = total_workers + total_shifts

        # Determine query filter
        focus_entity = shift_name or worker_name
        focus_type = "shift" if shift_name else ("worker" if worker_name else None)

        if focus_entity:
            col = "shift_name" if focus_type == "shift" else "worker_name"
            where = f"run_id = '{run_id}' AND {col} = '{focus_entity}'"
        elif total_edges <= GRAPH_ELEMENT_THRESHOLD:
            where = f"run_id = '{run_id}'"
        else:
            # Too large and no focus -- return metadata only
            return GraphSubsetOut(
                run_id=run_id,
                total_nodes=total_nodes,
                total_edges=total_edges,
                is_complete=False,
            )

        edge_rows = db_service.execute_sql(
            f"SELECT worker_name, shift_name, cost "
            f"FROM {results_table} WHERE {where} "
            f"LIMIT {limit}"
        )

        worker_set: dict[str, float] = {}
        shift_set: dict[str, int] = {}
        edges = []
        for r in edge_rows:
            wn = r["worker_name"]
            sn = r["shift_name"]
            cost = float(r["cost"]) if r["cost"] else 0.0
            edges.append({
                "id": f"edge-{wn}-{sn}",
                "source": f"worker-{wn}",
                "target": f"shift-{sn}",
                "cost": cost,
                "workerName": wn,
                "shiftName": sn,
            })
            worker_set[wn] = worker_set.get(wn, 0) + cost
            shift_set[sn] = shift_set.get(sn, 0) + 1

        nodes = []
        for wn, tc in worker_set.items():
            nodes.append({
                "id": f"worker-{wn}",
                "kind": "worker",
                "label": wn,
                "totalCost": tc,
            })
        for sn, cnt in shift_set.items():
            nodes.append({
                "id": f"shift-{sn}",
                "kind": "shift",
                "label": sn,
                "assignedCount": cnt,
            })

        is_complete = (not focus_entity) and len(edge_rows) < limit

        return GraphSubsetOut(
            run_id=run_id,
            focus_entity=focus_entity,
            focus_type=focus_type,
            nodes=nodes,
            edges=edges,
            total_nodes=total_nodes,
            total_edges=total_edges,
            is_complete=is_complete,
        )

    # ============== Helper Methods ==============
    
    def _build_config_dict(self, db_config: OptimizationConfigDB) -> dict:
        """Build config dictionary to pass to notebook."""
        return {
            "source_catalog": db_config.source_catalog,
            "source_schema": db_config.source_schema,
            "workers_table": db_config.workers_table,
            "shifts_table": db_config.shifts_table,
            "availability_table": db_config.availability_table,
            "worker_name_col": db_config.worker_name_col,
            "worker_pay_col": db_config.worker_pay_col,
            "shift_name_col": db_config.shift_name_col,
            "shift_required_col": db_config.shift_required_col,
            "availability_worker_col": db_config.availability_worker_col,
            "availability_shift_col": db_config.availability_shift_col,
            "max_shifts_per_worker": db_config.max_shifts_per_worker,
            "time_limit_seconds": db_config.time_limit_seconds or 60,
        }
    
    def _get_results_table(self, db_config: Optional[OptimizationConfigDB]) -> str:
        """Get the unified results table for a config.
        
        Always returns a fully-qualified table name (catalog.schema.table).
        """
        catalog = db_config.target_catalog if db_config and db_config.target_catalog else conf.default_catalog
        schema = db_config.target_schema if db_config and db_config.target_schema else conf.default_schema
        
        if db_config and db_config.results_table:
            # If results_table is already fully qualified, return as-is
            if "." in db_config.results_table:
                return db_config.results_table
            # Otherwise, prepend catalog.schema
            return f"{catalog}.{schema}.{db_config.results_table}"
        
        # Default unified results table
        return f"{catalog}.{schema}.optimization_results"
    
    def _refresh_run_status(self, session: Session, db_run: OptimizationRunDB) -> None:
        """Refresh run status from Databricks with comprehensive error handling."""
        try:
            db_service = get_databricks_service()
            status = db_service.get_run_status(db_run.databricks_run_id)
            
            lifecycle_state = status.get("state")
            result_state = status.get("result_state")
            state_message = status.get("state_message")
            run_page_url = status.get("run_page_url")
            
            logger.info(f"Run {db_run.id} Databricks status: lifecycle={lifecycle_state}, result={result_state}")
            
            # Handle terminal states
            if lifecycle_state == "TERMINATED":
                if result_state == "SUCCESS":
                    # Run completed - try to get output
                    # Try to get notebook output to check for infeasibility
                    try:
                        output = db_service.get_run_output(db_run.databricks_run_id)
                        if output:
                            status_from_output = output.get("status")
                            error_type = output.get("error_type")
                            
                            # Check if optimization was infeasible
                            if status_from_output == "infeasible" or error_type == "infeasible":
                                db_run.status = RunStatus.FAILED.value
                                db_run.solve_time_seconds = output.get("solve_time_seconds")
                                
                                # Build user-friendly error message
                                message = output.get("message", "Optimization problem is infeasible")
                                details = output.get("details", "")
                                config_info = output.get("configuration", {})
                                
                                error_parts = [
                                    "⚠️ INFEASIBLE PROBLEM",
                                    "",
                                    message,
                                    "",
                                    details
                                ]
                                
                                if config_info:
                                    error_parts.append("")
                                    error_parts.append("Configuration:")
                                    if config_info.get("max_shifts_per_worker"):
                                        error_parts.append(f"  • Max shifts per worker: {config_info['max_shifts_per_worker']}")
                                    error_parts.append(f"  • Workers: {config_info.get('num_workers', 'N/A')}")
                                    error_parts.append(f"  • Shifts: {config_info.get('num_shifts', 'N/A')}")
                                    error_parts.append(f"  • Total positions needed: {config_info.get('total_shift_requirements', 'N/A')}")
                                
                                db_run.error_message = "\n".join(error_parts)
                                logger.warning(f"Run {db_run.id} is infeasible")
                                
                            # Check for other solver errors
                            elif status_from_output == "solver_error" or error_type == "solver_error":
                                db_run.status = RunStatus.FAILED.value
                                db_run.solve_time_seconds = output.get("solve_time_seconds")
                                db_run.error_message = f"{output.get('message', 'Solver error')}\n\n{output.get('details', '')}"
                                logger.error(f"Run {db_run.id} solver error: {db_run.error_message}")
                                
                            # Successful optimization
                            else:
                                db_run.status = RunStatus.COMPLETED.value
                                db_run.total_cost = output.get("total_cost")
                                db_run.solve_time_seconds = output.get("solve_time_seconds")
                                db_run.num_workers_assigned = output.get("num_workers_assigned")
                                db_run.num_shifts_covered = output.get("num_shifts_covered")
                                logger.info(f"Run {db_run.id} completed with cost=${db_run.total_cost}")
                        else:
                            # No notebook output available (notebook may not have
                            # called dbutils.notebook.exit, or output not yet
                            # propagated).  Databricks already confirmed SUCCESS,
                            # so mark completed.
                            logger.warning(
                                f"Run {db_run.id} TERMINATED/SUCCESS but no "
                                f"notebook output available; marking COMPLETED"
                            )
                            db_run.status = RunStatus.COMPLETED.value
                    except Exception as e:
                        # If we can't parse output, assume success
                        logger.warning(f"Could not get notebook output for run {db_run.id}: {e}")
                        db_run.status = RunStatus.COMPLETED.value
                            
                elif result_state in ["FAILED", "TIMEDOUT"]:
                    db_run.status = RunStatus.FAILED.value
                    # Build detailed error message
                    error_parts = []
                    if state_message:
                        error_parts.append(state_message)
                    if run_page_url:
                        error_parts.append(f"View run: {run_page_url}")
                    db_run.error_message = "\n".join(error_parts) if error_parts else f"Run {result_state}"
                    logger.error(f"Run {db_run.id} failed: {db_run.error_message}")
                    
                elif result_state == "CANCELED":
                    db_run.status = RunStatus.CANCELLED.value
                    db_run.error_message = "Run was cancelled"
                    logger.info(f"Run {db_run.id} was cancelled")

                else:
                    # TERMINATED but result_state is None or an unexpected value.
                    # This can happen transiently when Databricks propagates
                    # task-level state to run-level state.  Treat as COMPLETED
                    # (the notebook succeeded since lifecycle is TERMINATED, not
                    # INTERNAL_ERROR) and try to extract output.
                    logger.warning(
                        f"Run {db_run.id} TERMINATED with unexpected "
                        f"result_state={result_state!r}; treating as COMPLETED"
                    )
                    try:
                        output = db_service.get_run_output(db_run.databricks_run_id)
                        if output:
                            db_run.total_cost = output.get("total_cost")
                            db_run.solve_time_seconds = output.get("solve_time_seconds")
                            db_run.num_workers_assigned = output.get("num_workers_assigned")
                            db_run.num_shifts_covered = output.get("num_shifts_covered")
                    except Exception as e:
                        logger.warning(f"Could not get notebook output for run {db_run.id}: {e}")
                    db_run.status = RunStatus.COMPLETED.value

                db_run.updated_at = datetime.utcnow()
                db_run.completed_at = datetime.utcnow()
                session.add(db_run)
                session.commit()
                
            elif lifecycle_state == "INTERNAL_ERROR":
                # Databricks internal error
                db_run.status = RunStatus.FAILED.value
                db_run.error_message = state_message or "Databricks internal error"
                if run_page_url:
                    db_run.error_message += f"\nView run: {run_page_url}"
                db_run.updated_at = datetime.utcnow()
                db_run.completed_at = datetime.utcnow()
                session.add(db_run)
                session.commit()
                logger.error(f"Run {db_run.id} hit internal error: {db_run.error_message}")
                
            elif lifecycle_state == "SKIPPED":
                db_run.status = RunStatus.CANCELLED.value
                db_run.error_message = "Run was skipped"
                db_run.updated_at = datetime.utcnow()
                session.add(db_run)
                session.commit()
                
        except Exception as e:
            logger.error(f"Failed to refresh run status for {db_run.id}: {e}")
            # Mark as FAILED so the UI stops polling instead of spinning forever
            try:
                db_run.status = RunStatus.FAILED.value
                db_run.error_message = f"Status check failed: {str(e)}"
                db_run.updated_at = datetime.utcnow()
                db_run.completed_at = datetime.utcnow()
                session.add(db_run)
                session.commit()
            except Exception:
                pass  # Don't raise if we can't update
    
    def _config_to_out(self, db_config: OptimizationConfigDB) -> OptimizationConfigOut:
        """Convert DB model to output model."""
        return OptimizationConfigOut(
            id=db_config.id,
            name=db_config.name,
            description=db_config.description,
            owner_user=db_config.owner_user,
            source_catalog=db_config.source_catalog,
            source_schema=db_config.source_schema,
            workers_table=db_config.workers_table,
            shifts_table=db_config.shifts_table,
            availability_table=db_config.availability_table,
            worker_name_col=db_config.worker_name_col,
            worker_pay_col=db_config.worker_pay_col,
            shift_name_col=db_config.shift_name_col,
            shift_required_col=db_config.shift_required_col,
            availability_worker_col=db_config.availability_worker_col,
            availability_shift_col=db_config.availability_shift_col,
            max_shifts_per_worker=db_config.max_shifts_per_worker,
            time_limit_seconds=db_config.time_limit_seconds,
            target_catalog=db_config.target_catalog,
            target_schema=db_config.target_schema,
            results_table=db_config.results_table,
            databricks_job_id=db_config.databricks_job_id,
            created_at=db_config.created_at,
            updated_at=db_config.updated_at
        )
    
    def _run_to_out(self, db_run: OptimizationRunDB) -> OptimizationRunOut:
        """Convert DB model to output model."""
        return OptimizationRunOut(
            id=db_run.id,
            config_id=db_run.config_id,
            run_name=db_run.run_name,
            owner_user=db_run.owner_user,
            status=RunStatus(db_run.status),
            databricks_run_id=db_run.databricks_run_id,
            total_cost=db_run.total_cost,
            solve_time_seconds=db_run.solve_time_seconds,
            num_workers_assigned=db_run.num_workers_assigned,
            num_shifts_covered=db_run.num_shifts_covered,
            error_message=db_run.error_message,
            created_at=db_run.created_at,
            updated_at=db_run.updated_at,
            completed_at=db_run.completed_at
        )


# Singleton instance
_optimization_service: Optional[OptimizationService] = None


def get_optimization_service() -> OptimizationService:
    """Get the singleton OptimizationService instance."""
    global _optimization_service
    if _optimization_service is None:
        _optimization_service = OptimizationService()
    return _optimization_service
