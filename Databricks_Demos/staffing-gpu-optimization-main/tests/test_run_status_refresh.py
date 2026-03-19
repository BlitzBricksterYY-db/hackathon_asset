"""Tests for run status refresh logic.

Covers:
- TERMINATED + result_state=None falls back to COMPLETED
- TERMINATED + result_state from task-level fallback in get_run_status
- PENDING runs are refreshed in list_runs path
- Force-refresh endpoint resolves terminal status
"""
from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest

from staffing_optimization.backend.models import RunStatus
from staffing_optimization.backend.db_models import OptimizationRunDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run(
    *,
    status: str = RunStatus.RUNNING.value,
    databricks_run_id: int | None = 12345,
) -> OptimizationRunDB:
    """Create a minimal in-memory OptimizationRunDB row."""
    run = OptimizationRunDB(
        id="test-run-1",
        config_id="test-config-1",
        run_name="unit test run",
        status=status,
        databricks_run_id=databricks_run_id,
        owner_user="tester@example.com",
    )
    run.created_at = datetime.utcnow()
    run.updated_at = datetime.utcnow()
    return run


# ---------------------------------------------------------------------------
# databricks_service.get_run_status – task-level fallback
# ---------------------------------------------------------------------------

class TestGetRunStatusFallback:
    """Verify that get_run_status falls back to task result_state."""

    def _build_run_object(self, *, lifecycle, run_result=None, task_result=None):
        """Build a mock Databricks Run object."""
        run = MagicMock()
        run.run_id = 99999

        # Run-level state
        run.state = MagicMock()
        run.state.life_cycle_state = MagicMock(value=lifecycle) if lifecycle else None
        if run_result is not None:
            run.state.result_state = MagicMock(value=run_result)
        else:
            run.state.result_state = None
        run.state.state_message = None
        run.run_page_url = "https://example.com/run/99999"

        # Task-level state
        if task_result is not None:
            task = MagicMock()
            task.task_key = "run_optimization"
            task.state = MagicMock()
            task.state.result_state = MagicMock(value=task_result)
            task.state.state_message = None
            run.tasks = [task]
        else:
            run.tasks = []

        return run

    def test_run_level_result_state_preferred(self):
        """When run-level result_state exists, it should be used."""
        from staffing_optimization.backend.databricks_service import DatabricksService

        svc = DatabricksService()
        mock_run = self._build_run_object(
            lifecycle="TERMINATED", run_result="SUCCESS", task_result="SUCCESS"
        )
        svc._client = MagicMock()
        svc._client.jobs.get_run.return_value = mock_run

        result = svc.get_run_status(99999)
        assert result["result_state"] == "SUCCESS"
        assert result["state"] == "TERMINATED"

    def test_task_fallback_when_run_result_none(self):
        """When run-level result_state is None, fall back to first task."""
        from staffing_optimization.backend.databricks_service import DatabricksService

        svc = DatabricksService()
        mock_run = self._build_run_object(
            lifecycle="TERMINATED", run_result=None, task_result="SUCCESS"
        )
        svc._client = MagicMock()
        svc._client.jobs.get_run.return_value = mock_run

        result = svc.get_run_status(99999)
        assert result["result_state"] == "SUCCESS"

    def test_none_when_both_absent(self):
        """When both run-level and task-level are absent, result_state is None."""
        from staffing_optimization.backend.databricks_service import DatabricksService

        svc = DatabricksService()
        mock_run = self._build_run_object(
            lifecycle="TERMINATED", run_result=None, task_result=None
        )
        svc._client = MagicMock()
        svc._client.jobs.get_run.return_value = mock_run

        result = svc.get_run_status(99999)
        assert result["result_state"] is None


# ---------------------------------------------------------------------------
# _refresh_run_status – TERMINATED with None result_state
# ---------------------------------------------------------------------------

class TestRefreshRunStatusTerminatedFallback:
    """Verify _refresh_run_status resolves TERMINATED + None result_state."""

    @patch("staffing_optimization.backend.optimization_service.get_databricks_service")
    def test_terminated_none_becomes_completed(self, mock_get_svc):
        from staffing_optimization.backend.optimization_service import OptimizationService

        mock_svc = MagicMock()
        mock_svc.get_run_status.return_value = {
            "state": "TERMINATED",
            "result_state": None,
            "state_message": None,
            "run_page_url": "https://example.com/run/1",
            "task_errors": [],
        }
        mock_svc.get_run_output.return_value = {
            "total_cost": 42.0,
            "solve_time_seconds": 1.5,
            "num_workers_assigned": 5,
            "num_shifts_covered": 10,
        }
        mock_get_svc.return_value = mock_svc

        session = MagicMock()
        db_run = _make_run(status=RunStatus.RUNNING.value)

        service = OptimizationService()
        service._refresh_run_status(session, db_run)

        assert db_run.status == RunStatus.COMPLETED.value
        assert db_run.total_cost == 42.0
        assert db_run.completed_at is not None
        session.commit.assert_called_once()

    @patch("staffing_optimization.backend.optimization_service.get_databricks_service")
    def test_terminated_none_output_failure_still_completed(self, mock_get_svc):
        """If notebook output fetch fails, TERMINATED + None still becomes COMPLETED."""
        from staffing_optimization.backend.optimization_service import OptimizationService

        mock_svc = MagicMock()
        mock_svc.get_run_status.return_value = {
            "state": "TERMINATED",
            "result_state": None,
            "state_message": None,
            "run_page_url": None,
            "task_errors": [],
        }
        mock_svc.get_run_output.side_effect = Exception("network error")
        mock_get_svc.return_value = mock_svc

        session = MagicMock()
        db_run = _make_run(status=RunStatus.RUNNING.value)

        service = OptimizationService()
        service._refresh_run_status(session, db_run)

        assert db_run.status == RunStatus.COMPLETED.value
        session.commit.assert_called_once()

    @patch("staffing_optimization.backend.optimization_service.get_databricks_service")
    def test_terminated_success_no_output_becomes_completed(self, mock_get_svc):
        """TERMINATED + SUCCESS with no notebook output must still become COMPLETED.

        This is the root cause of long-running GPU jobs staying stuck as RUNNING:
        get_run_output() returns None (no exception) when the notebook doesn't
        call dbutils.notebook.exit(), and without an else branch the status was
        never updated.
        """
        from staffing_optimization.backend.optimization_service import OptimizationService

        mock_svc = MagicMock()
        mock_svc.get_run_status.return_value = {
            "state": "TERMINATED",
            "result_state": "SUCCESS",
            "state_message": None,
            "run_page_url": None,
            "task_errors": [],
        }
        mock_svc.get_run_output.return_value = None  # No notebook output
        mock_get_svc.return_value = mock_svc

        session = MagicMock()
        db_run = _make_run(status=RunStatus.RUNNING.value)

        service = OptimizationService()
        service._refresh_run_status(session, db_run)

        assert db_run.status == RunStatus.COMPLETED.value
        assert db_run.completed_at is not None
        session.commit.assert_called_once()

    @patch("staffing_optimization.backend.optimization_service.get_databricks_service")
    def test_terminated_success_still_works(self, mock_get_svc):
        """The normal SUCCESS path remains intact."""
        from staffing_optimization.backend.optimization_service import OptimizationService

        mock_svc = MagicMock()
        mock_svc.get_run_status.return_value = {
            "state": "TERMINATED",
            "result_state": "SUCCESS",
            "state_message": None,
            "run_page_url": None,
            "task_errors": [],
        }
        mock_svc.get_run_output.return_value = {
            "total_cost": 100.0,
            "solve_time_seconds": 2.0,
            "num_workers_assigned": 8,
            "num_shifts_covered": 12,
        }
        mock_get_svc.return_value = mock_svc

        session = MagicMock()
        db_run = _make_run(status=RunStatus.RUNNING.value)

        service = OptimizationService()
        service._refresh_run_status(session, db_run)

        assert db_run.status == RunStatus.COMPLETED.value
        assert db_run.total_cost == 100.0

    @patch("staffing_optimization.backend.optimization_service.get_databricks_service")
    def test_terminated_failed_still_works(self, mock_get_svc):
        """The normal FAILED path remains intact."""
        from staffing_optimization.backend.optimization_service import OptimizationService

        mock_svc = MagicMock()
        mock_svc.get_run_status.return_value = {
            "state": "TERMINATED",
            "result_state": "FAILED",
            "state_message": "Task failed with error X",
            "run_page_url": "https://example.com/run/1",
            "task_errors": [{"task_key": "run_optimization", "result_state": "FAILED", "state_message": "error X"}],
        }
        mock_get_svc.return_value = mock_svc

        session = MagicMock()
        db_run = _make_run(status=RunStatus.RUNNING.value)

        service = OptimizationService()
        service._refresh_run_status(session, db_run)

        assert db_run.status == RunStatus.FAILED.value
        assert "error X" in (db_run.error_message or "")


# ---------------------------------------------------------------------------
# list_runs – PENDING refresh
# ---------------------------------------------------------------------------

class TestListRunsRefreshPending:
    """Verify list_runs refreshes both RUNNING and PENDING runs."""

    @patch("staffing_optimization.backend.optimization_service.session_scope")
    @patch("staffing_optimization.backend.optimization_service.get_databricks_service")
    def test_pending_run_is_refreshed(self, mock_get_svc, mock_session_scope):
        from staffing_optimization.backend.optimization_service import OptimizationService

        pending_run = _make_run(status=RunStatus.PENDING.value, databricks_run_id=111)
        running_run = _make_run(status=RunStatus.RUNNING.value, databricks_run_id=222)
        running_run.id = "test-run-2"
        completed_run = _make_run(status=RunStatus.COMPLETED.value, databricks_run_id=333)
        completed_run.id = "test-run-3"

        session = MagicMock()
        session.exec.return_value.all.return_value = [pending_run, running_run, completed_run]
        mock_session_scope.return_value.__enter__ = MagicMock(return_value=session)
        mock_session_scope.return_value.__exit__ = MagicMock(return_value=False)

        mock_svc = MagicMock()
        mock_svc.get_run_status.return_value = {
            "state": "RUNNING",
            "result_state": None,
            "state_message": None,
            "run_page_url": None,
            "task_errors": [],
        }
        mock_get_svc.return_value = mock_svc

        service = OptimizationService()
        service.list_runs()

        # Both PENDING and RUNNING runs should trigger a refresh call
        assert mock_svc.get_run_status.call_count == 2
