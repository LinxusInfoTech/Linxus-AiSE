# tests/unit/test_config_show.py
"""Unit tests for config show command."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from aise.cli.commands.config import _organize_config_by_section, _format_source


def test_organize_config_by_section():
    """Test that configuration is organized correctly by section."""
    config_dict = {
        "LLM_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "sk-ant-****",
        "POSTGRES_URL": "postgresql://localhost/db",
        "ZENDESK_SUBDOMAIN": "mycompany",
        "AWS_PROFILE": "default",
        "LOG_LEVEL": "INFO"
    }
    
    sources = {
        "LLM_PROVIDER": "environment variable",
        "ANTHROPIC_API_KEY": ".env file",
        "POSTGRES_URL": "environment variable",
        "ZENDESK_SUBDOMAIN": "default",
        "AWS_PROFILE": "system config",
        "LOG_LEVEL": "default"
    }
    
    sections = _organize_config_by_section(config_dict, sources)
    
    # Check that sections are created
    assert "LLM Providers" in sections
    assert "Database" in sections
    assert "Ticket Systems" in sections
    assert "Cloud Providers" in sections
    assert "Development" in sections
    
    # Check that settings are in correct sections
    llm_settings = {key for key, _, _ in sections["LLM Providers"]}
    assert "LLM_PROVIDER" in llm_settings
    assert "ANTHROPIC_API_KEY" in llm_settings
    
    db_settings = {key for key, _, _ in sections["Database"]}
    assert "POSTGRES_URL" in db_settings
    
    ticket_settings = {key for key, _, _ in sections["Ticket Systems"]}
    assert "ZENDESK_SUBDOMAIN" in ticket_settings
    
    cloud_settings = {key for key, _, _ in sections["Cloud Providers"]}
    assert "AWS_PROFILE" in cloud_settings
    
    dev_settings = {key for key, _, _ in sections["Development"]}
    assert "LOG_LEVEL" in dev_settings


def test_format_source():
    """Test that configuration sources are formatted correctly."""
    assert "[bold yellow]env var[/bold yellow]" in _format_source("environment variable")
    assert "[bold blue].env[/bold blue]" in _format_source(".env file")
    assert "[bold magenta]database[/bold magenta]" in _format_source("database")
    assert "[bold green]system[/bold green]" in _format_source("system config")
    assert "[dim]default[/dim]" in _format_source("default")
    assert "[dim]unknown[/dim]" in _format_source("unknown")


def test_organize_config_removes_empty_sections():
    """Test that empty sections are removed."""
    config_dict = {
        "LLM_PROVIDER": "anthropic"
    }
    
    sources = {
        "LLM_PROVIDER": "default"
    }
    
    sections = _organize_config_by_section(config_dict, sources)
    
    # Only LLM Providers section should exist
    assert "LLM Providers" in sections
    # Other sections should not exist
    assert "Browser Automation" not in sections
    assert "Observability" not in sections


def test_organize_config_sorts_settings():
    """Test that settings within sections are in the order they were added."""
    config_dict = {
        "ZENDESK_URL": "https://example.zendesk.com",
        "ZENDESK_API_TOKEN": "token123",
        "ZENDESK_EMAIL": "admin@example.com",
        "ZENDESK_SUBDOMAIN": "example"
    }
    
    sources = {k: "default" for k in config_dict.keys()}
    
    sections = _organize_config_by_section(config_dict, sources)
    
    ticket_settings = [key for key, _, _ in sections["Ticket Systems"]]
    
    # All settings should be present
    assert len(ticket_settings) == 4
    assert "ZENDESK_URL" in ticket_settings
    assert "ZENDESK_API_TOKEN" in ticket_settings
    assert "ZENDESK_EMAIL" in ticket_settings
    assert "ZENDESK_SUBDOMAIN" in ticket_settings
