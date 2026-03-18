# aise/tool_executor/tools/ssh_tool.py
"""SSH execution wrapper. Requirements: 9.4"""

from typing import Optional
import structlog

from aise.tool_executor.base import ToolExecutor, ToolResult
from aise.tool_executor.output_parser import OutputParser

logger = structlog.get_logger(__name__)


class SSHTool:
    """Wrapper for SSH command execution with key-based auth."""

    def __init__(self, executor: Optional[ToolExecutor] = None):
        self.executor = executor or ToolExecutor()
        self.parser = OutputParser()
        logger.info("SSHTool initialized")

    async def run_command(
        self,
        host: str,
        command: str,
        user: Optional[str] = None,
        key_file: Optional[str] = None,
        port: int = 22,
        timeout: int = 30,
    ) -> ToolResult:
        """Execute a command on a remote host via SSH."""
        parts = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes"]
        parts += ["-p", str(port)]
        if key_file:
            parts += ["-i", key_file]
        target = f"{user}@{host}" if user else host
        parts += [target, command]
        cmd = " ".join(parts)
        result = await self.executor.run(cmd, timeout=timeout)
        result.anomalies = self.parser.detect_anomalies(result.stdout + result.stderr)
        return result
