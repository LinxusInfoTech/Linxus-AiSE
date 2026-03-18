# aise/tool_executor/tools/kubectl.py
"""Kubernetes CLI wrapper.

Requirements: 9.4, 9.14, 17.20
"""

import os
from typing import Optional
import structlog

from aise.tool_executor.base import ToolExecutor, ToolResult
from aise.tool_executor.output_parser import OutputParser

logger = structlog.get_logger(__name__)


class KubectlTool:
    """Wrapper for kubectl commands with JSON output parsing.

    Uses KUBECONFIG env var → ~/.kube/config. Respects current-context.
    """

    def __init__(self, executor: Optional[ToolExecutor] = None):
        self.executor = executor or ToolExecutor()
        self.parser = OutputParser()
        kubeconfig = os.environ.get("KUBECONFIG", "~/.kube/config")
        logger.info("KubectlTool initialized", kubeconfig=kubeconfig)

    async def _run(self, *parts: str, timeout: int = 30) -> ToolResult:
        cmd = "kubectl " + " ".join(parts) + " -o json"
        return await self.executor.run(cmd, timeout=timeout)

    async def get_pods(self, namespace: str = "default") -> ToolResult:
        """Run kubectl get pods -o json."""
        result = await self._run("get", "pods", "-n", namespace)
        result.parsed_output = self.parser.parse_kubectl_output(result.stdout)
        result.anomalies = self.parser.detect_anomalies(result.stdout + result.stderr)
        return result

    async def describe_pod(self, pod_name: str, namespace: str = "default") -> ToolResult:
        """Run kubectl describe pod (plain text output)."""
        cmd = f"kubectl describe pod {pod_name} -n {namespace}"
        result = await self.executor.run(cmd)
        result.anomalies = self.parser.detect_anomalies(result.stdout + result.stderr)
        return result

    async def get_events(self, namespace: str = "default") -> ToolResult:
        """Run kubectl get events -o json."""
        result = await self._run("get", "events", "-n", namespace)
        result.parsed_output = self.parser.parse_kubectl_output(result.stdout)
        result.anomalies = self.parser.detect_anomalies(result.stdout)
        return result

    async def get_logs(self, pod_name: str, namespace: str = "default",
                       container: Optional[str] = None, tail: int = 100) -> ToolResult:
        """Run kubectl logs."""
        parts = ["logs", pod_name, "-n", namespace, f"--tail={tail}"]
        if container:
            parts += ["-c", container]
        cmd = "kubectl " + " ".join(parts)
        result = await self.executor.run(cmd)
        result.anomalies = self.parser.detect_anomalies(result.stdout + result.stderr)
        return result
