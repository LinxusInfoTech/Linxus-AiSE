# aise/tool_executor/runner.py
"""Subprocess execution for CLI tools with security controls.

This module implements secure subprocess execution for CLI tools with:
- No shell=True (prevents command injection)
- Configurable timeouts
- Restricted environment
- Structured output capture

Requirements:
- 9.5: Execute commands using asyncio.create_subprocess_exec (never shell=True)
- 9.6: Enforce timeout (default 30s, configurable)
- 9.7: Capture stdout, stderr, exit code, duration
- 9.8: Use restricted environment with minimal permissions
- 9.11: Use restricted environment with minimal permissions
"""

import asyncio
import time
from typing import Dict, Optional, List
import structlog

from aise.core.exceptions import ToolExecutionError, ToolExecutionTimeout

logger = structlog.get_logger(__name__)


class SubprocessRunner:
    """Executes CLI commands in restricted subprocess with security controls.
    
    This class provides secure subprocess execution with:
    - No shell interpretation (prevents injection attacks)
    - Configurable timeouts to prevent hanging processes
    - Restricted environment variables
    - Structured output capture (stdout, stderr, exit code, duration)
    
    The runner uses asyncio.create_subprocess_exec which does NOT use shell=True,
    preventing command injection vulnerabilities.
    
    Attributes:
        default_timeout: Default timeout in seconds for command execution
        restricted_env: Restricted environment variables for subprocess
    """
    
    def __init__(self, default_timeout: int = 30):
        """Initialize the subprocess runner.
        
        Args:
            default_timeout: Default timeout in seconds (default: 30)
        """
        self.default_timeout = default_timeout
        self.restricted_env = self._create_restricted_env()
        
        logger.info(
            "Subprocess runner initialized",
            default_timeout=default_timeout
        )
    
    def _create_restricted_env(self) -> Dict[str, str]:
        """Create a restricted environment for subprocess execution.
        
        This environment includes only essential variables and excludes
        potentially dangerous ones. It preserves cloud provider credentials
        and tool configurations while removing shell-related variables.
        
        Returns:
            Dictionary of environment variables for subprocess
        """
        import os
        
        # Start with minimal environment
        restricted = {}
        
        # Essential system variables
        safe_vars = [
            "PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM",
            # AWS credentials
            "AWS_PROFILE", "AWS_DEFAULT_REGION", "AWS_REGION",
            "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN", "AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE",
            # Kubernetes
            "KUBECONFIG",
            # Google Cloud
            "GOOGLE_APPLICATION_CREDENTIALS", "GCLOUD_PROJECT",
            # Azure
            "AZURE_CONFIG_DIR",
            # Docker
            "DOCKER_HOST", "DOCKER_CONFIG",
            # Git
            "GIT_CONFIG",
            # SSH
            "SSH_AUTH_SOCK",
        ]
        
        for var in safe_vars:
            value = os.environ.get(var)
            if value:
                restricted[var] = value
        
        # Ensure PATH is set (critical for finding executables)
        if "PATH" not in restricted:
            restricted["PATH"] = "/usr/local/bin:/usr/bin:/bin"
        
        return restricted
    
    async def run(
        self,
        command: str,
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None
    ) -> Dict[str, any]:
        """Execute a command in a restricted subprocess.
        
        This method executes a command using asyncio.create_subprocess_exec
        (NOT shell=True) to prevent command injection. It captures stdout,
        stderr, exit code, and execution duration.
        
        Args:
            command: Full command string to execute (will be split into args)
            timeout: Timeout in seconds (uses default_timeout if not specified)
            env: Additional environment variables (merged with restricted_env)
            cwd: Working directory for command execution
        
        Returns:
            Dictionary containing:
                - command: The executed command string
                - stdout: Standard output as string
                - stderr: Standard error as string
                - exit_code: Process exit code
                - duration_ms: Execution duration in milliseconds
        
        Raises:
            ToolExecutionTimeout: If command exceeds timeout
            ToolExecutionError: If command execution fails
        
        Example:
            >>> result = await runner.run("aws ec2 describe-instances", timeout=30)
            >>> print(result['exit_code'])
            0
        """
        timeout_seconds = timeout if timeout is not None else self.default_timeout
        
        # Parse command into arguments (split by whitespace)
        # This is safe because we're not using shell=True
        args = command.strip().split()
        if not args:
            raise ToolExecutionError("Empty command provided")
        
        # Merge environment variables
        process_env = self.restricted_env.copy()
        if env:
            process_env.update(env)
        
        logger.info(
            "Executing command",
            command=command,
            timeout=timeout_seconds,
            cwd=cwd
        )
        
        start_time = time.time()
        
        try:
            # Create subprocess without shell=True (security requirement)
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=process_env,
                cwd=cwd
            )
            
            # Wait for process with timeout
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                # Kill the process if it times out
                try:
                    process.kill()
                    await process.wait()
                except Exception as e:
                    logger.warning("Failed to kill timed out process", error=str(e))
                
                duration_ms = int((time.time() - start_time) * 1000)
                
                logger.warning(
                    "Command timed out",
                    command=command,
                    timeout=timeout_seconds,
                    duration_ms=duration_ms
                )
                
                raise ToolExecutionTimeout(command, timeout_seconds)
            
            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Decode output
            stdout = stdout_bytes.decode('utf-8', errors='replace')
            stderr = stderr_bytes.decode('utf-8', errors='replace')
            exit_code = process.returncode
            
            # Log execution result
            log_data = {
                "command": command,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "stdout_length": len(stdout),
                "stderr_length": len(stderr)
            }
            
            if exit_code == 0:
                logger.info("Command executed successfully", **log_data)
            else:
                logger.warning("Command failed", **log_data, stderr_preview=stderr[:200])
            
            return {
                "command": command,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "duration_ms": duration_ms
            }
        
        except ToolExecutionTimeout:
            # Re-raise timeout exceptions
            raise
        
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.error(
                "Command execution failed",
                command=command,
                error=str(e),
                duration_ms=duration_ms
            )
            
            raise ToolExecutionError(
                f"Failed to execute command: {str(e)}",
                command=command
            )
    
    async def run_with_input(
        self,
        command: str,
        stdin_data: str,
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None
    ) -> Dict[str, any]:
        """Execute a command with stdin input.
        
        Similar to run() but allows passing data to stdin.
        
        Args:
            command: Full command string to execute
            stdin_data: Data to send to stdin
            timeout: Timeout in seconds
            env: Additional environment variables
            cwd: Working directory
        
        Returns:
            Dictionary with command execution results
        
        Raises:
            ToolExecutionTimeout: If command exceeds timeout
            ToolExecutionError: If command execution fails
        """
        timeout_seconds = timeout if timeout is not None else self.default_timeout
        
        args = command.strip().split()
        if not args:
            raise ToolExecutionError("Empty command provided")
        
        process_env = self.restricted_env.copy()
        if env:
            process_env.update(env)
        
        logger.info(
            "Executing command with stdin",
            command=command,
            stdin_length=len(stdin_data),
            timeout=timeout_seconds
        )
        
        start_time = time.time()
        
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=process_env,
                cwd=cwd
            )
            
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(input=stdin_data.encode('utf-8')),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                try:
                    process.kill()
                    await process.wait()
                except Exception as e:
                    logger.warning("Failed to kill timed out process", error=str(e))
                
                duration_ms = int((time.time() - start_time) * 1000)
                raise ToolExecutionTimeout(command, timeout_seconds)
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            stdout = stdout_bytes.decode('utf-8', errors='replace')
            stderr = stderr_bytes.decode('utf-8', errors='replace')
            exit_code = process.returncode
            
            logger.info(
                "Command with stdin executed",
                command=command,
                exit_code=exit_code,
                duration_ms=duration_ms
            )
            
            return {
                "command": command,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "duration_ms": duration_ms
            }
        
        except ToolExecutionTimeout:
            raise
        
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.error(
                "Command with stdin failed",
                command=command,
                error=str(e),
                duration_ms=duration_ms
            )
            
            raise ToolExecutionError(
                f"Failed to execute command with stdin: {str(e)}",
                command=command
            )
