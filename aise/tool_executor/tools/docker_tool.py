# aise/tool_executor/tools/docker_tool.py
"""Docker CLI wrapper. Requirements: 9.4"""

from typing import Optional
import structlog

from aise.tool_executor.base import ToolExecutor, ToolResult
from aise.tool_executor.output_parser import OutputParser

logger = structlog.get_logger(__name__)


class DockerTool:
    """Wrapper for read-only Docker commands."""

    def __init__(self, executor: Optional[ToolExecutor] = None):
        self.executor = executor or ToolExecutor()
        self.parser = OutputParser()
        logger.info("DockerTool initialized")

    async def ps(self, all_containers: bool = False) -> ToolResult:
        cmd = "docker ps --format json" + (" -a" if all_containers else "")
        result = await self.executor.run(cmd)
        result.parsed_output = self.parser.parse(result.stdout, tool="docker")
        return result

    async def logs(self, container: str, tail: int = 100) -> ToolResult:
        result = await self.executor.run(f"docker logs {container} --tail {tail}")
        result.anomalies = self.parser.detect_anomalies(result.stdout + result.stderr)
        return result

    async def inspect(self, container: str) -> ToolResult:
        result = await self.executor.run(f"docker inspect {container}")
        result.parsed_output = self.parser.parse(result.stdout, tool="docker")
        return result

    async def stats(self, container: str) -> ToolResult:
        result = await self.executor.run(f"docker stats {container} --no-stream")
        return result

    async def images(self) -> ToolResult:
        result = await self.executor.run("docker images")
        return result
