"""
Databricks workspace service using the Python SDK.
Provides methods for interacting with Unity Catalog, Jobs, and SQL.
"""
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import CatalogInfo as SDKCatalogInfo
from databricks.sdk.service.jobs import NotebookTask, SubmitTask
from typing import Optional
import os

from .config import conf
from .logger import logger
from .models import CatalogInfo, SchemaInfo, TableInfo, ColumnInfo, TableColumnsOut


def get_workspace_client() -> WorkspaceClient:
    """
    Get a Databricks WorkspaceClient.
    When running in a Databricks App, authentication is automatic.
    For local development, uses DATABRICKS_HOST and DATABRICKS_TOKEN env vars.
    """
    # WorkspaceClient will automatically pick up credentials from:
    # 1. Environment variables (DATABRICKS_HOST, DATABRICKS_TOKEN)
    # 2. Databricks CLI config (~/.databrickscfg)
    # 3. Azure/GCP/AWS credential providers
    return WorkspaceClient()


class DatabricksService:
    """Service for interacting with Databricks workspace."""
    
    def __init__(self):
        self._client: Optional[WorkspaceClient] = None
    
    @property
    def client(self) -> WorkspaceClient:
        if self._client is None:
            self._client = get_workspace_client()
        return self._client
    
    # ============== Unity Catalog Operations ==============
    
    def list_catalogs(self) -> list[CatalogInfo]:
        """List all accessible catalogs."""
        try:
            catalogs = self.client.catalogs.list()
            return [
                CatalogInfo(
                    name=c.name,
                    comment=c.comment
                )
                for c in catalogs
                if c.name is not None
            ]
        except Exception as e:
            logger.error(f"Failed to list catalogs: {e}")
            raise
    
    def list_schemas(self, catalog_name: str) -> list[SchemaInfo]:
        """List all schemas in a catalog."""
        try:
            schemas = self.client.schemas.list(catalog_name=catalog_name)
            return [
                SchemaInfo(
                    name=s.name,
                    catalog_name=catalog_name,
                    comment=s.comment
                )
                for s in schemas
                if s.name is not None
            ]
        except Exception as e:
            logger.error(f"Failed to list schemas in {catalog_name}: {e}")
            raise
    
    def list_tables(self, catalog_name: str, schema_name: str) -> list[TableInfo]:
        """List all tables in a schema."""
        try:
            tables = self.client.tables.list(
                catalog_name=catalog_name,
                schema_name=schema_name
            )
            return [
                TableInfo(
                    name=t.name,
                    catalog_name=catalog_name,
                    schema_name=schema_name,
                    table_type=str(t.table_type) if t.table_type else "UNKNOWN",
                    comment=t.comment
                )
                for t in tables
                if t.name is not None
            ]
        except Exception as e:
            logger.error(f"Failed to list tables in {catalog_name}.{schema_name}: {e}")
            raise
    
    def get_table_columns(self, catalog_name: str, schema_name: str, table_name: str) -> TableColumnsOut:
        """Get table info with columns."""
        try:
            full_name = f"{catalog_name}.{schema_name}.{table_name}"
            table = self.client.tables.get(full_name)
            
            columns = []
            if table.columns:
                columns = [
                    ColumnInfo(
                        name=c.name,
                        type_name=str(c.type_name) if c.type_name else "UNKNOWN",
                        comment=c.comment
                    )
                    for c in table.columns
                    if c.name is not None
                ]
            
            table_info = TableInfo(
                name=table.name or table_name,
                catalog_name=catalog_name,
                schema_name=schema_name,
                table_type=str(table.table_type) if table.table_type else "UNKNOWN",
                comment=table.comment
            )
            
            return TableColumnsOut(table=table_info, columns=columns)
        except Exception as e:
            logger.error(f"Failed to get columns for {catalog_name}.{schema_name}.{table_name}: {e}")
            raise
    
    def create_schema_if_not_exists(self, catalog_name: str, schema_name: str) -> None:
        """Create a schema if it doesn't exist.

        Checks for existence first so we don't need CREATE SCHEMA privilege
        when the schema is already present.
        """
        try:
            self.client.schemas.get(full_name=f"{catalog_name}.{schema_name}")
            logger.info(f"Schema {catalog_name}.{schema_name} already exists")
            return
        except Exception:
            pass  # Schema doesn't exist (or not accessible) — try to create it

        try:
            self.client.schemas.create(
                name=schema_name,
                catalog_name=catalog_name,
                comment="Created by Staffing Optimization app"
            )
            logger.info(f"Created schema {catalog_name}.{schema_name}")
        except Exception as e:
            if "SCHEMA_ALREADY_EXISTS" in str(e) or "already exists" in str(e).lower():
                logger.info(f"Schema {catalog_name}.{schema_name} already exists")
            else:
                raise
    
    # ============== SQL Warehouse Operations ==============
    
    def execute_sql(self, sql: str, catalog: str = None, schema: str = None) -> list[dict]:
        """Execute SQL statement and return results."""
        try:
            # Use Statement Execution API
            statement = self.client.statement_execution.execute_statement(
                statement=sql,
                warehouse_id=self._get_warehouse_id(),
                catalog=catalog or conf.default_catalog,
                schema=schema or conf.default_schema,
                wait_timeout="30s"
            )
            
            if statement.result and statement.result.data_array:
                # Get column names from manifest
                columns = []
                if statement.manifest and statement.manifest.schema and statement.manifest.schema.columns:
                    columns = [c.name for c in statement.manifest.schema.columns]
                
                # Convert to list of dicts
                results = []
                for row in statement.result.data_array:
                    if columns:
                        results.append(dict(zip(columns, row)))
                    else:
                        results.append({"_row": row})
                return results
            return []
        except Exception as e:
            logger.error(f"Failed to execute SQL: {e}")
            raise
    
    def _get_warehouse_id(self) -> str:
        """Get SQL warehouse ID from env var or first available warehouse."""
        # Check for environment variable first
        warehouse_id = os.environ.get("DATABRICKS_SQL_WAREHOUSE_ID")
        if warehouse_id:
            logger.debug(f"Using warehouse ID from env: {warehouse_id}")
            return warehouse_id
        
        # Fall back to auto-discovery
        warehouses = list(self.client.warehouses.list())
        if not warehouses:
            raise ValueError("No SQL warehouses available")
        
        # Prefer running warehouses
        for wh in warehouses:
            if wh.state and wh.state.value == "RUNNING":
                return wh.id
        
        # Return first warehouse
        return warehouses[0].id
    
    # ============== Jobs Operations ==============
    
    def create_optimization_job(
        self,
        config_id: str,
        config_dict: dict,
        job_name: str = None,
        notebook_path: str = None,
        results_table: str = None
    ) -> int:
        """Create a persistent Databricks job for a config (1:1 with config).
        
        Args:
            config_id: Our internal config ID
            config_dict: Configuration parameters for the optimization
            job_name: Name for the Databricks job
            notebook_path: Path to the optimization notebook
            results_table: Unity Catalog table for results
        
        Returns:
            Databricks job_id (persistent, reused for all runs)
        """
        import json
        from databricks.sdk.service.jobs import (
            Task, NotebookTask as JobNotebookTask, JobEnvironment
        )
        from databricks.sdk.service.compute import Environment
        
        notebook_path = notebook_path or conf.optimization_notebook_path
        if not notebook_path:
            raise ValueError(
                "optimization_notebook_path is required for per-config job creation. "
                "Use the shared bundle job (STAFFING_OPTIMIZATION_DATABRICKS_JOB_ID) instead."
            )
        job_name = job_name or f"Optimization: {config_id[:8]}"
        results_table = results_table or f"{conf.default_catalog}.{conf.default_schema}.optimization_results"
        
        try:
            # Create a persistent job with serverless GPU compute
            # Note: run_id and results_table are passed at run time via run_now
            created_job = self.client.jobs.create(
                name=job_name,
                tasks=[
                    Task(
                        task_key="run_optimization",
                        notebook_task=JobNotebookTask(
                            notebook_path=notebook_path,
                            # Base parameters are config-level, run-specific params added at run time
                            base_parameters={
                                "config_json": json.dumps(config_dict),
                            }
                        ),
                        environment_key="cuopt_gpu_env"
                    )
                ],
                environments=[
                    JobEnvironment(
                        environment_key="cuopt_gpu_env",
                        spec=Environment(
                            client="4",  # GPU environment version 4
                            dependencies=[
                                "cuopt-server-cu12",
                                "cuopt-sh-client",
                                "cuopt-cu12==25.8.*"
                            ]
                        )
                    )
                ],
                max_concurrent_runs=1
            )
            
            logger.info(f"Created persistent Databricks job {created_job.job_id} for config {config_id}")
            return created_job.job_id
            
        except Exception as e:
            logger.error(f"Failed to create optimization job for config {config_id}: {e}")
            raise
    
    def update_optimization_job(
        self,
        databricks_job_id: int,
        config_dict: dict,
        job_name: str = None
    ) -> None:
        """Update an existing Databricks job with new config parameters.
        
        Called when a config is updated to keep the job in sync.
        """
        import json
        from databricks.sdk.service.jobs import JobSettings, Task, NotebookTask as JobNotebookTask
        
        try:
            # Get current job to preserve settings
            current_job = self.client.jobs.get(job_id=databricks_job_id)
            
            # Update the job settings with new config
            notebook_path = conf.optimization_notebook_path
            if current_job.settings and current_job.settings.tasks:
                task = current_job.settings.tasks[0]
                if task.notebook_task:
                    notebook_path = task.notebook_task.notebook_path or notebook_path
            
            self.client.jobs.update(
                job_id=databricks_job_id,
                new_settings=JobSettings(
                    name=job_name or current_job.settings.name,
                    tasks=[
                        Task(
                            task_key="run_optimization",
                            notebook_task=JobNotebookTask(
                                notebook_path=notebook_path,
                                base_parameters={
                                    "config_json": json.dumps(config_dict),
                                }
                            ),
                            environment_key="cuopt_gpu_env"
                        )
                    ]
                )
            )
            
            logger.info(f"Updated Databricks job {databricks_job_id}")
            
        except Exception as e:
            logger.error(f"Failed to update job {databricks_job_id}: {e}")
            raise
    
    def run_optimization_job(
        self,
        databricks_job_id: int,
        run_id: str,
        results_table: str,
        config_dict: dict | None = None,
        owner_user: str | None = None,
    ) -> int:
        """Run an optimization job with run-specific parameters.

        When using the shared bundle job, *config_dict* is passed as
        ``config_json`` so the notebook receives the correct config
        for this particular run.

        Returns:
            Databricks run_id
        """
        import json
        try:
            params: dict[str, str] = {
                "run_id": run_id,
                "results_table": results_table,
            }
            if config_dict:
                params["config_json"] = json.dumps(config_dict)
            if owner_user:
                params["owner_user"] = owner_user

            waiter = self.client.jobs.run_now(
                job_id=databricks_job_id,
                job_parameters=params,
            )
            logger.info(f"Started run {run_id} on job {databricks_job_id}, Databricks run_id: {waiter.run_id}")
            return waiter.run_id
        except Exception as e:
            logger.error(f"Failed to run job {databricks_job_id} for run {run_id}: {e}")
            raise
    
    def get_run_output(self, run_id: int) -> dict:
        """Get the notebook output from a completed run."""
        try:
            # Get the run details first
            run = self.client.jobs.get_run(run_id=run_id)
            if run.tasks and len(run.tasks) > 0:
                task_run_id = run.tasks[0].run_id
                output = self.client.jobs.get_run_output(run_id=task_run_id)
                if output.notebook_output and output.notebook_output.result:
                    import json
                    return json.loads(output.notebook_output.result)
            return None
        except Exception as e:
            logger.error(f"Failed to get run output for {run_id}: {e}")
            return None
    
    def delete_job(self, databricks_job_id: int) -> None:
        """Delete a Databricks job."""
        try:
            self.client.jobs.delete(job_id=databricks_job_id)
            logger.info(f"Deleted Databricks job {databricks_job_id}")
        except Exception as e:
            err = str(e).lower()
            if "does not exist" in err or "resource_does_not_exist" in err:
                logger.warning(f"Databricks job {databricks_job_id} already missing; skipping delete")
            else:
                logger.error(f"Failed to delete job {databricks_job_id}: {e}")
    
    def get_run_status(self, run_id: int) -> dict:
        """Get the detailed status of a job run.

        Falls back to the first task's ``result_state`` when the run-level
        ``result_state`` is absent (which can happen transiently for
        single-task jobs even after the lifecycle reaches TERMINATED).
        """
        try:
            run = self.client.jobs.get_run(run_id=run_id)
            
            # Extract task-level errors if available
            task_errors = []
            first_task_result_state = None
            if run.tasks:
                for task in run.tasks:
                    if task.state and task.state.result_state:
                        if first_task_result_state is None:
                            first_task_result_state = task.state.result_state.value
                        if task.state.result_state.value in ["FAILED", "TIMEDOUT", "CANCELED"]:
                            task_errors.append({
                                "task_key": task.task_key,
                                "result_state": task.state.result_state.value,
                                "state_message": task.state.state_message or "No message"
                            })
            
            # Determine result_state: prefer run-level, fall back to first task
            run_result_state = None
            if run.state and run.state.result_state:
                run_result_state = run.state.result_state.value
            elif first_task_result_state is not None:
                run_result_state = first_task_result_state
                logger.info(
                    f"Run {run_id}: run-level result_state is None, "
                    f"falling back to first task result_state={first_task_result_state}"
                )

            # Build comprehensive error message
            error_message = None
            if run.state and run.state.state_message:
                error_message = run.state.state_message
            if task_errors:
                task_error_str = "; ".join([
                    f"{e['task_key']}: {e['state_message']}" for e in task_errors
                ])
                error_message = f"{error_message or 'Task failures'}: {task_error_str}"
            
            return {
                "run_id": run.run_id,
                "state": run.state.life_cycle_state.value if run.state and run.state.life_cycle_state else None,
                "result_state": run_result_state,
                "state_message": error_message,
                "run_page_url": run.run_page_url,
                "task_errors": task_errors
            }
        except Exception as e:
            logger.error(f"Failed to get run status for {run_id}: {e}")
            raise
    
    def cancel_run(self, run_id: int) -> None:
        """Cancel a running job."""
        try:
            self.client.jobs.cancel_run(run_id=run_id)
            logger.info(f"Cancelled run {run_id}")
        except Exception as e:
            logger.error(f"Failed to cancel run {run_id}: {e}")
            raise


# Singleton instance
_databricks_service: Optional[DatabricksService] = None


def get_databricks_service() -> DatabricksService:
    """Get the singleton DatabricksService instance."""
    global _databricks_service
    if _databricks_service is None:
        _databricks_service = DatabricksService()
    return _databricks_service
