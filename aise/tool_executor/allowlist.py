# aise/tool_executor/allowlist.py
"""Command allowlist enforcement for secure tool execution.

This module implements the CommandAllowlist class that enforces which CLI commands
and subcommands are permitted for execution. This is a critical security feature
that prevents arbitrary command execution and command injection attacks.

Requirements:
- 9.1: Maintain allowlist of permitted commands and subcommands
- 9.2: Validate commands against allowlist before execution
- 9.4: Support AWS CLI, kubectl, terraform, docker, git, ssh
- 9.12: Make allowlist configurable without code changes
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
import structlog

from aise.core.exceptions import ForbiddenCommandError

logger = structlog.get_logger(__name__)


class CommandAllowlist:
    """Enforces allowed commands and subcommands for secure tool execution.
    
    The allowlist defines which CLI tools can be executed and which subcommands
    are permitted for each tool. Commands not in the allowlist are rejected
    with a ForbiddenCommandError.
    
    The allowlist can be loaded from:
    1. A JSON configuration file (for customization without code changes)
    2. Default built-in allowlist (if no config file exists)
    
    Example allowlist structure:
    {
        "aws": ["ec2", "s3", "iam", "cloudwatch", "logs"],
        "kubectl": ["get", "describe", "logs", "top"],
        "terraform": ["plan", "show", "state"],
        "docker": ["ps", "logs", "inspect", "stats"],
        "git": ["status", "log", "diff"],
        "ssh": []
    }
    
    Attributes:
        allowlist: Dictionary mapping command names to allowed subcommands
        config_path: Path to custom allowlist configuration file
    """
    
    # Default allowlist for common cloud infrastructure tools
    DEFAULT_ALLOWLIST: Dict[str, List[str]] = {
        "aws": [
            # EC2 commands
            "ec2", "describe-instances", "describe-security-groups",
            "describe-vpcs", "describe-subnets", "describe-volumes",
            # S3 commands
            "s3", "ls", "mb", "rb",
            # IAM commands
            "iam", "list-users", "list-roles", "get-user", "get-role",
            # CloudWatch commands
            "cloudwatch", "describe-alarms", "get-metric-statistics",
            # Logs commands
            "logs", "describe-log-groups", "describe-log-streams",
            "filter-log-events", "tail",
            # ECS commands
            "ecs", "list-clusters", "list-services", "describe-services",
            "describe-tasks",
            # EKS commands
            "eks", "list-clusters", "describe-cluster",
            # Lambda commands
            "lambda", "list-functions", "get-function",
            # RDS commands
            "rds", "describe-db-instances", "describe-db-clusters"
        ],
        "kubectl": [
            # Read-only commands
            "get", "describe", "logs", "top", "explain",
            # Cluster info
            "cluster-info", "version", "api-resources", "api-versions"
        ],
        "terraform": [
            # Read-only commands
            "plan", "show", "state", "list", "output", "version",
            "validate", "fmt", "graph"
        ],
        "docker": [
            # Read-only commands
            "ps", "logs", "inspect", "stats", "version", "info",
            "images", "network", "volume"
        ],
        "git": [
            # Read-only commands
            "status", "log", "diff", "show", "branch", "remote",
            "config", "rev-parse", "describe"
        ],
        "ssh": [
            # SSH requires explicit configuration per host
            # Empty list means SSH is allowed but must be configured
        ]
    }
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the command allowlist.
        
        Args:
            config_path: Optional path to custom allowlist JSON file.
                        If not provided, uses default allowlist.
        """
        self.config_path = Path(config_path) if config_path else None
        self.allowlist = self._load_allowlist()
        
        logger.info(
            "Command allowlist initialized",
            tools=list(self.allowlist.keys()),
            config_path=str(self.config_path) if self.config_path else "default"
        )
    
    def _load_allowlist(self) -> Dict[str, List[str]]:
        """Load allowlist from config file or use default.
        
        Returns:
            Dictionary mapping command names to allowed subcommands
        """
        # Try to load from config file if provided
        if self.config_path and self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    custom_allowlist = json.load(f)
                logger.info(
                    "Loaded custom allowlist from file",
                    path=str(self.config_path),
                    tools=list(custom_allowlist.keys())
                )
                return custom_allowlist
            except Exception as e:
                logger.warning(
                    "Failed to load custom allowlist, using default",
                    path=str(self.config_path),
                    error=str(e)
                )
        
        # Use default allowlist
        return self.DEFAULT_ALLOWLIST.copy()
    
    def is_allowed(self, command: str) -> bool:
        """Check if a command is allowed by the allowlist.
        
        This method parses the command string and checks if:
        1. The base command (first token) is in the allowlist
        2. If subcommands are specified, they are also allowed
        
        Args:
            command: Full command string to validate (e.g., "aws ec2 describe-instances")
        
        Returns:
            True if command is allowed, False otherwise
        
        Example:
            >>> allowlist.is_allowed("aws ec2 describe-instances")
            True
            >>> allowlist.is_allowed("rm -rf /")
            False
        """
        if not command or not command.strip():
            return False
        
        # Parse command into tokens
        tokens = command.strip().split()
        if not tokens:
            return False
        
        base_command = tokens[0]
        
        # Check if base command is in allowlist
        if base_command not in self.allowlist:
            return False
        
        # Get allowed subcommands for this base command
        allowed_subcommands = self.allowlist[base_command]
        
        # If allowlist is empty, command is allowed but may require configuration
        # (e.g., SSH requires per-host configuration)
        if not allowed_subcommands:
            return True
        
        # Check if any subcommands in the command are allowed
        # We check all tokens after the base command
        for token in tokens[1:]:
            # Skip flags (starting with - or --)
            if token.startswith('-'):
                continue
            
            # Check if this token is an allowed subcommand
            if token in allowed_subcommands:
                return True
        
        # If we have subcommands defined but none matched, reject
        # This handles cases like "aws rm" where "rm" is not in the allowlist
        if len(tokens) > 1:
            # Check if the second token (likely the subcommand) is allowed
            potential_subcommand = tokens[1]
            if not potential_subcommand.startswith('-'):
                return potential_subcommand in allowed_subcommands
        
        # If only base command provided and we have subcommands defined,
        # allow it (e.g., "aws" by itself for help)
        return True
    
    def validate_or_raise(self, command: str) -> None:
        """Validate command against allowlist and raise exception if forbidden.
        
        This method should be called before executing any command to ensure
        it passes security validation.
        
        Args:
            command: Full command string to validate
        
        Raises:
            ForbiddenCommandError: If command is not in the allowlist
        
        Example:
            >>> allowlist.validate_or_raise("aws ec2 describe-instances")
            # No exception raised
            >>> allowlist.validate_or_raise("rm -rf /")
            ForbiddenCommandError: Command not allowed: rm -rf /
        """
        if not self.is_allowed(command):
            tokens = command.strip().split()
            base_command = tokens[0] if tokens else "unknown"
            
            if base_command not in self.allowlist:
                reason = f"Base command '{base_command}' not in allowlist"
            else:
                reason = f"Subcommand not permitted for '{base_command}'"
            
            logger.warning(
                "Forbidden command blocked",
                command=command,
                reason=reason
            )
            
            raise ForbiddenCommandError(command, reason)
        
        logger.debug("Command validated", command=command)
    
    def add_command(self, base_command: str, subcommands: List[str]) -> None:
        """Add a new command to the allowlist at runtime.
        
        This method allows dynamic modification of the allowlist without
        restarting the system. Use with caution as it affects security.
        
        Args:
            base_command: Base command name (e.g., "aws", "kubectl")
            subcommands: List of allowed subcommands
        
        Example:
            >>> allowlist.add_command("gcloud", ["compute", "storage"])
        """
        self.allowlist[base_command] = subcommands
        logger.info(
            "Command added to allowlist",
            base_command=base_command,
            subcommands=subcommands
        )
    
    def remove_command(self, base_command: str) -> None:
        """Remove a command from the allowlist at runtime.
        
        Args:
            base_command: Base command name to remove
        
        Example:
            >>> allowlist.remove_command("ssh")
        """
        if base_command in self.allowlist:
            del self.allowlist[base_command]
            logger.info("Command removed from allowlist", base_command=base_command)
    
    def get_allowed_commands(self) -> Dict[str, List[str]]:
        """Get a copy of the current allowlist.
        
        Returns:
            Dictionary mapping command names to allowed subcommands
        """
        return self.allowlist.copy()
    
    def save_to_file(self, path: str) -> None:
        """Save current allowlist to a JSON file.
        
        This allows persisting runtime modifications to the allowlist.
        
        Args:
            path: Path to save the allowlist JSON file
        
        Example:
            >>> allowlist.save_to_file("./config/allowlist.json")
        """
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(self.allowlist, f, indent=2)
        
        logger.info("Allowlist saved to file", path=str(output_path))
