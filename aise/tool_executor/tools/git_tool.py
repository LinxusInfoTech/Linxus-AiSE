# aise/tool_executor/tools/git_tool.py
"""Git CLI wrapper. Requirements: 9.4"""

from typing import Optional
import structlog

from aise.tool_executor.base import ToolExecutor, ToolResult
from aise.tool_executor.output_parser import OutputParser

logger = structlog.get_logger(__name__)


class GitTool:
    """Wrapper for read-only Git commands."""

    def __init__(self, executor: Optional[ToolExecutor] = None, cwd: Optional[str] = None):
        self.executor = executor or ToolExecutor()
        self.parser = OutputParser()
        self.cwd = cwd
        logger.info("GitTool initialized", cwd=cwd)

    async def status(self) -> ToolResult:
        return await self.executor.run("git status", cwd=self.cwd)

    async def log(self, limit: int = 20, oneline: bool = True) -> ToolResult:
        flags = "--oneline" if oneline else ""
        cmd = f"git log -{limit} {flags}".strip()
        return await self.executor.run(cmd, cwd=self.cwd)

    async def diff(self, ref: Optional[str] = None) -> ToolResult:
        cmd = f"git diff {ref}" if ref else "git diff"
        return await self.executor.run(cmd, cwd=self.cwd)

    async def show(self, ref: str = "HEAD") -> ToolResult:
        return await self.executor.run(f"git show {ref}", cwd=self.cwd)

    async def branch(self) -> ToolResult:
        return await self.executor.run("git branch -a", cwd=self.cwd)

    async def remote(self) -> ToolResult:
        return await self.executor.run("git remote -v", cwd=self.cwd)
