# aise/agents/tool_agent.py
"""Tool execution planning and analysis agent.

Requirements: 10.9
"""

import asyncio
from typing import Any, Dict, List, Optional
import structlog

from aise.agents.state import AiSEState, ToolResult, update_state
from aise.tool_executor.base import ToolExecutor
from aise.tool_executor.output_parser import OutputParser
from aise.core.exceptions import ForbiddenCommandError, ToolExecutionTimeout

logger = structlog.get_logger(__name__)

# Commands the LLM may suggest mapped to safe executor calls
TOOL_PLAN_KEYWORDS = {
    "aws": "aws",
    "kubectl": "kubectl",
    "terraform": "terraform",
    "docker": "docker",
    "git": "git",
    "ssh": "ssh",
}


class ToolAgent:
    """Plans and executes diagnostic CLI tools based on the current diagnosis.

    Integrates with ToolExecutor for allowlist-enforced subprocess execution
    and updates AiSEState with structured ToolResult objects.
    """

    def __init__(self, executor: Optional[ToolExecutor] = None):
        self.executor = executor or ToolExecutor()
        self.parser = OutputParser()
        logger.info("tool_agent_initialized")

    def plan_execution(self, state: AiSEState) -> List[str]:
        """Determine which commands to run based on diagnosis and ticket context.

        Scans the diagnosis text for tool keywords and builds a minimal
        list of safe diagnostic commands to run.

        Args:
            state: Current AiSEState

        Returns:
            List of command strings to execute
        """
        diagnosis = state.get("diagnosis") or ""
        ticket = state.get("ticket")
        ticket_body = ticket.body if ticket else ""
        combined = (diagnosis + " " + ticket_body).lower()

        planned: List[str] = []

        # Suggest kubectl commands for Kubernetes issues
        if any(kw in combined for kw in ("pod", "kubectl", "kubernetes", "k8s", "crashloop", "oomkilled")):
            planned.append("kubectl get pods -n default")
            planned.append("kubectl get events -n default")

        # Suggest AWS commands for cloud issues
        if any(kw in combined for kw in ("ec2", "instance", "security group", "aws", "vpc")):
            planned.append("aws ec2 describe-instances --output json")

        # Suggest docker commands for container issues
        if any(kw in combined for kw in ("docker", "container", "image")):
            planned.append("docker ps -a")

        # Suggest git commands for deployment issues
        if any(kw in combined for kw in ("git", "commit", "deploy", "branch")):
            planned.append("git log -10 --oneline")
            planned.append("git status")

        logger.info("tool_plan_complete", planned_count=len(planned), commands=planned)
        return planned

    async def execute_and_analyze(self, state: AiSEState, commands: Optional[List[str]] = None) -> AiSEState:
        """Execute planned commands and update state with results.

        Runs each command through the ToolExecutor (allowlist enforced),
        parses output, detects anomalies, and appends ToolResult objects
        to state.tool_results.

        Args:
            state: Current AiSEState
            commands: Commands to run (uses plan_execution if None)

        Returns:
            New AiSEState with tool_results populated
        """
        if commands is None:
            commands = self.plan_execution(state)

        if not commands:
            logger.info("tool_execute_skip", reason="no_commands_planned")
            return state

        results: List[ToolResult] = list(state.get("tool_results") or [])
        actions: List[str] = list(state.get("actions_taken") or [])

        for cmd in commands:
            try:
                exec_result = await self.executor.run(cmd)

                # Parse and detect anomalies
                parsed = self.parser.parse(exec_result.stdout, tool=cmd.split()[0])
                anomalies = self.parser.detect_anomalies(exec_result.stdout + exec_result.stderr)

                tool_result = ToolResult(
                    tool_name=cmd.split()[0],
                    command=cmd,
                    stdout=exec_result.stdout,
                    stderr=exec_result.stderr,
                    exit_code=exec_result.exit_code,
                    duration_seconds=exec_result.duration_ms / 1000.0,
                    timestamp=exec_result.timestamp,
                )

                results.append(tool_result)
                actions.append(f"Executed: {cmd}")

                logger.info(
                    "tool_executed",
                    command=cmd,
                    exit_code=exec_result.exit_code,
                    anomalies=anomalies,
                )

            except ForbiddenCommandError as e:
                logger.warning("tool_forbidden", command=cmd, error=str(e))
                actions.append(f"Blocked (not allowed): {cmd}")

            except ToolExecutionTimeout as e:
                logger.warning("tool_timeout", command=cmd, error=str(e))
                actions.append(f"Timed out: {cmd}")

            except Exception as e:
                logger.error("tool_execution_error", command=cmd, error=str(e))
                actions.append(f"Failed: {cmd}")

        return update_state(state, tool_results=results, actions_taken=actions)
