#!/usr/bin/env bash
# Deploy staffing-optimization bundle.
# Usage: ./scripts/deploy.sh [target] [profile] [catalog]
# Example: ./scripts/deploy.sh
# Example: ./scripts/deploy.sh dev DEFAULT demos
#
# Defaults: target=dev, profile=DEFAULT, catalog=demos
# Requires Databricks CLI 0.287.0+ (for bundle-managed Lakebase).
# Upgrade: brew upgrade databricks

set -e

MIN_CLI_VERSION="0.287.0"
CLI_VERSION=$(databricks -v 2>/dev/null | sed -n 's/.*v\([0-9][0-9.]*\).*/\1/p' || echo "0")
if [[ "$(printf '%s\n' "$MIN_CLI_VERSION" "$CLI_VERSION" | sort -V | head -n1)" != "$MIN_CLI_VERSION" ]]; then
  echo "Error: Databricks CLI $CLI_VERSION is older than required $MIN_CLI_VERSION."
  echo "Upgrade with: brew upgrade databricks"
  exit 1
fi

TARGET="${1:-dev}"
PROFILE="${2:-DEFAULT}"
CATALOG="${3:-demos}"

echo "Deploying bundle (target=$TARGET, profile=$PROFILE, catalog=$CATALOG)..."
databricks bundle deploy -t "$TARGET" -p "$PROFILE" --var "default_catalog=$CATALOG"

# Deploy app to compute (bundle creates the app resource but doesn't deploy to compute)
WORKSPACE_USER=$(databricks bundle summary -t "$TARGET" -p "$PROFILE" 2>/dev/null | sed -n 's/.*User:[[:space:]]*//p') || true
if [[ -n "$WORKSPACE_USER" ]]; then
  SOURCE_PATH="/Workspace/Users/${WORKSPACE_USER}/.bundle/staffing-optimization/${TARGET}/files/.build"

  # Bootstrap Lakebase Autoscaling: project ACL + OAuth Postgres role + DB grants.
  # Run after bundle deploy and before apps deploy so the app starts with valid DB auth.
  echo "Bootstrapping Lakebase for app service principal..."
  DATABRICKS_PROFILE="$PROFILE" UC_CATALOG="$CATALOG" uv run python - <<'PY'
import json
import os
import subprocess
import psycopg2

profile = os.environ.get("DATABRICKS_PROFILE", "DEFAULT")
project_name = "staffing-optimization-db"
project_path = f"projects/{project_name}"
endpoint = f"{project_path}/branches/production/endpoints/primary"
db_name = "databricks_postgres"
schema = "staffing_optimization"
app_name = "staffing-optimization"


def run_json(args: list[str]) -> dict:
    out = subprocess.check_output(args, text=True)
    return json.loads(out)


# 1. Grant Lakebase project ACL (CAN_USE) so app SP can access the project
app = run_json(["databricks", "apps", "get", app_name, "-p", profile, "--output", "json"])
app_sp = app["service_principal_client_id"]

projects = run_json(["databricks", "postgres", "list-projects", "-p", profile, "--output", "json"])
project_uid = None
for p in projects:
    if p.get("name") == project_path:
        project_uid = p.get("uid")
        break
if not project_uid:
    raise RuntimeError(f"Lakebase project {project_path} not found in list-projects")

acl_json = json.dumps({
    "access_control_list": [
        {"service_principal_name": app_sp, "permission_level": "CAN_USE"}
    ]
})
subprocess.run(
    ["databricks", "permissions", "update", "database-projects", project_uid, "--json", acl_json, "-p", profile],
    check=True,
)
print(f"Granted CAN_USE on project {project_uid} to app SP {app_sp}")

# 2. Create OAuth Postgres role via databricks_auth (not plain CREATE ROLE)
ep = run_json(["databricks", "postgres", "get-endpoint", endpoint, "-p", profile, "--output", "json"])
host = ep["status"]["hosts"]["host"]

cred = run_json(["databricks", "postgres", "generate-database-credential", endpoint, "-p", profile, "--output", "json"])
token = cred.get("token")
if not token:
    raise RuntimeError("No token returned from generate-database-credential")

me = run_json(["databricks", "current-user", "me", "-p", profile, "--output", "json"])
admin_user = me["userName"]

conn = psycopg2.connect(
    host=host,
    port=5432,
    dbname=db_name,
    user=admin_user,
    password=token,
    sslmode="require",
)
# Check if role exists with wrong auth (NO_LOGIN) via Lakebase API
roles = run_json(["databricks", "postgres", "list-roles", f"{project_path}/branches/production", "-p", profile, "--output", "json"])
role_needs_recreate = False
for r in roles:
    if r.get("status", {}).get("postgres_role") == app_sp:
        if r.get("status", {}).get("auth_method") != "LAKEBASE_OAUTH_V1":
            role_needs_recreate = True
        break

conn.autocommit = True
with conn.cursor() as cur:
    cur.execute("CREATE EXTENSION IF NOT EXISTS databricks_auth")
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (app_sp,))
    exists = cur.fetchone() is not None
    if exists and role_needs_recreate:
        # Role has wrong auth (e.g. NO_LOGIN). Revoke grants, drop, recreate.
        cur.execute(f'REVOKE ALL ON DATABASE "{db_name}" FROM "{app_sp}"')
        cur.execute(f'REVOKE ALL ON SCHEMA "{schema}" FROM "{app_sp}"')
        cur.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA "{schema}" FROM "{app_sp}"')
        cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" REVOKE ALL ON TABLES FROM "{app_sp}"')
        cur.execute(f'DROP ROLE IF EXISTS "{app_sp}"')
    if not exists or role_needs_recreate:
        cur.execute("SELECT databricks_create_role(%s, 'SERVICE_PRINCIPAL')", (app_sp,))
    cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    cur.execute(f'GRANT CONNECT ON DATABASE "{db_name}" TO "{app_sp}"')
    cur.execute(f'GRANT USAGE, CREATE ON SCHEMA "{schema}" TO "{app_sp}"')
    cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "{schema}" TO "{app_sp}"')
    cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{app_sp}"')
conn.close()

print(f"Lakebase OAuth role and grants configured for app principal: {app_sp}")
PY
  echo "Lakebase bootstrap complete."

  # Grant Unity Catalog permissions so app SP can create schemas/tables (generate-sample-data, etc.)
  echo "Granting Unity Catalog permissions to app service principal..."
  DATABRICKS_PROFILE="$PROFILE" UC_CATALOG="$CATALOG" uv run python - <<'PY'
import json
import os
import subprocess

profile = os.environ.get("DATABRICKS_PROFILE", "DEFAULT")
catalog = os.environ.get("UC_CATALOG", "demos")
schema = "staffing_optimization"
app_name = "staffing-optimization"


def run_json(args: list[str]) -> dict:
    out = subprocess.check_output(args, text=True)
    return json.loads(out)


app = run_json(["databricks", "apps", "get", app_name, "-p", profile, "--output", "json"])
app_sp = app["service_principal_client_id"]

# Catalog: USE_CATALOG, CREATE_SCHEMA (for create_schema_if_not_exists)
catalog_changes = json.dumps({
    "changes": [{"principal": app_sp, "add": ["USE_CATALOG", "CREATE_SCHEMA"]}]
})
subprocess.run(
    ["databricks", "grants", "update", "catalog", catalog, "--json", catalog_changes, "-p", profile],
    check=True,
)
print(f"Granted USE_CATALOG, CREATE_SCHEMA on catalog {catalog} to app SP {app_sp}")

# Schema: USE_SCHEMA, CREATE_TABLE, MODIFY, SELECT (for sample data generation and queries)
schema_full_name = f"{catalog}.{schema}"
schema_changes = json.dumps({
    "changes": [{"principal": app_sp, "add": ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"]}]
})
subprocess.run(
    ["databricks", "grants", "update", "schema", schema_full_name, "--json", schema_changes, "-p", profile],
    check=True,
)
print(f"Granted USE_SCHEMA, CREATE_TABLE, MODIFY, SELECT on schema {schema_full_name} to app SP {app_sp}")
PY
  echo "Unity Catalog grants complete."

  echo "Deploying app to compute from $SOURCE_PATH..."
  databricks apps deploy staffing-optimization --source-code-path "$SOURCE_PATH" -p "$PROFILE"
  echo "App deployed and started."
else
  echo "Could not determine workspace user; deploy app manually:"
  echo "  databricks apps deploy staffing-optimization --source-code-path /Workspace/Users/<you>/.bundle/staffing-optimization/<target>/files/.build -p $PROFILE"
fi
echo "Deploy complete."
