# tests/unit/test_logging.py
"""Unit tests for structured logging."""

import pytest
import logging
import structlog
from aise.core.logging import setup_logging


def test_setup_logging_default():
    """Test default logging setup."""
    setup_logging()
    logger = structlog.get_logger()
    assert logger is not None


def test_setup_logging_debug():
    """Test debug logging setup."""
    setup_logging(debug=True)
    logger = structlog.get_logger()
    assert logger is not None


def test_setup_logging_custom_level():
    """Test custom log level."""
    setup_logging(log_level="WARNING")
    logger = structlog.get_logger()
    assert logger is not None


def test_get_logger():
    """Test getting a logger instance."""
    setup_logging()
    logger = structlog.get_logger("test_module")
    assert logger is not None
    assert hasattr(logger, "info")
    assert hasattr(logger, "error")
    assert hasattr(logger, "warning")
    assert hasattr(logger, "debug")


def test_logging_different_levels():
    """Test logging at different levels."""
    setup_logging(log_level="DEBUG")
    logger = structlog.get_logger("test")
    
    # These should not raise exceptions
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
