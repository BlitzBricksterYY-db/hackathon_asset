# staffing-optimization ✨

> A modern full-stack application built with [`apx`](https://github.com/databricks-solutions/apx) 🚀

## 🛠️ Tech Stack

This application leverages a powerful, modern tech stack:

- **Backend** 🐍 Python + [FastAPI](https://fastapi.tiangolo.com/)
- **Frontend** ⚛️ React + [shadcn/ui](https://ui.shadcn.com/)
- **API Client** 🔄 Auto-generated with [orval](https://orval.dev/) from OpenAPI schema

## 🚀 Quick Start

### Prerequisites

- [Databricks CLI](https://docs.databricks.com/dev-tools/cli/install.html) (for deployment)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [bun](https://bun.sh/) (JavaScript runtime)
- [apx](https://github.com/databricks-solutions/apx) — install via `uv tool install apx` or the [install script](https://databricks-solutions.github.io/apx/install.sh)

### Development Mode

Start all development servers (backend, frontend, and OpenAPI watcher) in detached mode:

```bash
uv run apx dev start
```

This will start an apx development server, which runs the backend, frontend, and OpenAPI watcher. 
All servers run in the background, with logs kept in-memory of the apx dev server.

### 📊 Monitoring & Logs

```bash
# View all logs
uv run apx dev logs

# Stream logs in real-time
uv run apx dev logs -f

# Check server status
uv run apx dev status

# Stop all servers
uv run apx dev stop
```

## ✅ Code Quality

Run type checking and linting for both TypeScript and Python:

```bash
uv run apx dev check
```

## 📦 Build

Create a production-ready build:

```bash
uv run apx build
```

## 🚢 Deployment (Easy Button)

The bundle creates the app, shared GPU job, SQL warehouse, Lakebase project (for app state), and Unity Catalog schema in one step.

**Prerequisites:** Databricks CLI configured with a profile (DEFAULT or named). A Unity Catalog catalog must already exist. For bundle-managed Lakebase (postgres_projects, etc.), use Databricks CLI 0.287.0+.

**Deploy** (uses DEFAULT profile and demos catalog by default):

```bash
databricks bundle deploy -t dev -p DEFAULT --var default_catalog=demos
```

Then deploy the app to compute (bundle creates the app resource but doesn't start it):

```bash
databricks apps deploy staffing-optimization --source-code-path /Workspace/Users/<you>/.bundle/staffing-optimization/dev/files/.build -p DEFAULT
```

Or use the helper script (no args = dev + DEFAULT + demos):

```bash
./scripts/deploy.sh
```

The script runs both steps automatically.

**What the bundle creates:**
- Databricks App (staffing-optimization)
- Serverless GPU job (cuOpt optimization)
- SQL warehouse (for data operations)
- Lakebase project, branch, and endpoint (for configs and runs)
- UC schema `{catalog}.staffing_optimization`

**What you must have:**
- An existing Unity Catalog catalog (name passed via `default_catalog`)
- Workspace permissions to create apps, jobs, warehouses, and Lakebase resources

**Optional overrides** (via `--var key=value` or `BUNDLE_VAR_key=value`):
- `default_schema` — schema name (default: staffing_optimization)
- `lakebase_project_display_name` — Lakebase project display name

### Lakebase Autoscaling bootstrap (required)

When using Lakebase Autoscaling, the app's service principal needs project ACL and Postgres OAuth role setup that the bundle does not yet manage. The deploy script runs a **post-deploy bootstrap** between `bundle deploy` and `apps deploy`:

1. **Project ACL** — Grants `CAN_USE` on the Lakebase project to the app SP via `databricks permissions update database-projects <uid>`.
2. **OAuth Postgres role** — Creates the app SP's Postgres role using `databricks_auth` and `databricks_create_role()` (not plain `CREATE ROLE`).
3. **DB grants** — Grants CONNECT, schema USAGE/CREATE, and table SELECT/INSERT/UPDATE/DELETE (including default privileges) to the app SP.

Until bundle resources support app SP wiring for Lakebase Autoscaling, this bootstrap step is required. Without it, the app will fail with `password authentication failed` when calling `/api/configs` or `/api/runs`.

### Unity Catalog bootstrap (required)

The deploy script also grants Unity Catalog permissions to the app SP so it can create schemas and tables (e.g. for `/api/generate-sample-data`):

1. **Catalog** — `USE_CATALOG`, `CREATE_SCHEMA` on the default catalog (e.g. `demos`).
2. **Schema** — `USE_SCHEMA`, `CREATE_TABLE`, `MODIFY`, `SELECT` on `{catalog}.staffing_optimization`.

Without these grants, the app fails with `User does not have CREATE SCHEMA and USE CATALOG on Catalog` when generating sample data.

---

<p align="center">Built with ❤️ using <a href="https://github.com/databricks-solutions/apx">apx</a></p>