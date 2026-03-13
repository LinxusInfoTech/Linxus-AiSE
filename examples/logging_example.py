#!/usr/bin/env python3
"""
Example demonstrating AiSE structured logging capabilities.

This script shows:
- Basic logging usage
- PII redaction
- API key masking
- Context variables
- Different log levels
- JSON vs console output
"""

from aise.core.logging import (
    setup_logging,
    get_logger,
    bind_context,
    clear_context,
    mask_sensitive_dict,
)


def demo_basic_logging():
    """Demonstrate basic structured logging."""
    print("\n=== Basic Logging Demo ===\n")
    
    logger = get_logger(__name__)
    
    # Simple log messages with structured data
    logger.info("Application started", version="0.1.0", environment="development")
    logger.debug("Debug information", module="example", function="demo_basic_logging")
    logger.warning("Resource usage high", cpu_percent=85, memory_mb=1500)
    logger.error("Connection failed", service="database", retry_count=3)


def demo_pii_redaction():
    """Demonstrate automatic PII redaction."""
    print("\n=== PII Redaction Demo ===\n")
    
    logger = get_logger(__name__)
    
    # These will be automatically redacted
    logger.info(
        "User registration",
        email="john.doe@example.com",  # Will be redacted
        phone="123-456-7890",  # Will be redacted
        ip="192.168.1.100",  # Will be redacted
        username="johndoe"  # Not PII, will remain
    )
    
    logger.info(
        "Payment processed",
        card="1234-5678-9012-3456",  # Will be redacted
        amount=99.99,
        currency="USD"
    )


def demo_api_key_masking():
    """Demonstrate API key masking."""
    print("\n=== API Key Masking Demo ===\n")
    
    logger = get_logger(__name__)
    
    # API keys will be masked
    logger.info(
        "API configuration",
        api_key="sk-proj-abc123xyz789defghi",  # Will be masked
        endpoint="https://api.example.com"
    )
    
    # Demonstrate mask_sensitive_dict utility
    config = {
        "anthropic_api_key": "sk-ant-abc123xyz789",
        "openai_api_key": "sk-proj-def456uvw012",
        "database_url": "postgresql://localhost:5432/aise",
        "redis_url": "redis://localhost:6379"
    }
    
    masked_config = mask_sensitive_dict(config)
    logger.info("Configuration loaded", config=masked_config)


def demo_context_variables():
    """Demonstrate context variable binding."""
    print("\n=== Context Variables Demo ===\n")
    
    logger = get_logger(__name__)
    
    # Bind context that will be included in all logs
    bind_context(request_id="req-12345", user_id="user-67890")
    
    logger.info("Processing request")
    logger.info("Fetching data from database")
    logger.info("Request completed successfully")
    
    # Clear context
    clear_context()
    
    logger.info("This log won't have the context")


def demo_different_log_levels():
    """Demonstrate different log levels."""
    print("\n=== Log Levels Demo ===\n")
    
    logger = get_logger(__name__)
    
    logger.debug("Detailed diagnostic information")
    logger.info("General informational message")
    logger.warning("Warning: something might be wrong")
    logger.error("Error: something went wrong")
    logger.critical("Critical: immediate action required")


def demo_exception_logging():
    """Demonstrate exception logging with stack traces."""
    print("\n=== Exception Logging Demo ===\n")
    
    logger = get_logger(__name__)
    
    try:
        # Simulate an error
        result = 1 / 0
    except ZeroDivisionError as e:
        logger.error(
            "Division by zero error",
            operation="divide",
            numerator=1,
            denominator=0,
            exc_info=True  # Include stack trace
        )


def main():
    """Run all logging demonstrations."""
    print("=" * 60)
    print("AiSE Structured Logging Examples")
    print("=" * 60)
    
    # Setup logging in development mode (pretty console)
    print("\n--- Development Mode (Pretty Console) ---")
    setup_logging(debug=True, enable_pii_redaction=True)
    
    demo_basic_logging()
    demo_pii_redaction()
    demo_api_key_masking()
    demo_context_variables()
    demo_different_log_levels()
    demo_exception_logging()
    
    # Setup logging in production mode (JSON)
    print("\n\n--- Production Mode (JSON Output) ---\n")
    setup_logging(log_level="INFO", json_output=True, enable_pii_redaction=True)
    
    logger = get_logger(__name__)
    logger.info(
        "Production log example",
        service="aise",
        environment="production",
        email="admin@example.com",  # Will be redacted
        api_key="sk-abc123xyz789"  # Will be masked
    )
    
    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
