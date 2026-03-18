# tests/unit/test_tool_executor.py
"""Unit tests for tool executor components.

Tests cover:
- CommandAllowlist validation
- SubprocessRunner execution
- ToolExecutor integration
- ToolResult data model
"""

import pytest
import asyncio
import json
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

from aise.tool_executor import (
    CommandAllowlist,
    SubprocessRunner,
    ToolExecutor,
    ToolResult
)
from aise.core.exceptions import (
    ForbiddenCommandError,
    ToolExecutionTimeout,
    ToolExecutionError
)


# ============================================================================
# CommandAllowlist Tests
# ============================================================================

class TestCommandAllowlist:
    """Tests for CommandAllowlist class."""
    
    def test_default_allowlist_initialization(self):
        """Test that default allowlist is loaded correctly."""
        allowlist = CommandAllowlist()
        
        assert "aws" in allowlist.allowlist
        assert "kubectl" in allowlist.allowlist
        assert "terraform" in allowlist.allowlist
        assert "docker" in allowlist.allowlist
        assert "git" in allowlist.allowlist
        assert "ssh" in allowlist.allowlist
    
    def test_is_allowed_base_command(self):
        """Test that base commands in allowlist are allowed."""
        allowlist = CommandAllowlist()
        
        assert allowlist.is_allowed("aws")
        assert allowlist.is_allowed("kubectl")
        assert allowlist.is_allowed("terraform")
    
    def test_is_allowed_with_subcommand(self):
        """Test that allowed subcommands pass validation."""
        allowlist = CommandAllowlist()
        
        assert allowlist.is_allowed("aws ec2 describe-instances")
        assert allowlist.is_allowed("kubectl get pods")
        assert allowlist.is_allowed("docker ps")
        assert allowlist.is_allowed("git status")
    
    def test_is_not_allowed_forbidden_command(self):
        """Test that forbidden commands are rejected."""
        allowlist = CommandAllowlist()
        
        assert not allowlist.is_allowed("rm -rf /")
        assert not allowlist.is_allowed("curl http://evil.com")
        assert not allowlist.is_allowed("bash -c 'malicious code'")
    
    def test_is_not_allowed_forbidden_subcommand(self):
        """Test that forbidden subcommands are rejected."""
        allowlist = CommandAllowlist()
        
        # "delete" is not in the kubectl allowlist
        assert not allowlist.is_allowed("kubectl delete pod")
        # "apply" is not in the kubectl allowlist
        assert not allowlist.is_allowed("kubectl apply -f config.yaml")
    
    def test_is_allowed_with_flags(self):
        """Test that commands with flags are handled correctly."""
        allowlist = CommandAllowlist()
        
        assert allowlist.is_allowed("aws ec2 describe-instances --region us-east-1")
        assert allowlist.is_allowed("kubectl get pods -n default")
        assert allowlist.is_allowed("docker ps -a")
    
    def test_is_allowed_empty_command(self):
        """Test that empty commands are rejected."""
        allowlist = CommandAllowlist()
        
        assert not allowlist.is_allowed("")
        assert not allowlist.is_allowed("   ")
    
    def test_validate_or_raise_success(self):
        """Test that valid commands don't raise exceptions."""
        allowlist = CommandAllowlist()
        
        # Should not raise
        allowlist.validate_or_raise("aws ec2 describe-instances")
        allowlist.validate_or_raise("kubectl get pods")
    
    def test_validate_or_raise_forbidden(self):
        """Test that forbidden commands raise ForbiddenCommandError."""
        allowlist = CommandAllowlist()
        
        with pytest.raises(ForbiddenCommandError) as exc_info:
            allowlist.validate_or_raise("rm -rf /")
        
        assert "rm" in str(exc_info.value)
    
    def test_validate_or_raise_forbidden_subcommand(self):
        """Test that forbidden subcommands raise ForbiddenCommandError."""
        allowlist = CommandAllowlist()
        
        with pytest.raises(ForbiddenCommandError) as exc_info:
            allowlist.validate_or_raise("kubectl delete pod")
        
        assert "kubectl" in str(exc_info.value)
    
    def test_add_command(self):
        """Test adding a new command to allowlist."""
        allowlist = CommandAllowlist()
        
        allowlist.add_command("gcloud", ["compute", "storage"])
        
        assert "gcloud" in allowlist.allowlist
        assert allowlist.is_allowed("gcloud compute instances list")
    
    def test_remove_command(self):
        """Test removing a command from allowlist."""
        allowlist = CommandAllowlist()
        
        allowlist.remove_command("ssh")
        
        assert "ssh" not in allowlist.allowlist
        assert not allowlist.is_allowed("ssh user@host")
    
    def test_get_allowed_commands(self):
        """Test getting a copy of the allowlist."""
        allowlist = CommandAllowlist()
        
        commands = allowlist.get_allowed_commands()
        
        assert isinstance(commands, dict)
        assert "aws" in commands
        
        # Verify it's a copy (modifying it doesn't affect original)
        commands["test"] = ["test"]
        assert "test" not in allowlist.allowlist
    
    def test_save_to_file(self, tmp_path):
        """Test saving allowlist to file."""
        allowlist = CommandAllowlist()
        output_file = tmp_path / "allowlist.json"
        
        allowlist.save_to_file(str(output_file))
        
        assert output_file.exists()
        
        with open(output_file, 'r') as f:
            saved_data = json.load(f)
        
        assert "aws" in saved_data
        assert "kubectl" in saved_data
    
    def test_load_from_custom_file(self, tmp_path):
        """Test loading allowlist from custom file."""
        custom_allowlist = {
            "custom_tool": ["cmd1", "cmd2"],
            "another_tool": ["action1"]
        }
        
        config_file = tmp_path / "custom_allowlist.json"
        with open(config_file, 'w') as f:
            json.dump(custom_allowlist, f)
        
        allowlist = CommandAllowlist(config_path=str(config_file))
        
        assert "custom_tool" in allowlist.allowlist
        assert "another_tool" in allowlist.allowlist
        assert allowlist.is_allowed("custom_tool cmd1")


# ============================================================================
# SubprocessRunner Tests
# ============================================================================

class TestSubprocessRunner:
    """Tests for SubprocessRunner class."""
    
    def test_initialization(self):
        """Test runner initialization with default timeout."""
        runner = SubprocessRunner(default_timeout=60)
        
        assert runner.default_timeout == 60
        assert isinstance(runner.restricted_env, dict)
        assert "PATH" in runner.restricted_env
    
    def test_restricted_env_creation(self):
        """Test that restricted environment is created correctly."""
        runner = SubprocessRunner()
        
        # Should have PATH
        assert "PATH" in runner.restricted_env
        
        # Should preserve cloud credentials if present
        # (These may or may not be present depending on test environment)
        env = runner.restricted_env
        assert isinstance(env, dict)
    
    @pytest.mark.asyncio
    async def test_run_success(self):
        """Test successful command execution."""
        runner = SubprocessRunner()
        
        # Use a simple command that should work on all platforms
        result = await runner.run("echo hello")
        
        assert result["command"] == "echo hello"
        assert "hello" in result["stdout"]
        assert result["exit_code"] == 0
        assert result["duration_ms"] > 0
    
    @pytest.mark.asyncio
    async def test_run_with_stderr(self):
        """Test command that produces stderr output."""
        runner = SubprocessRunner()
        
        # This command should produce stderr (command not found or similar)
        result = await runner.run("ls /nonexistent_directory_12345")
        
        assert result["exit_code"] != 0
        assert len(result["stderr"]) > 0
    
    @pytest.mark.asyncio
    async def test_run_with_timeout(self):
        """Test that timeout is enforced."""
        runner = SubprocessRunner()
        
        # Use a command that will timeout
        with pytest.raises(ToolExecutionTimeout) as exc_info:
            await runner.run("sleep 10", timeout=1)
        
        assert "timed out" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_run_empty_command(self):
        """Test that empty command raises error."""
        runner = SubprocessRunner()
        
        with pytest.raises(ToolExecutionError):
            await runner.run("")
    
    @pytest.mark.asyncio
    async def test_run_with_custom_env(self):
        """Test command execution with custom environment variables."""
        runner = SubprocessRunner()
        
        # Set a custom environment variable
        custom_env = {"TEST_VAR": "test_value"}
        
        # This test is platform-dependent, so we just verify it doesn't crash
        result = await runner.run("echo test", env=custom_env)
        
        assert result["exit_code"] == 0
    
    @pytest.mark.asyncio
    async def test_run_with_input(self):
        """Test command execution with stdin input."""
        runner = SubprocessRunner()
        
        # Use cat command which reads from stdin
        result = await runner.run_with_input("cat", stdin_data="hello world")
        
        assert "hello world" in result["stdout"]
        assert result["exit_code"] == 0


# ============================================================================
# ToolResult Tests
# ============================================================================

class TestToolResult:
    """Tests for ToolResult data model."""
    
    def test_initialization(self):
        """Test ToolResult initialization."""
        result = ToolResult(
            command="aws ec2 describe-instances",
            stdout='{"Reservations": []}',
            stderr="",
            exit_code=0,
            duration_ms=1500
        )
        
        assert result.command == "aws ec2 describe-instances"
        assert result.exit_code == 0
        assert result.duration_ms == 1500
        assert result.timestamp is not None
    
    def test_is_success(self):
        """Test is_success method."""
        success_result = ToolResult(
            command="test",
            stdout="output",
            stderr="",
            exit_code=0,
            duration_ms=100
        )
        
        failure_result = ToolResult(
            command="test",
            stdout="",
            stderr="error",
            exit_code=1,
            duration_ms=100
        )
        
        assert success_result.is_success()
        assert not failure_result.is_success()
    
    def test_has_output(self):
        """Test has_output method."""
        with_stdout = ToolResult(
            command="test",
            stdout="output",
            stderr="",
            exit_code=0,
            duration_ms=100
        )
        
        with_stderr = ToolResult(
            command="test",
            stdout="",
            stderr="error",
            exit_code=1,
            duration_ms=100
        )
        
        no_output = ToolResult(
            command="test",
            stdout="",
            stderr="",
            exit_code=0,
            duration_ms=100
        )
        
        assert with_stdout.has_output()
        assert with_stderr.has_output()
        assert not no_output.has_output()
    
    def test_to_dict(self):
        """Test to_dict conversion."""
        result = ToolResult(
            command="test",
            stdout="output",
            stderr="",
            exit_code=0,
            duration_ms=100,
            parsed_output={"key": "value"},
            anomalies=["warning1"]
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["command"] == "test"
        assert result_dict["exit_code"] == 0
        assert result_dict["parsed_output"] == {"key": "value"}
        assert result_dict["anomalies"] == ["warning1"]


# ============================================================================
# ToolExecutor Tests
# ============================================================================

class TestToolExecutor:
    """Tests for ToolExecutor class."""
    
    def test_initialization(self):
        """Test ToolExecutor initialization."""
        executor = ToolExecutor()
        
        assert executor.allowlist is not None
        assert executor.runner is not None
        assert isinstance(executor.audit_log, list)
    
    def test_initialization_with_custom_components(self):
        """Test initialization with custom allowlist and runner."""
        custom_allowlist = CommandAllowlist()
        custom_runner = SubprocessRunner(default_timeout=60)
        
        executor = ToolExecutor(
            allowlist=custom_allowlist,
            runner=custom_runner
        )
        
        assert executor.allowlist is custom_allowlist
        assert executor.runner is custom_runner
    
    @pytest.mark.asyncio
    async def test_run_success(self):
        """Test successful command execution through ToolExecutor."""
        allowlist = CommandAllowlist()
        allowlist.add_command("echo", [])
        executor = ToolExecutor(allowlist=allowlist)
        
        result = await executor.run("echo hello")
        
        assert isinstance(result, ToolResult)
        assert result.is_success()
        assert "hello" in result.stdout
        
        # Check audit log
        assert len(executor.audit_log) == 1
        assert executor.audit_log[0]["command"] == "echo hello"
        assert executor.audit_log[0]["exit_code"] == 0
    
    @pytest.mark.asyncio
    async def test_run_forbidden_command(self):
        """Test that forbidden commands are blocked."""
        executor = ToolExecutor()
        
        with pytest.raises(ForbiddenCommandError):
            await executor.run("rm -rf /")
        
        # Check audit log records the forbidden attempt
        assert len(executor.audit_log) == 1
        assert executor.audit_log[0]["command"] == "rm -rf /"
        assert executor.audit_log[0]["exit_code"] == -1
        assert "error" in executor.audit_log[0]
    
    @pytest.mark.asyncio
    async def test_run_with_timeout(self):
        """Test timeout enforcement through ToolExecutor."""
        allowlist = CommandAllowlist()
        allowlist.add_command("sleep", [])
        executor = ToolExecutor(allowlist=allowlist)
        
        with pytest.raises(ToolExecutionTimeout):
            await executor.run("sleep 10", timeout=1)
        
        # Check audit log
        assert len(executor.audit_log) == 1
        assert "error" in executor.audit_log[0]
    
    @pytest.mark.asyncio
    async def test_run_with_input(self):
        """Test command execution with stdin through ToolExecutor."""
        allowlist = CommandAllowlist()
        allowlist.add_command("cat", [])
        executor = ToolExecutor(allowlist=allowlist)
        
        result = await executor.run_with_input("cat", stdin_data="test input")
        
        assert isinstance(result, ToolResult)
        assert "test input" in result.stdout
        
        # Check audit log
        assert len(executor.audit_log) == 1
        assert "stdin_length" in executor.audit_log[0]
    
    def test_get_audit_log(self):
        """Test getting audit log."""
        executor = ToolExecutor()
        
        # Add some entries
        executor.audit_log.append({"command": "test1", "exit_code": 0})
        executor.audit_log.append({"command": "test2", "exit_code": 1})
        
        log = executor.get_audit_log()
        
        assert len(log) == 2
        assert log[0]["command"] == "test1"
        assert log[1]["command"] == "test2"
        
        # Verify it's a copy
        log.append({"command": "test3"})
        assert len(executor.audit_log) == 2
    
    def test_clear_audit_log(self):
        """Test clearing audit log."""
        executor = ToolExecutor()
        
        executor.audit_log.append({"command": "test", "exit_code": 0})
        assert len(executor.audit_log) == 1
        
        executor.clear_audit_log()
        assert len(executor.audit_log) == 0
    
    def test_get_allowed_commands(self):
        """Test getting allowed commands."""
        executor = ToolExecutor()
        
        commands = executor.get_allowed_commands()
        
        assert isinstance(commands, dict)
        assert "aws" in commands
        assert "kubectl" in commands


# ============================================================================
# Integration Tests
# ============================================================================

class TestToolExecutorIntegration:
    """Integration tests for the complete tool execution flow."""
    
    @pytest.mark.asyncio
    async def test_full_execution_flow(self):
        """Test complete execution flow from validation to result."""
        allowlist = CommandAllowlist()
        allowlist.add_command("echo", [])
        executor = ToolExecutor(allowlist=allowlist)
        
        # Execute a simple command
        result = await executor.run("echo integration test")
        
        # Verify result
        assert result.is_success()
        assert "integration test" in result.stdout
        assert result.duration_ms > 0
        assert result.timestamp is not None
        
        # Verify audit log
        audit_log = executor.get_audit_log()
        assert len(audit_log) == 1
        assert audit_log[0]["command"] == "echo integration test"
        assert audit_log[0]["exit_code"] == 0
    
    @pytest.mark.asyncio
    async def test_multiple_commands(self):
        """Test executing multiple commands in sequence."""
        allowlist = CommandAllowlist()
        allowlist.add_command("echo", [])
        executor = ToolExecutor(allowlist=allowlist)
        
        # Execute multiple commands
        result1 = await executor.run("echo first")
        result2 = await executor.run("echo second")
        
        assert result1.is_success()
        assert result2.is_success()
        assert "first" in result1.stdout
        assert "second" in result2.stdout
        
        # Verify audit log has both
        audit_log = executor.get_audit_log()
        assert len(audit_log) == 2
    
    @pytest.mark.asyncio
    async def test_error_handling_flow(self):
        """Test error handling throughout the execution flow."""
        allowlist = CommandAllowlist()
        allowlist.add_command("ls", [])
        executor = ToolExecutor(allowlist=allowlist)
        
        # Try forbidden command
        with pytest.raises(ForbiddenCommandError):
            await executor.run("malicious_command")
        
        # Try command that will fail
        result = await executor.run("ls /nonexistent_12345")
        assert not result.is_success()
        
        # Verify both are in audit log
        audit_log = executor.get_audit_log()
        assert len(audit_log) == 2
