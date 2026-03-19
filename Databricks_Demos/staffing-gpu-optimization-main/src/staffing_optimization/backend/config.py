from importlib import resources
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from pydantic import Field, field_validator
from dotenv import load_dotenv
from .._metadata import app_name, app_slug, api_prefix
from typing import ClassVar, Optional

# project root is the parent of the src folder
project_root = Path(__file__).parent.parent.parent.parent
env_file = project_root / ".env"

if env_file.exists():
    load_dotenv(dotenv_path=env_file)


class AppConfig(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=env_file, env_prefix=f"{app_slug.upper()}_", extra="ignore"
    )
    app_name: str = Field(default=app_name)
    api_prefix: str = Field(default=api_prefix)
    debug: bool = Field(default=False)
    
    # PostgreSQL / Lakebase configuration
    postgres_host: Optional[str] = Field(default=None)
    postgres_port: str = Field(default="5432")
    postgres_database: Optional[str] = Field(default=None)
    postgres_user: Optional[str] = Field(default=None)
    postgres_password: Optional[str] = Field(default=None)
    postgres_sslmode: str = Field(default="require")
    
    # Databricks configuration
    databricks_host: Optional[str] = Field(default=None)
    databricks_token: Optional[str] = Field(default=None)
    
    # Optimization job configuration
    gpu_job_cluster_key: str = Field(default="gpu_optimization_cluster")
    # Only used when creating per-config jobs (local dev fallback). In deployed mode, use shared bundle job.
    optimization_notebook_path: Optional[str] = Field(default=None)
    default_catalog: str = Field(default="demos")
    default_schema: str = Field(default="staffing_optimization")
    # Bundle-deployed Databricks job ID for optimization runs.
    # Set via env var STAFFING_OPTIMIZATION_DATABRICKS_JOB_ID.
    databricks_job_id: Optional[int] = Field(default=None)

    # Lakebase configuration (used for app state storage)
    lakebase_project: str = Field(default="staffing-optimization")
    # Branch display-name or UID. If None, the default branch is used.
    lakebase_branch: Optional[str] = Field(default=None)
    # Optional endpoint selector. If None, uses first available endpoint.
    lakebase_endpoint_host: Optional[str] = Field(default=None)
    lakebase_database: str = Field(default="databricks_postgres")
    lakebase_sslmode: str = Field(default="require")
    lakebase_schema: str = Field(default="staffing_optimization")

    @field_validator("databricks_job_id", mode="before")
    @classmethod
    def _empty_string_to_none_for_optional_int(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @property
    def static_assets_path(self) -> Path:
        return Path(str(resources.files(app_slug))).joinpath("__dist__")


conf = AppConfig()
