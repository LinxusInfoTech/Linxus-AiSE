# aise/tool_executor/tools/aws_cli.py
"""AWS CLI wrapper with structured output.

Requirements: 9.4, 9.13, 17.19
"""

import os
from typing import Any, Dict, List, Optional
import structlog

from aise.tool_executor.base import ToolExecutor, ToolResult
from aise.tool_executor.output_parser import OutputParser

logger = structlog.get_logger(__name__)


class AWSCLITool:
    """Wrapper for AWS CLI commands with JSON output parsing.

    Uses the AWS credential chain: env vars → ~/.aws/credentials →
    ~/.aws/config → IAM role. Respects AWS_PROFILE and AWS_DEFAULT_REGION.
    """

    def __init__(self, executor: Optional[ToolExecutor] = None):
        self.executor = executor or ToolExecutor()
        self.parser = OutputParser()
        profile = os.environ.get("AWS_PROFILE", "default")
        region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION", "us-east-1")
        logger.info("AWSCLITool initialized", profile=profile, region=region)

    def _build_cmd(self, *parts: str) -> str:
        return "aws " + " ".join(parts) + " --output json"

    async def _run(self, *parts: str, timeout: int = 30) -> ToolResult:
        cmd = self._build_cmd(*parts)
        return await self.executor.run(cmd, timeout=timeout)

    async def describe_instances(self, filters: Optional[List[str]] = None) -> ToolResult:
        """Run aws ec2 describe-instances."""
        args = ["ec2", "describe-instances"]
        if filters:
            args += ["--filters"] + filters
        result = await self._run(*args)
        result.parsed_output = self.parser.parse_aws_output(result.stdout)
        result.anomalies = self.parser.detect_anomalies(result.stderr)
        return result

    async def get_security_groups(self, group_ids: Optional[List[str]] = None) -> ToolResult:
        """Run aws ec2 describe-security-groups."""
        args = ["ec2", "describe-security-groups"]
        if group_ids:
            args += ["--group-ids"] + group_ids
        result = await self._run(*args)
        result.parsed_output = self.parser.parse_aws_output(result.stdout)
        return result

    async def describe_vpcs(self) -> ToolResult:
        result = await self._run("ec2", "describe-vpcs")
        result.parsed_output = self.parser.parse_aws_output(result.stdout)
        return result

    async def get_log_events(self, log_group: str, log_stream: str, limit: int = 100) -> ToolResult:
        result = await self._run(
            "logs", "get-log-events",
            "--log-group-name", log_group,
            "--log-stream-name", log_stream,
            "--limit", str(limit)
        )
        result.parsed_output = self.parser.parse_aws_output(result.stdout)
        return result

    async def describe_alarms(self, state: str = "ALARM") -> ToolResult:
        result = await self._run("cloudwatch", "describe-alarms", "--state-value", state)
        result.parsed_output = self.parser.parse_aws_output(result.stdout)
        return result
