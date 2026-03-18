# aise/tool_executor/__init__.py
"""CLI tool execution with security controls.

This package provides secure CLI tool execution with:
- Command allowlist enforcement
- Subprocess execution without shell=True
- Timeout enforcement
- Structured output capture
- Comprehensive audit logging

Main components:
- CommandAllowlist: Enforces which commands can be executed
- SubprocessRunner: Executes commands in restricted subprocess
- ToolExecutor: Main interface integrating allowlist and runner
- ToolResult: Data model for execution results

Example usage:
    >>> from aise.tool_executor import ToolExecutor
    >>> executor = ToolExecutor()
    >>> result = await executor.run("aws ec2 describe-instances")
    >>> print(result.exit_code)
    0
"""

from aise.tool_executor.allowlist import CommandAllowlist
from aise.tool_executor.runner import SubprocessRunner
from aise.tool_executor.base import ToolExecutor, ToolResult
from aise.tool_executor.output_parser import OutputParser

__all__ = [
    "CommandAllowlist",
    "SubprocessRunner",
    "ToolExecutor",
    "ToolResult",
    "OutputParser",
]
