# tests/unit/test_learn_command.py
"""Unit tests for aise learn command."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from typer.testing import CliRunner

from aise.cli.app import app


runner = CliRunner()


def test_learn_list_command():
    """Test that learn list command executes without errors."""
    with patch('aise.cli.commands.learn.get_registry') as mock_registry:
        # Mock registry to return empty list
        mock_reg = Mock()
        mock_reg.list_sources.return_value = []
        mock_registry.return_value = mock_reg
        
        result = runner.invoke(app, ["learn", "list"])
        
        # Should not crash
        assert result.exit_code == 0
        assert "No documentation sources found" in result.stdout


def test_learn_url_command_requires_arguments():
    """Test that learn url command requires --url and --source-name."""
    result = runner.invoke(app, ["learn", "url"])
    
    # Should fail without required arguments
    assert result.exit_code != 0
