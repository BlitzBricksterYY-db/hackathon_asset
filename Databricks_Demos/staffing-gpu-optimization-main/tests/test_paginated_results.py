"""Tests for the scalable / paginated results endpoints.

Covers:
- get_results_summary returns lightweight KPIs from SQL aggregate
- get_paged_assignments paginates with limit/offset and filters
- get_shift_aggregates returns SQL GROUP BY results
- get_worker_aggregates returns SQL GROUP BY results
- get_focused_graph returns bounded subgraph or fallback for large graphs
- Pagination metadata (total, has_more) is correct
- Sort field validation falls back to safe defaults
"""
from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest

from staffing_optimization.backend.models import (
    RunStatus,
    GRAPH_ELEMENT_THRESHOLD,
)
from staffing_optimization.backend.db_models import (
    OptimizationConfigDB,
    OptimizationRunDB,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run(
    *,
    status: str = RunStatus.COMPLETED.value,
    databricks_run_id: int | None = 12345,
    config_id: str = "cfg-1",
) -> OptimizationRunDB:
    run = OptimizationRunDB(
        id="run-1",
        config_id=config_id,
        run_name="test run",
        status=status,
        databricks_run_id=databricks_run_id,
        total_cost=500.0,
        solve_time_seconds=2.5,
        num_workers_assigned=10,
        num_shifts_covered=14,
        owner_user="tester@example.com",
    )
    run.created_at = datetime.utcnow()
    run.updated_at = datetime.utcnow()
    return run


def _make_config(config_id: str = "cfg-1") -> OptimizationConfigDB:
    cfg = OptimizationConfigDB(
        id=config_id,
        name="Test Config",
        source_catalog="main",
        source_schema="opt",
        workers_table="workers",
        shifts_table="shifts",
        availability_table="avail",
        target_catalog="main",
        target_schema="opt",
        results_table="optimization_results",
    )
    cfg.created_at = datetime.utcnow()
    cfg.updated_at = datetime.utcnow()
    return cfg


def _patch_session(mock_scope, run, config):
    """Wire up session_scope mock so session.get returns run/config."""
    session = MagicMock()

    def _get(model, pk):
        if model is OptimizationRunDB:
            return run
        if model is OptimizationConfigDB:
            return config
        return None

    session.get.side_effect = _get
    mock_scope.return_value.__enter__ = MagicMock(return_value=session)
    mock_scope.return_value.__exit__ = MagicMock(return_value=False)
    return session


# ---------------------------------------------------------------------------
# get_results_summary
# ---------------------------------------------------------------------------

class TestGetResultsSummary:

    @patch("staffing_optimization.backend.optimization_service.session_scope")
    @patch("staffing_optimization.backend.optimization_service.get_databricks_service")
    def test_returns_aggregated_kpis(self, mock_get_svc, mock_scope):
        from staffing_optimization.backend.optimization_service import OptimizationService

        run = _make_run()
        config = _make_config()
        _patch_session(mock_scope, run, config)

        mock_svc = MagicMock()
        mock_svc.execute_sql.return_value = [{
            "total_assignments": "120",
            "num_workers": "10",
            "num_shifts": "14",
            "total_cost": "500.0",
            "avg_cost": "4.17",
            "min_cost": "2.0",
            "max_cost": "8.5",
        }]
        mock_get_svc.return_value = mock_svc

        svc = OptimizationService()
        result = svc.get_results_summary("run-1")

        assert result is not None
        assert result.run_id == "run-1"
        assert result.total_assignments == 120
        assert result.num_workers_assigned == 10
        assert result.num_shifts_covered == 14
        assert result.avg_cost_per_assignment == pytest.approx(4.17)

    @patch("staffing_optimization.backend.optimization_service.session_scope")
    @patch("staffing_optimization.backend.optimization_service.get_databricks_service")
    def test_non_completed_returns_run_metadata(self, mock_get_svc, mock_scope):
        from staffing_optimization.backend.optimization_service import OptimizationService

        run = _make_run(status=RunStatus.RUNNING.value)
        config = _make_config()
        _patch_session(mock_scope, run, config)

        svc = OptimizationService()
        result = svc.get_results_summary("run-1")

        assert result is not None
        assert result.status == RunStatus.RUNNING
        assert result.total_assignments == 0
        mock_get_svc.return_value.execute_sql.assert_not_called()

    @patch("staffing_optimization.backend.optimization_service.session_scope")
    def test_unknown_run_returns_none(self, mock_scope):
        from staffing_optimization.backend.optimization_service import OptimizationService

        session = MagicMock()
        session.get.return_value = None
        mock_scope.return_value.__enter__ = MagicMock(return_value=session)
        mock_scope.return_value.__exit__ = MagicMock(return_value=False)

        svc = OptimizationService()
        assert svc.get_results_summary("nonexistent") is None


# ---------------------------------------------------------------------------
# get_paged_assignments
# ---------------------------------------------------------------------------

class TestGetPagedAssignments:

    @patch("staffing_optimization.backend.optimization_service.session_scope")
    @patch("staffing_optimization.backend.optimization_service.get_databricks_service")
    def test_basic_pagination(self, mock_get_svc, mock_scope):
        from staffing_optimization.backend.optimization_service import OptimizationService

        run = _make_run()
        config = _make_config()
        _patch_session(mock_scope, run, config)

        mock_svc = MagicMock()
        mock_svc.execute_sql.side_effect = [
            [{"cnt": "100"}],
            [
                {"worker_name": "Alice", "shift_name": "Mon1", "cost": "10.0"},
                {"worker_name": "Bob", "shift_name": "Tue1", "cost": "12.5"},
            ],
        ]
        mock_get_svc.return_value = mock_svc

        svc = OptimizationService()
        result = svc.get_paged_assignments("run-1", limit=2, offset=0)

        assert result is not None
        assert len(result.assignments) == 2
        assert result.pagination.total == 100
        assert result.pagination.has_more is True
        assert result.assignments[0].worker_name == "Alice"

    @patch("staffing_optimization.backend.optimization_service.session_scope")
    @patch("staffing_optimization.backend.optimization_service.get_databricks_service")
    def test_filter_by_shift(self, mock_get_svc, mock_scope):
        from staffing_optimization.backend.optimization_service import OptimizationService

        run = _make_run()
        config = _make_config()
        _patch_session(mock_scope, run, config)

        mock_svc = MagicMock()
        mock_svc.execute_sql.side_effect = [
            [{"cnt": "3"}],
            [
                {"worker_name": "Alice", "shift_name": "Mon1", "cost": "10.0"},
                {"worker_name": "Bob", "shift_name": "Mon1", "cost": "12.0"},
                {"worker_name": "Carol", "shift_name": "Mon1", "cost": "11.0"},
            ],
        ]
        mock_get_svc.return_value = mock_svc

        svc = OptimizationService()
        result = svc.get_paged_assignments("run-1", limit=50, offset=0, shift_name="Mon1")

        assert result is not None
        assert len(result.assignments) == 3
        assert result.pagination.total == 3
        assert result.pagination.has_more is False

        # Verify SQL includes shift_name filter
        count_sql = mock_svc.execute_sql.call_args_list[0][0][0]
        assert "shift_name = 'Mon1'" in count_sql

    @patch("staffing_optimization.backend.optimization_service.session_scope")
    @patch("staffing_optimization.backend.optimization_service.get_databricks_service")
    def test_invalid_sort_falls_back(self, mock_get_svc, mock_scope):
        from staffing_optimization.backend.optimization_service import OptimizationService

        run = _make_run()
        config = _make_config()
        _patch_session(mock_scope, run, config)

        mock_svc = MagicMock()
        mock_svc.execute_sql.side_effect = [
            [{"cnt": "0"}],
            [],
        ]
        mock_get_svc.return_value = mock_svc

        svc = OptimizationService()
        result = svc.get_paged_assignments("run-1", sort="DROP TABLE;--")

        assert result is not None
        data_sql = mock_svc.execute_sql.call_args_list[1][0][0]
        assert "worker_name ASC" in data_sql


# ---------------------------------------------------------------------------
# get_shift_aggregates
# ---------------------------------------------------------------------------

class TestGetShiftAggregates:

    @patch("staffing_optimization.backend.optimization_service.session_scope")
    @patch("staffing_optimization.backend.optimization_service.get_databricks_service")
    def test_returns_grouped_shifts(self, mock_get_svc, mock_scope):
        from staffing_optimization.backend.optimization_service import OptimizationService

        run = _make_run()
        config = _make_config()
        _patch_session(mock_scope, run, config)

        mock_svc = MagicMock()
        mock_svc.execute_sql.side_effect = [
            [{"cnt": "3"}],
            [
                {"shift_name": "Mon1", "assigned_count": "5", "total_cost": "50.0"},
                {"shift_name": "Tue1", "assigned_count": "3", "total_cost": "30.0"},
                {"shift_name": "Wed1", "assigned_count": "4", "total_cost": "40.0"},
            ],
        ]
        mock_get_svc.return_value = mock_svc

        svc = OptimizationService()
        result = svc.get_shift_aggregates("run-1", limit=50, offset=0)

        assert result is not None
        assert len(result.shifts) == 3
        assert result.shifts[0].shift_name == "Mon1"
        assert result.shifts[0].assigned_count == 5
        assert result.pagination.total == 3


# ---------------------------------------------------------------------------
# get_worker_aggregates
# ---------------------------------------------------------------------------

class TestGetWorkerAggregates:

    @patch("staffing_optimization.backend.optimization_service.session_scope")
    @patch("staffing_optimization.backend.optimization_service.get_databricks_service")
    def test_returns_grouped_workers(self, mock_get_svc, mock_scope):
        from staffing_optimization.backend.optimization_service import OptimizationService

        run = _make_run()
        config = _make_config()
        _patch_session(mock_scope, run, config)

        mock_svc = MagicMock()
        mock_svc.execute_sql.side_effect = [
            [{"cnt": "2"}],
            [
                {"worker_name": "Alice", "shift_count": "3", "total_cost": "30.0"},
                {"worker_name": "Bob", "shift_count": "5", "total_cost": "50.0"},
            ],
        ]
        mock_get_svc.return_value = mock_svc

        svc = OptimizationService()
        result = svc.get_worker_aggregates("run-1", limit=50, offset=0)

        assert result is not None
        assert len(result.workers) == 2
        assert result.workers[1].worker_name == "Bob"
        assert result.workers[1].shift_count == 5


# ---------------------------------------------------------------------------
# get_focused_graph
# ---------------------------------------------------------------------------

class TestGetFocusedGraph:

    @patch("staffing_optimization.backend.optimization_service.session_scope")
    @patch("staffing_optimization.backend.optimization_service.get_databricks_service")
    def test_small_graph_returns_complete(self, mock_get_svc, mock_scope):
        from staffing_optimization.backend.optimization_service import OptimizationService

        run = _make_run()
        config = _make_config()
        _patch_session(mock_scope, run, config)

        mock_svc = MagicMock()
        mock_svc.execute_sql.side_effect = [
            [{"cnt": "3", "w": "2", "s": "2"}],
            [
                {"worker_name": "Alice", "shift_name": "Mon1", "cost": "10.0"},
                {"worker_name": "Alice", "shift_name": "Tue1", "cost": "10.0"},
                {"worker_name": "Bob", "shift_name": "Mon1", "cost": "12.0"},
            ],
        ]
        mock_get_svc.return_value = mock_svc

        svc = OptimizationService()
        result = svc.get_focused_graph("run-1")

        assert result is not None
        assert result.is_complete is True
        assert len(result.edges) == 3
        assert len(result.nodes) == 4  # 2 workers + 2 shifts

    @patch("staffing_optimization.backend.optimization_service.session_scope")
    @patch("staffing_optimization.backend.optimization_service.get_databricks_service")
    def test_large_graph_without_focus_returns_metadata_only(self, mock_get_svc, mock_scope):
        from staffing_optimization.backend.optimization_service import OptimizationService

        run = _make_run()
        config = _make_config()
        _patch_session(mock_scope, run, config)

        mock_svc = MagicMock()
        mock_svc.execute_sql.return_value = [{
            "cnt": str(GRAPH_ELEMENT_THRESHOLD + 1),
            "w": "500",
            "s": "200",
        }]
        mock_get_svc.return_value = mock_svc

        svc = OptimizationService()
        result = svc.get_focused_graph("run-1")

        assert result is not None
        assert result.is_complete is False
        assert result.total_edges == GRAPH_ELEMENT_THRESHOLD + 1
        assert len(result.nodes) == 0
        assert len(result.edges) == 0

    @patch("staffing_optimization.backend.optimization_service.session_scope")
    @patch("staffing_optimization.backend.optimization_service.get_databricks_service")
    def test_focused_on_shift_returns_neighbourhood(self, mock_get_svc, mock_scope):
        from staffing_optimization.backend.optimization_service import OptimizationService

        run = _make_run()
        config = _make_config()
        _patch_session(mock_scope, run, config)

        mock_svc = MagicMock()
        mock_svc.execute_sql.side_effect = [
            [{"cnt": "10000", "w": "500", "s": "200"}],
            [
                {"worker_name": "Alice", "shift_name": "Mon1", "cost": "10.0"},
                {"worker_name": "Bob", "shift_name": "Mon1", "cost": "12.0"},
            ],
        ]
        mock_get_svc.return_value = mock_svc

        svc = OptimizationService()
        result = svc.get_focused_graph("run-1", shift_name="Mon1")

        assert result is not None
        assert result.focus_entity == "Mon1"
        assert result.focus_type == "shift"
        assert len(result.edges) == 2
        worker_nodes = [n for n in result.nodes if n["kind"] == "worker"]
        shift_nodes = [n for n in result.nodes if n["kind"] == "shift"]
        assert len(worker_nodes) == 2
        assert len(shift_nodes) == 1

    @patch("staffing_optimization.backend.optimization_service.session_scope")
    def test_nonexistent_run_returns_none(self, mock_scope):
        from staffing_optimization.backend.optimization_service import OptimizationService

        session = MagicMock()
        session.get.return_value = None
        mock_scope.return_value.__enter__ = MagicMock(return_value=session)
        mock_scope.return_value.__exit__ = MagicMock(return_value=False)

        svc = OptimizationService()
        assert svc.get_focused_graph("nonexistent") is None
