"""
API Router for the Staffing Optimization application.
"""
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.iam import User as UserOut
import csv
import io
import json

from .models import (
    VersionOut,
    WorkspaceInfoOut,
    CatalogInfo,
    SchemaInfo,
    TableInfo,
    TableColumnsOut,
    OptimizationConfigCreate,
    OptimizationConfigOut,
    OptimizationRunCreate,
    OptimizationRunOut,
    OptimizationResultOut,
    GenerateSampleDataRequest,
    GenerateSampleDataResponse,
    ExportFormat,
    RunResultsSummaryOut,
    PagedAssignmentsOut,
    PagedShiftAggregatesOut,
    PagedWorkerAggregatesOut,
    GraphSubsetOut,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
)
from .dependencies import get_obo_ws, get_current_user_email
from .config import conf
from .databricks_service import get_databricks_service
from .optimization_service import get_optimization_service
from .logger import logger

api = APIRouter(prefix=conf.api_prefix)


# ============== Health & Info ==============

@api.get("/version", response_model=VersionOut, operation_id="version")
async def version():
    """Get application version."""
    return VersionOut.from_metadata()


@api.get("/workspace-info", response_model=WorkspaceInfoOut, operation_id="getWorkspaceInfo")
def workspace_info():
    """Return workspace metadata needed by the frontend (host URL, shared job ID)."""
    import os
    host = os.environ.get("DATABRICKS_HOST") or conf.databricks_host
    return WorkspaceInfoOut(
        host=host,
        databricks_job_id=conf.databricks_job_id,
    )


@api.get("/current-user", response_model=UserOut, operation_id="currentUser")
def me(obo_ws: Annotated[WorkspaceClient, Depends(get_obo_ws)]):
    """Get current authenticated user."""
    return obo_ws.current_user.me()


# ============== Unity Catalog - Catalogs ==============

@api.get("/catalogs", response_model=list[CatalogInfo], operation_id="listCatalogs")
def list_catalogs():
    """List all accessible Unity Catalogs."""
    try:
        service = get_databricks_service()
        return service.list_catalogs()
    except Exception as e:
        logger.error(f"Failed to list catalogs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Unity Catalog - Schemas ==============

@api.get(
    "/catalogs/{catalog_name}/schemas",
    response_model=list[SchemaInfo],
    operation_id="listSchemas"
)
def list_schemas(catalog_name: str):
    """List all schemas in a catalog."""
    try:
        service = get_databricks_service()
        return service.list_schemas(catalog_name)
    except Exception as e:
        logger.error(f"Failed to list schemas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Unity Catalog - Tables ==============

@api.get(
    "/catalogs/{catalog_name}/schemas/{schema_name}/tables",
    response_model=list[TableInfo],
    operation_id="listTables"
)
def list_tables(catalog_name: str, schema_name: str):
    """List all tables in a schema."""
    try:
        service = get_databricks_service()
        return service.list_tables(catalog_name, schema_name)
    except Exception as e:
        logger.error(f"Failed to list tables: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.get(
    "/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}/columns",
    response_model=TableColumnsOut,
    operation_id="getTableColumns"
)
def get_table_columns(catalog_name: str, schema_name: str, table_name: str):
    """Get table information including columns."""
    try:
        service = get_databricks_service()
        return service.get_table_columns(catalog_name, schema_name, table_name)
    except Exception as e:
        logger.error(f"Failed to get table columns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Sample Data Generation ==============

@api.post(
    "/generate-sample-data",
    response_model=GenerateSampleDataResponse,
    operation_id="generateSampleData"
)
def generate_sample_data(request: GenerateSampleDataRequest):
    """Generate sample workforce optimization data."""
    try:
        import random
        import re
        
        service = get_databricks_service()
        
        # Ensure schema exists
        service.create_schema_if_not_exists(request.catalog, request.schema_name)

        # Build a SQL-safe table suffix from the dataset label (e.g. "small", "large")
        # so each generated dataset gets its own set of tables.
        if request.dataset_label:
            safe_label = re.sub(r"[^a-z0-9]", "_", request.dataset_label.lower()).strip("_")
            suffix = f"_{safe_label}" if safe_label else ""
        else:
            suffix = ""
        
        # Generate worker names
        first_names = ["Alice", "Bob", "Carol", "Dan", "Eve", "Frank", "Grace", "Henry", "Ivy", "Jack",
                       "Kate", "Leo", "Maya", "Nick", "Olivia", "Paul", "Quinn", "Rose", "Sam", "Tina"]
        workers = random.sample(first_names, min(request.num_workers, len(first_names)))
        if request.num_workers > len(first_names):
            workers.extend([f"Worker{i}" for i in range(len(first_names), request.num_workers)])
        
        # Generate shifts
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        shifts = []
        shift_num = 1
        while len(shifts) < request.num_shifts:
            for day in days:
                if len(shifts) >= request.num_shifts:
                    break
                shifts.append(f"{day}{shift_num}")
            shift_num += 1
        
        # Create workers table
        workers_table = f"{request.catalog}.{request.schema_name}.workers{suffix}"
        workers_data = []
        for worker in workers:
            pay = round(random.uniform(request.min_pay, request.max_pay), 2)
            workers_data.append(f"('{worker}', {pay})")
        
        # Execute CREATE and INSERT as separate statements
        service.execute_sql(f"""
            CREATE OR REPLACE TABLE {workers_table} (
                worker_name STRING,
                pay_rate DOUBLE
            ) USING DELTA
        """)
        service.execute_sql(f"INSERT INTO {workers_table} VALUES {', '.join(workers_data)}")
        
        # Create shifts table
        shifts_table = f"{request.catalog}.{request.schema_name}.shifts{suffix}"
        shifts_data = []
        for shift in shifts:
            required = random.randint(2, max(2, request.num_workers // 3))
            shifts_data.append(f"('{shift}', {required})")
        
        service.execute_sql(f"""
            CREATE OR REPLACE TABLE {shifts_table} (
                shift_name STRING,
                required_workers INT
            ) USING DELTA
        """)
        service.execute_sql(f"INSERT INTO {shifts_table} VALUES {', '.join(shifts_data)}")
        
        # Create availability table (warehouse-side generation for scalability)
        availability_table = f"{request.catalog}.{request.schema_name}.availability{suffix}"
        # Avoid building huge VALUES payloads in the app process.
        # Generate availability directly in SQL by sampling worker/shift pairs.
        service.execute_sql(f"""
            CREATE OR REPLACE TABLE {availability_table} AS
            SELECT
                w.worker_name,
                s.shift_name
            FROM {workers_table} w
            CROSS JOIN {shifts_table} s
            WHERE rand() < {request.avg_availability_pct}
        """)

        availability_count_result = service.execute_sql(
            f"SELECT COUNT(*) AS num_availability_records FROM {availability_table}"
        )
        num_availability_records = (
            int(availability_count_result[0]["num_availability_records"])
            if availability_count_result
            else 0
        )
        
        return GenerateSampleDataResponse(
            dataset_label=request.dataset_label,
            workers_table=workers_table,
            shifts_table=shifts_table,
            availability_table=availability_table,
            num_workers=len(workers),
            num_shifts=len(shifts),
            num_availability_records=num_availability_records
        )
        
    except Exception as e:
        logger.error(f"Failed to generate sample data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Optimization Configurations ==============

@api.post(
    "/configs",
    response_model=OptimizationConfigOut,
    operation_id="createConfig"
)
def create_config(
    config: OptimizationConfigCreate,
    current_user: Annotated[Optional[str], Depends(get_current_user_email)] = None,
):
    """Create a new optimization configuration."""
    try:
        service = get_optimization_service()
        return service.create_config(config, owner_user=current_user)
    except Exception as e:
        logger.error(f"Failed to create config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.get(
    "/configs",
    response_model=list[OptimizationConfigOut],
    operation_id="listConfigs"
)
def list_configs(
    current_user: Annotated[Optional[str], Depends(get_current_user_email)] = None,
):
    """List all optimization configurations."""
    try:
        service = get_optimization_service()
        return service.list_configs(owner_user=current_user)
    except Exception as e:
        logger.error(f"Failed to list configs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.get(
    "/configs/{config_id}",
    response_model=OptimizationConfigOut,
    operation_id="getConfig"
)
def get_config(config_id: str):
    """Get an optimization configuration by ID."""
    try:
        service = get_optimization_service()
        config = service.get_config(config_id)
        if not config:
            raise HTTPException(status_code=404, detail="Configuration not found")
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.put(
    "/configs/{config_id}",
    response_model=OptimizationConfigOut,
    operation_id="updateConfig"
)
def update_config(config_id: str, config: OptimizationConfigCreate):
    """Update an optimization configuration."""
    try:
        service = get_optimization_service()
        updated = service.update_config(config_id, config)
        if not updated:
            raise HTTPException(status_code=404, detail="Configuration not found")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.delete(
    "/configs/{config_id}",
    operation_id="deleteConfig"
)
def delete_config(config_id: str):
    """Delete an optimization configuration."""
    try:
        service = get_optimization_service()
        deleted = service.delete_config(config_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Configuration not found")
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Optimization Runs ==============

@api.post(
    "/runs",
    response_model=OptimizationRunOut,
    operation_id="createRun"
)
def create_run(
    run_create: OptimizationRunCreate,
    current_user: Annotated[Optional[str], Depends(get_current_user_email)] = None,
):
    """Create and submit a new optimization run."""
    try:
        service = get_optimization_service()
        return service.create_run(run_create, owner_user=current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.get(
    "/runs",
    response_model=list[OptimizationRunOut],
    operation_id="listRuns"
)
def list_runs(
    config_id: Optional[str] = None,
    current_user: Annotated[Optional[str], Depends(get_current_user_email)] = None,
):
    """List all optimization runs, optionally filtered by config."""
    try:
        service = get_optimization_service()
        return service.list_runs(config_id, owner_user=current_user)
    except Exception as e:
        logger.error(f"Failed to list runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.get(
    "/runs/{run_id}",
    response_model=OptimizationRunOut,
    operation_id="getRun"
)
def get_run(run_id: str):
    """Get an optimization run by ID."""
    try:
        service = get_optimization_service()
        run = service.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return run
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.post(
    "/runs/{run_id}/cancel",
    operation_id="cancelRun"
)
def cancel_run(run_id: str):
    """Cancel a running optimization run."""
    try:
        service = get_optimization_service()
        cancelled = service.cancel_run(run_id)
        if not cancelled:
            raise HTTPException(status_code=400, detail="Run not found or not running")
        return {"status": "cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.post(
    "/runs/{run_id}/refresh",
    response_model=OptimizationRunOut,
    operation_id="refreshRunStatus"
)
def refresh_run_status(run_id: str):
    """Force refresh run status from Databricks."""
    try:
        service = get_optimization_service()
        run = service.refresh_run_status(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return run
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refresh run status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Optimization Results ==============

@api.get(
    "/runs/{run_id}/results",
    response_model=OptimizationResultOut,
    operation_id="getRunResults"
)
def get_run_results(run_id: str):
    """Get optimization results for a run."""
    try:
        service = get_optimization_service()
        results = service.get_results(run_id)
        if not results:
            raise HTTPException(status_code=404, detail="Run not found")
        return results
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.get(
    "/runs/{run_id}/export",
    operation_id="exportRunResults"
)
def export_run_results(run_id: str, format: ExportFormat = ExportFormat.CSV):
    """Export optimization results as CSV or JSON."""
    try:
        service = get_optimization_service()
        results = service.get_results(run_id)
        if not results:
            raise HTTPException(status_code=404, detail="Run not found")
        
        if format == ExportFormat.CSV:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["worker_name", "shift_name", "cost"])
            for assignment in results.assignments:
                writer.writerow([assignment.worker_name, assignment.shift_name, assignment.cost])
            
            output.seek(0)
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=optimization_results_{run_id}.csv"}
            )
        else:
            return Response(
                content=json.dumps(results.model_dump(), default=str, indent=2),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename=optimization_results_{run_id}.json"}
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.post(
    "/runs/{run_id}/save-to-table",
    operation_id="saveResultsToTable"
)
def save_results_to_table(
    run_id: str,
    catalog: str,
    schema_name: str,
    table_name: str
):
    """Copy optimization results to a new Delta table.
    
    Results are already saved by the notebook to the unified results table.
    This endpoint copies them to a user-specified location.
    """
    try:
        service = get_optimization_service()
        results = service.get_results(run_id)
        if not results:
            raise HTTPException(status_code=404, detail="Run not found")
        
        db_service = get_databricks_service()
        
        # Ensure schema exists
        db_service.create_schema_if_not_exists(catalog, schema_name)
        
        # Create and populate table
        full_table = f"{catalog}.{schema_name}.{table_name}"
        
        if results.assignments:
            values = []
            for a in results.assignments:
                values.append(f"('{run_id}', '{a.worker_name}', '{a.shift_name}', {a.cost})")
            
            db_service.execute_sql(f"""
                CREATE OR REPLACE TABLE {full_table} (
                    run_id STRING,
                    worker_name STRING,
                    shift_name STRING,
                    cost DOUBLE
                ) USING DELTA
            """)
            db_service.execute_sql(f"INSERT INTO {full_table} VALUES {', '.join(values)}")
        else:
            db_service.execute_sql(f"""
                CREATE OR REPLACE TABLE {full_table} (
                    run_id STRING,
                    worker_name STRING,
                    shift_name STRING,
                    cost DOUBLE
                ) USING DELTA
            """)
        
        return {"status": "saved", "table": full_table, "rows": len(results.assignments)}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save results to table: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Scalable / Paginated Results ==============

def _clamp_page(limit: int, offset: int) -> tuple[int, int]:
    """Clamp pagination params to sane ranges."""
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    offset = max(0, offset)
    return limit, offset


@api.get(
    "/runs/{run_id}/results/summary",
    response_model=RunResultsSummaryOut,
    operation_id="getRunResultsSummary",
)
def get_run_results_summary(run_id: str):
    """Get lightweight KPI summary for a run (no row-level data)."""
    try:
        service = get_optimization_service()
        summary = service.get_results_summary(run_id)
        if not summary:
            raise HTTPException(status_code=404, detail="Run not found")
        return summary
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get results summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.get(
    "/runs/{run_id}/results/assignments",
    response_model=PagedAssignmentsOut,
    operation_id="getPagedAssignments",
)
def get_paged_assignments(
    run_id: str,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
    sort: str = "worker_name",
    sort_dir: str = "asc",
):
    """Get paginated assignment rows."""
    limit, offset = _clamp_page(limit, offset)
    try:
        service = get_optimization_service()
        result = service.get_paged_assignments(
            run_id, limit=limit, offset=offset, sort=sort, sort_dir=sort_dir,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get paged assignments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.get(
    "/runs/{run_id}/results/by-shift",
    response_model=PagedShiftAggregatesOut,
    operation_id="getShiftAggregates",
)
def get_shift_aggregates(
    run_id: str,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
    sort: str = "name",
    sort_dir: str = "asc",
):
    """Get paginated shift-level aggregates."""
    limit, offset = _clamp_page(limit, offset)
    try:
        service = get_optimization_service()
        result = service.get_shift_aggregates(
            run_id, limit=limit, offset=offset, sort=sort, sort_dir=sort_dir,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get shift aggregates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.get(
    "/runs/{run_id}/results/by-shift/{shift_name}/assignments",
    response_model=PagedAssignmentsOut,
    operation_id="getShiftAssignments",
)
def get_shift_assignments(
    run_id: str,
    shift_name: str,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
):
    """Get paginated assignments for a single shift."""
    limit, offset = _clamp_page(limit, offset)
    try:
        service = get_optimization_service()
        result = service.get_paged_assignments(
            run_id, limit=limit, offset=offset,
            sort="worker_name", sort_dir="asc",
            shift_name=shift_name,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get shift assignments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.get(
    "/runs/{run_id}/results/by-worker",
    response_model=PagedWorkerAggregatesOut,
    operation_id="getWorkerAggregates",
)
def get_worker_aggregates(
    run_id: str,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
    sort: str = "name",
    sort_dir: str = "asc",
):
    """Get paginated worker-level aggregates."""
    limit, offset = _clamp_page(limit, offset)
    try:
        service = get_optimization_service()
        result = service.get_worker_aggregates(
            run_id, limit=limit, offset=offset, sort=sort, sort_dir=sort_dir,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get worker aggregates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.get(
    "/runs/{run_id}/results/by-worker/{worker_name}/assignments",
    response_model=PagedAssignmentsOut,
    operation_id="getWorkerAssignments",
)
def get_worker_assignments(
    run_id: str,
    worker_name: str,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
):
    """Get paginated assignments for a single worker."""
    limit, offset = _clamp_page(limit, offset)
    try:
        service = get_optimization_service()
        result = service.get_paged_assignments(
            run_id, limit=limit, offset=offset,
            sort="shift_name", sort_dir="asc",
            worker_name=worker_name,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get worker assignments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api.get(
    "/runs/{run_id}/graph/focused",
    response_model=GraphSubsetOut,
    operation_id="getFocusedGraph",
)
def get_focused_graph(
    run_id: str,
    shift_name: Optional[str] = None,
    worker_name: Optional[str] = None,
    limit: int = 200,
):
    """Get a bounded subgraph for the graph explorer.

    Without focus params, returns the full graph if it's small enough,
    otherwise returns metadata only so the UI can prompt for focus selection.
    """
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    try:
        service = get_optimization_service()
        result = service.get_focused_graph(
            run_id, shift_name=shift_name, worker_name=worker_name, limit=limit,
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get focused graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))
