# aise/tool_executor/output_parser.py
"""CLI output parsing and anomaly detection.

Parses raw CLI output into structured data and detects common error patterns.

Requirements:
- 9.9: Parse raw CLI output to structured data, detect anomalies
"""

import json
import re
from typing import Any, Dict, List, Optional
import structlog

logger = structlog.get_logger(__name__)

# Common anomaly patterns across tools
ANOMALY_PATTERNS: List[Dict[str, str]] = [
    # Kubernetes
    {"pattern": r"OOMKilled", "message": "Container killed due to out-of-memory (OOMKilled)"},
    {"pattern": r"CrashLoopBackOff", "message": "Container in CrashLoopBackOff - repeatedly crashing"},
    {"pattern": r"ImagePullBackOff|ErrImagePull", "message": "Failed to pull container image"},
    {"pattern": r"Pending.*Unschedulable", "message": "Pod unschedulable - insufficient resources"},
    {"pattern": r"Error.*ContainerCreating", "message": "Container creation error"},
    # Network
    {"pattern": r"connection refused", "message": "Connection refused - service may be down"},
    {"pattern": r"connection timed out|i/o timeout", "message": "Connection timed out"},
    {"pattern": r"no route to host", "message": "No route to host - network/firewall issue"},
    {"pattern": r"Name or service not known|could not resolve", "message": "DNS resolution failure"},
    # AWS
    {"pattern": r"AccessDenied|UnauthorizedOperation", "message": "AWS access denied - check IAM permissions"},
    {"pattern": r"ThrottlingException|RequestLimitExceeded", "message": "AWS API rate limit exceeded"},
    {"pattern": r"InvalidClientTokenId|AuthFailure", "message": "AWS authentication failure - check credentials"},
    # General
    {"pattern": r"permission denied", "message": "Permission denied"},
    {"pattern": r"disk.*full|no space left", "message": "Disk full or no space left"},
    {"pattern": r"out of memory|cannot allocate memory", "message": "Out of memory"},
    {"pattern": r"segmentation fault|core dumped", "message": "Process crashed (segfault)"},
    {"pattern": r"certificate.*expired|ssl.*error", "message": "TLS/SSL certificate error"},
]


class OutputParser:
    """Parses raw CLI output into structured data and detects anomalies.

    Supports JSON output from AWS CLI and kubectl, plus plain text parsing
    with pattern-based anomaly detection for common error conditions.
    """

    def parse(self, output: str, tool: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Parse raw CLI output into structured data.

        Attempts JSON parsing first (for AWS CLI, kubectl with -o json).
        Falls back to plain text representation.

        Args:
            output: Raw stdout string from command execution
            tool: Optional tool name hint (e.g., "aws", "kubectl")

        Returns:
            Parsed dictionary, or None if output is empty
        """
        if not output or not output.strip():
            return None

        stripped = output.strip()

        # Try JSON parsing
        if stripped.startswith(("{", "[")):
            try:
                parsed = json.loads(stripped)
                logger.debug("Parsed JSON output", tool=tool, type=type(parsed).__name__)
                return {"format": "json", "data": parsed}
            except json.JSONDecodeError:
                pass

        # Return as plain text
        return {"format": "text", "data": stripped}

    def detect_anomalies(self, output: str) -> List[str]:
        """Detect common error patterns in command output.

        Scans both stdout and stderr for known error patterns like
        OOMKilled, CrashLoopBackOff, connection refused, etc.

        Args:
            output: Combined stdout/stderr string to scan

        Returns:
            List of human-readable anomaly descriptions found
        """
        if not output:
            return []

        found: List[str] = []
        lower = output.lower()

        for entry in ANOMALY_PATTERNS:
            if re.search(entry["pattern"], output, re.IGNORECASE):
                found.append(entry["message"])

        if found:
            logger.info("Anomalies detected", count=len(found), anomalies=found)

        return found

    def parse_aws_output(self, output: str) -> Optional[Dict[str, Any]]:
        """Parse AWS CLI JSON output.

        Args:
            output: Raw AWS CLI stdout

        Returns:
            Parsed AWS response dict, or None if not parseable
        """
        result = self.parse(output, tool="aws")
        if result and result["format"] == "json":
            return result["data"]
        return None

    def parse_kubectl_output(self, output: str) -> Optional[Dict[str, Any]]:
        """Parse kubectl JSON output (-o json).

        Args:
            output: Raw kubectl stdout

        Returns:
            Parsed kubectl response dict, or None if not parseable
        """
        result = self.parse(output, tool="kubectl")
        if result and result["format"] == "json":
            return result["data"]
        return None
