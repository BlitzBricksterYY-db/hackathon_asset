"""
Database models for Lakebase PostgreSQL storage.
Uses SQLModel for ORM with PostgreSQL backend.

Data Model:
- OptimizationConfigDB: Configuration for optimization (1:1 with Databricks job)
- OptimizationRunDB: Individual optimization run (many:1 with config)
- Results are stored in Unity Catalog Delta table (one unified table)
"""
from sqlmodel import SQLModel, Field

from .config import conf
from sqlalchemy import Column, BigInteger
from typing import Optional
from datetime import datetime
from uuid import uuid4
from .models import RunStatus


def generate_uuid() -> str:
    return str(uuid4())


class OptimizationConfigDB(SQLModel, table=True):
    """Stored optimization configuration with persistent Databricks job."""
    __tablename__ = "optimization_configs"
    __table_args__ = {"schema": conf.lakebase_schema}
    
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    
    # Source table configuration
    source_catalog: str
    source_schema: str
    workers_table: str
    shifts_table: str
    availability_table: str
    
    # Column mappings
    worker_name_col: str = "worker_name"
    worker_pay_col: str = "pay_rate"
    shift_name_col: str = "shift_name"
    shift_required_col: str = "required_workers"
    availability_worker_col: str = "worker_name"
    availability_shift_col: str = "shift_name"
    
    # Optimization parameters
    max_shifts_per_worker: Optional[int] = None
    time_limit_seconds: float = 60.0
    
    # Target table configuration (unified results table)
    target_catalog: Optional[str] = None
    target_schema: Optional[str] = None
    results_table: Optional[str] = None
    
    # Persistent Databricks job (created once per config, reused for all runs)
    databricks_job_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger))
    
    # Ownership (user email from Databricks OBO token)
    owner_user: Optional[str] = Field(default=None, index=True)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OptimizationRunDB(SQLModel, table=True):
    """Individual optimization run record (many runs per config)."""
    __tablename__ = "optimization_runs"
    __table_args__ = {"schema": conf.lakebase_schema}
    
    id: str = Field(default_factory=generate_uuid, primary_key=True)
    config_id: str = Field(foreign_key=f"{conf.lakebase_schema}.optimization_configs.id", index=True)
    run_name: Optional[str] = None
    status: str = Field(default=RunStatus.PENDING.value, index=True)
    
    # Databricks run tracking (run_id, not job_id - job is on config)
    databricks_run_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger))
    
    # Results summary (from notebook output)
    total_cost: Optional[float] = None
    solve_time_seconds: Optional[float] = None
    num_workers_assigned: Optional[int] = None
    num_shifts_covered: Optional[int] = None
    
    # Error handling
    error_message: Optional[str] = None
    
    # Ownership (user email from Databricks OBO token)
    owner_user: Optional[str] = Field(default=None, index=True)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
