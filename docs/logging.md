# Logging Best Practices

## Overview

AiSE uses structured logging with `structlog` to provide comprehensive, secure, and production-ready logging capabilities. The logging system includes automatic PII redaction, API key masking, and support for both development and production environments.

## Features

- **Structured Logging**: JSON output for production, pretty console for development
- **PII Redaction**: Automatic redaction of emails, phone numbers, IP addresses, credit cards
- **API Key Masking**: Shows only first and last 4 characters of API keys
- **Context Variables**: Support for request tracing and contextual logging
- **Multiple Log Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Exception Handling**: Automatic stack trace and exception formatting

## Quick Start

### Basic Usage

```python
from aise.core.logging import get_logger

logger = get_logger(__name__)

# Simple logging
logger.info("Processing ticket", ticket_id="12345")
logger.error("Failed to connect", service="postgres", error=str(e))
logger.warning("Rate limit approaching", current=95, limit=100)
```

### Configuration

```python
from aise.core.logging import setup_logging

# Development mode (pretty console output)
setup_logging(debug=True)

# Production mode (JSON output)
setup_logging(log_level="INFO", json_output=True)

# Custom configuration
setup_logging(
    log_level="WARNING",
    json_output=True,
    enable_pii_redaction=True
)
```

## PII Redaction

The logging system automatically redacts sensitive information:

### Supported PII Types

1. **Email Addresses**: `user@example.com` → `[EMAIL_REDACTED]`
2. **Phone Numbers**: `123-456-7890` → `[PHONE_REDACTED]`
3. **IP Addresses**: `192.168.1.1` → `[IP_REDACTED]`
4. **Credit Cards**: `1234-5678-9012-3456` → `[CC_REDACTED]`
5. **API Keys**: `sk-abc123xyz789` → `sk-a****x789`


### Example

```python
logger.info(
    "User login",
    email="john@example.com",  # Will be redacted
    ip="192.168.1.100"  # Will be redacted
)
# Output: {"event": "User login", "email": "[EMAIL_REDACTED]", "ip": "[IP_REDACTED]"}
```

## API Key Masking

API keys are automatically masked to show only the first and last 4 characters:

```python
from aise.core.logging import mask_api_key

key = "sk-proj-abc123xyz789defghi"
masked = mask_api_key(key)
print(masked)  # "sk-p****fghi"
```

## Context Variables

Use context variables for request tracing and adding metadata to all logs:

```python
from aise.core.logging import bind_context, unbind_context, clear_context

# Bind context for all subsequent logs
bind_context(request_id="abc-123", user_id="user-456")

logger.info("Processing request")
# Output includes: {"request_id": "abc-123", "user_id": "user-456", ...}

# Unbind specific keys
unbind_context("user_id")

# Clear all context
clear_context()
```

## Log Levels

Configure appropriate log levels for different environments:

- **DEBUG**: Detailed diagnostic information (development only)
- **INFO**: General informational messages (default)
- **WARNING**: Warning messages for potentially harmful situations
- **ERROR**: Error messages for serious problems
- **CRITICAL**: Critical messages for very serious errors


## Production Configuration

For production deployments, use JSON output for container log aggregation:

```python
# In your application startup
from aise.core.logging import setup_logging
from aise.core.config import get_config

config = get_config()
setup_logging(
    log_level=config.LOG_LEVEL,
    json_output=True,  # JSON for log aggregation
    enable_pii_redaction=True  # Always enable in production
)
```

### Docker/Kubernetes

The JSON output format is optimized for log aggregation systems like:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Splunk
- CloudWatch Logs
- Datadog
- Grafana Loki

## Development Configuration

For local development, use pretty console output:

```python
from aise.core.logging import setup_logging

setup_logging(debug=True)  # Pretty console with colors
```

## Masking Sensitive Dictionaries

Use `mask_sensitive_dict` to mask sensitive values in configuration or data:

```python
from aise.core.logging import mask_sensitive_dict

config = {
    "api_key": "sk-abc123xyz789",
    "username": "john",
    "password": "secret123",
    "endpoint": "https://api.example.com"
}

masked = mask_sensitive_dict(config)
# Output: {
#     "api_key": "sk-a****x789",
#     "username": "john",
#     "password": "secr****t123",
#     "endpoint": "https://api.example.com"
# }
```


## Best Practices

### 1. Use Structured Logging

Always use key-value pairs instead of string formatting:

```python
# Good ✓
logger.info("User login", user_id=user_id, ip=ip_address)

# Bad ✗
logger.info(f"User {user_id} logged in from {ip_address}")
```

### 2. Include Context

Add relevant context to help with debugging:

```python
logger.error(
    "Database connection failed",
    database="postgres",
    host=db_host,
    port=db_port,
    error=str(e),
    retry_count=retry_count
)
```

### 3. Use Appropriate Log Levels

- Use `DEBUG` for detailed diagnostic information
- Use `INFO` for general operational messages
- Use `WARNING` for potentially harmful situations
- Use `ERROR` for errors that need attention
- Use `CRITICAL` for severe errors requiring immediate action

### 4. Bind Context for Request Tracing

```python
from aise.core.logging import bind_context, clear_context

def process_ticket(ticket_id):
    bind_context(ticket_id=ticket_id)
    try:
        logger.info("Starting ticket processing")
        # All logs will include ticket_id
        # ...
    finally:
        clear_context()
```

### 5. Never Log Sensitive Data Directly

The PII redaction is automatic, but be mindful:

```python
# The system will redact, but be explicit when possible
logger.info("User registered", email="[REDACTED]", user_id=user_id)
```

## Security Considerations

1. **Always Enable PII Redaction in Production**: Set `enable_pii_redaction=True`
2. **Review Logs Regularly**: Ensure no sensitive data leaks through
3. **Use Secure Log Storage**: Encrypt logs at rest and in transit
4. **Implement Log Retention Policies**: Delete old logs per compliance requirements
5. **Restrict Log Access**: Limit who can view production logs

## Troubleshooting

### Logs Not Appearing

Check log level configuration:
```python
setup_logging(log_level="DEBUG")  # Lower the threshold
```

### PII Not Being Redacted

Ensure PII redaction is enabled:
```python
setup_logging(enable_pii_redaction=True)
```

### JSON Output Not Working

Force JSON output:
```python
setup_logging(json_output=True, debug=False)
```

## Integration with Config

The logging system integrates with AiSE configuration:

```python
from aise.core.config import load_config
from aise.core.logging import setup_logging

config = load_config()
setup_logging(
    log_level=config.LOG_LEVEL,
    debug=config.DEBUG,
    json_output=not config.DEBUG
)
```
