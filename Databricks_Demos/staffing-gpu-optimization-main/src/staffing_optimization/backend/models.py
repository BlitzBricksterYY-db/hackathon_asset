from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum
from .. import __version__


class VersionOut(BaseModel):
    version: str

    @classmethod
    def from_metadata(cls):
        return cls(version=__version__)


class WorkspaceInfoOut(BaseModel):
    """Workspace metadata exposed to the frontend."""
    host: Optional[str] = None
    databricks_job_id: Optional[int] = None


# ============== Workforce Optimization Models ==============

class RunStatus(str, Enum):
    """Status of an optimization run."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WorkerInput(BaseModel):
    """Input model for a single worker"""
    name: str
    pay_rate: float
    available_shifts: list[str]


class ShiftInput(BaseModel):
    """Input model for a single shift requirement"""
    name: str
    required_workers: int


class OptimizationConfig(BaseModel):
    """Configuration for workforce optimization (1:1 with Databricks job)."""
    name: str
    description: Optional[str] = None
    source_catalog: str
    source_schema: str
    workers_table: str
    shifts_table: str
    availability_table: str
    worker_name_col: str = "worker_name"
    worker_pay_col: str = "pay_rate"
    shift_name_col: str = "shift_name"
    shift_required_col: str = "required_workers"
    availability_worker_col: str = "worker_name"
    availability_shift_col: str = "shift_name"
    max_shifts_per_worker: Optional[int] = None
    time_limit_seconds: float = 60.0
    target_catalog: Optional[str] = None
    target_schema: Optional[str] = None
    results_table: Optional[str] = None


class OptimizationConfigCreate(OptimizationConfig):
    """Model for creating a new optimization config"""
    pass


class OptimizationConfigOut(OptimizationConfig):
    """Model for returning an optimization config"""
    id: str
    owner_user: Optional[str] = None
    databricks_job_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class OptimizationRunCreate(BaseModel):
    """Model for creating a new optimization run."""
    config_id: str
    run_name: Optional[str] = None


class OptimizationRunOut(BaseModel):
    """Model for returning an optimization run."""
    id: str
    config_id: str
    run_name: Optional[str] = None
    owner_user: Optional[str] = None
    status: RunStatus
    databricks_run_id: Optional[int] = None
    total_cost: Optional[float] = None
    solve_time_seconds: Optional[float] = None
    num_workers_assigned: Optional[int] = None
    num_shifts_covered: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class AssignmentResult(BaseModel):
    """A single worker-shift assignment in the result"""
    worker_name: str
    shift_name: str
    cost: float


class OptimizationResultOut(BaseModel):
    """Full optimization result for a run (legacy, kept for small datasets)."""
    run_id: str
    status: RunStatus
    total_cost: Optional[float] = None
    solve_time_seconds: Optional[float] = None
    assignments: list[AssignmentResult] = []
    worker_summary: dict[str, dict] = {}  # worker_name -> {shifts: [...], total_cost: ...}
    shift_summary: dict[str, dict] = {}   # shift_name -> {workers: [...], required: ..., assigned: ...}


# ============== Scalable / Paginated Results Models ==============

# Guardrail: max rows the legacy full-results endpoint will return
FULL_RESULTS_ROW_CAP = 5_000
# Threshold above which the graph UI should use focused mode instead of full render
GRAPH_ELEMENT_THRESHOLD = 2_000

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500

VALID_ASSIGNMENT_SORT_FIELDS = {"worker_name", "shift_name", "cost"}
VALID_AGGREGATE_SORT_FIELDS = {"name", "count", "total_cost"}


class RunResultsSummaryOut(BaseModel):
    """Lightweight summary of a completed run, no row-level data."""
    run_id: str
    status: RunStatus
    total_cost: Optional[float] = None
    solve_time_seconds: Optional[float] = None
    num_workers_assigned: Optional[int] = None
    num_shifts_covered: Optional[int] = None
    total_assignments: int = 0
    avg_cost_per_assignment: Optional[float] = None
    min_assignment_cost: Optional[float] = None
    max_assignment_cost: Optional[float] = None


class PaginationMeta(BaseModel):
    """Standard pagination metadata."""
    offset: int
    limit: int
    total: int
    has_more: bool


class PagedAssignmentsOut(BaseModel):
    """Paginated list of individual assignments."""
    run_id: str
    assignments: list[AssignmentResult] = []
    pagination: PaginationMeta


class ShiftAggregateOut(BaseModel):
    """One row in the by-shift aggregate view."""
    shift_name: str
    assigned_count: int
    total_cost: float


class PagedShiftAggregatesOut(BaseModel):
    """Paginated list of shift aggregates."""
    run_id: str
    shifts: list[ShiftAggregateOut] = []
    pagination: PaginationMeta


class WorkerAggregateOut(BaseModel):
    """One row in the by-worker aggregate view."""
    worker_name: str
    shift_count: int
    total_cost: float


class PagedWorkerAggregatesOut(BaseModel):
    """Paginated list of worker aggregates."""
    run_id: str
    workers: list[WorkerAggregateOut] = []
    pagination: PaginationMeta


class GraphSubsetOut(BaseModel):
    """Bounded subgraph payload for the graph explorer."""
    run_id: str
    focus_entity: Optional[str] = None
    focus_type: Optional[str] = None  # "shift" | "worker" | None (full small graph)
    nodes: list[dict] = []
    edges: list[dict] = []
    total_nodes: int = 0
    total_edges: int = 0
    is_complete: bool = True  # False when graph was truncated / focused


# ============== Databricks Workspace Models ==============

class CatalogInfo(BaseModel):
    """Information about a Unity Catalog"""
    name: str
    comment: Optional[str] = None


class SchemaInfo(BaseModel):
    """Information about a schema"""
    name: str
    catalog_name: str
    comment: Optional[str] = None


class TableInfo(BaseModel):
    """Information about a table"""
    name: str
    catalog_name: str
    schema_name: str
    table_type: str
    comment: Optional[str] = None


class ColumnInfo(BaseModel):
    """Information about a table column"""
    name: str
    type_name: str
    comment: Optional[str] = None


class TableColumnsOut(BaseModel):
    """Table with its columns"""
    table: TableInfo
    columns: list[ColumnInfo]


# ============== Sample Data Models ==============

class GenerateSampleDataRequest(BaseModel):
    """Request to generate sample workforce data"""
    catalog: str
    schema_name: str = Field(alias="schema")
    num_workers: int = 10
    num_shifts: int = 14
    min_pay: float = 8.0
    max_pay: float = 15.0
    avg_availability_pct: float = 0.6
    dataset_label: Optional[str] = Field(
        default=None,
        description="Label such as 'small', 'medium', 'large'. "
        "Used as a table-name suffix so multiple datasets can coexist.",
    )


class GenerateSampleDataResponse(BaseModel):
    """Response after generating sample data"""
    dataset_label: Optional[str] = None
    workers_table: str
    shifts_table: str
    availability_table: str
    num_workers: int
    num_shifts: int
    num_availability_records: int


# ============== Run Submission Models ==============

class SubmitRunRequest(BaseModel):
    """Request to submit an optimization run."""
    config_id: str


class SubmitRunResponse(BaseModel):
    """Response after submitting a run."""
    run_id: str
    databricks_run_id: int
    status: RunStatus


# ============== Export Models ==============

class ExportFormat(str, Enum):
    CSV = "csv"
    JSON = "json"


class ExportResultsRequest(BaseModel):
    """Request to export optimization results."""
    run_id: str
    format: ExportFormat = ExportFormat.CSV
    save_to_table: bool = False
    target_catalog: Optional[str] = None
    target_schema: Optional[str] = None
    target_table: Optional[str] = None
