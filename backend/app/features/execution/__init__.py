"""Approved query execution workflows and source-bound connector selection."""

from app.features.execution.connector_selection import (
    ExecutionConnectorSelection,
    ExecutionConnectorSelectionError,
    select_execution_connector,
)
from app.features.execution.runtime import (
    ExecutableCandidateRecord,
    ExecutionAuditContext,
    ExecutionConnectorExecutionError,
    ExecutionRuntimeCancelledError,
    ExecutionRuntimeControls,
    ExecutionRuntimeSafetyState,
    ExecutionResult,
    MSSQLExecutionRuntimeUnavailable,
    check_mssql_execution_runtime_readiness,
    execute_candidate_sql,
)

__all__ = [
    "ExecutableCandidateRecord",
    "ExecutionAuditContext",
    "ExecutionConnectorExecutionError",
    "ExecutionConnectorSelection",
    "ExecutionConnectorSelectionError",
    "ExecutionRuntimeCancelledError",
    "ExecutionRuntimeControls",
    "ExecutionRuntimeSafetyState",
    "ExecutionResult",
    "MSSQLExecutionRuntimeUnavailable",
    "check_mssql_execution_runtime_readiness",
    "execute_candidate_sql",
    "select_execution_connector",
]
