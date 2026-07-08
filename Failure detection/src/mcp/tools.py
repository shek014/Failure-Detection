"""MCP tool execution layer for remediation actions."""

import time
from typing import Any

import structlog

from src.models.incident import RemediationAction, ResolutionResult
from src.monitoring.incident_simulator import get_simulator

logger = structlog.get_logger()


class MCPToolExecutor:
    """Executes remediation actions via MCP-compatible tool interface."""

    def __init__(self) -> None:
        self.simulator = get_simulator()

    TOOLS = {
        RemediationAction.RESTART_SERVICE: "restart_service",
        RemediationAction.CLEAR_CACHE: "clear_cache",
        RemediationAction.SCALE_CONTAINERS: "scale_containers",
        RemediationAction.ROLLBACK_DEPLOYMENT: "rollback_deployment",
        RemediationAction.RECONNECT_DATABASE: "reconnect_database",
        RemediationAction.RESTART_PODS: "restart_pods",
    }

    def execute(self, action: RemediationAction, service: str, **kwargs: Any) -> ResolutionResult:
        tool_name = self.TOOLS.get(action)
        if not tool_name:
            return ResolutionResult(
                action=action,
                success=False,
                message=f"No tool mapped for action: {action.value}",
            )

        logger.info("mcp_execute", tool=tool_name, service=service)
        handler = getattr(self, f"_tool_{tool_name}", None)
        if handler:
            result = handler(service, **kwargs)
            if result.success:
                self.simulator.apply_remediation(action, service)
                result.message = f"{result.message} (Simulated — state updated)"
            return result

        return ResolutionResult(
            action=action,
            success=False,
            message=f"Tool handler not implemented: {tool_name}",
        )

    def _tool_restart_service(self, service: str, **kwargs: Any) -> ResolutionResult:
        time.sleep(0.5)
        return ResolutionResult(
            action=RemediationAction.RESTART_SERVICE,
            success=True,
            message=f"Service '{service}' restarted successfully",
            execution_details={"duration_ms": 500, "method": "graceful_restart"},
        )

    def _tool_clear_cache(self, service: str, **kwargs: Any) -> ResolutionResult:
        time.sleep(0.3)
        return ResolutionResult(
            action=RemediationAction.CLEAR_CACHE,
            success=True,
            message=f"Cache cleared for '{service}'",
            execution_details={"keys_evicted": 1247},
        )

    def _tool_scale_containers(self, service: str, **kwargs: Any) -> ResolutionResult:
        replicas = kwargs.get("replicas", 3)
        time.sleep(0.8)
        return ResolutionResult(
            action=RemediationAction.SCALE_CONTAINERS,
            success=True,
            message=f"Scaled '{service}' to {replicas} replicas",
            execution_details={"previous_replicas": 1, "new_replicas": replicas},
        )

    def _tool_rollback_deployment(self, service: str, **kwargs: Any) -> ResolutionResult:
        time.sleep(1.0)
        return ResolutionResult(
            action=RemediationAction.ROLLBACK_DEPLOYMENT,
            success=True,
            message=f"Rolled back deployment for '{service}' to previous version",
            execution_details={"from_version": "v2.1.0", "to_version": "v2.0.5"},
        )

    def _tool_reconnect_database(self, service: str, **kwargs: Any) -> ResolutionResult:
        time.sleep(0.6)
        return ResolutionResult(
            action=RemediationAction.RECONNECT_DATABASE,
            success=True,
            message=f"Database proxy reconnected for '{service}'",
            execution_details={"pool_size_reset": True, "connections_freed": 50},
        )

    def _tool_restart_pods(self, service: str, **kwargs: Any) -> ResolutionResult:
        time.sleep(0.7)
        return ResolutionResult(
            action=RemediationAction.RESTART_PODS,
            success=True,
            message=f"Restarted pods for '{service}'",
            execution_details={"pods_restarted": 2, "namespace": "production"},
        )

    def list_tools(self) -> list[dict[str, str]]:
        return [
            {"name": tool, "action": action.value}
            for action, tool in self.TOOLS.items()
        ]
