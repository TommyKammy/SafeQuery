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
    ExecutionRuntimeFailureError,
    ExecutionRuntimeControls,
    ExecutionRuntimeSafetyState,
    ExecutionResult,
    ExecutionResultMetadata,
    MSSQLExecutionRuntimeUnavailable,
    PostgreSQLExecutionRuntimeUnavailable,
    check_mssql_execution_runtime_readiness,
    check_postgresql_execution_runtime_readiness,
    execute_candidate_sql,
    preflight_execution_runtime_controls,
)

__all__ = [
    "ExecutableCandidateRecord",
    "ExecutionAuditContext",
    "ExecutionConnectorExecutionError",
    "ExecutionConnectorSelection",
    "ExecutionConnectorSelectionError",
    "ExecutionRuntimeCancelledError",
    "ExecutionRuntimeFailureError",
    "ExecutionRuntimeControls",
    "ExecutionRuntimeSafetyState",
    "ExecutionResult",
    "ExecutionResultMetadata",
    "MSSQLExecutionRuntimeUnavailable",
    "PostgreSQLExecutionRuntimeUnavailable",
    "check_mssql_execution_runtime_readiness",
    "check_postgresql_execution_runtime_readiness",
    "execute_candidate_sql",
    "preflight_execution_runtime_controls",
    "select_execution_connector",
]
