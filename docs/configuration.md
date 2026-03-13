# Configuration Management

## Overview

AiSE uses a comprehensive configuration system built on Pydantic Settings that supports multiple configuration sources with clear precedence rules and automatic system-level credential detection.

## Configuration Precedence

Configuration values are loaded in the following order (highest to lowest priority):

1. **Environment variables** (highest priority)
2. **.env file** in project directory
3. **Config UI database settings** (future feature)
4. **System-level config files** (~/.aws/config, ~/.kube/config, ~/.ssh/config, ~/.docker/config.json)
5. **Default values** (lowest priority)

## System-Level Credential Detection

AiSE automatically detects credentials from standard system locations, eliminating the need to duplicate credentials:

### AWS Credentials
- Environment variables: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- AWS profile: `AWS_PROFILE` environment variable
- Credentials file: `~/.aws/credentials`
- Config file: `~/.aws/config`
- IAM role (when running on EC2/ECS)

### Kubernetes Credentials
- Environment variable: `KUBECONFIG`
- Default location: `~/.kube/config`

### SSH Configuration
- Default location: `~/.ssh/config`

### Docker Configuration
- Default location: `~/.docker/config.json`

## Required Configuration

The following configuration values are **required** for AiSE to start:

### Database Configuration
```bash
POSTGRES_URL=postgresql://aise:password@localhost:5432/aise
REDIS_URL=redis://localhost:6379/0
```

### LLM Provider
At least one LLM provider must be configured:

```bash
# Choose one or more:
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=...
# Or use local Ollama:
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
```

## Configuration Sections

### LLM Provider Configuration

```bash
# Primary LLM provider: anthropic, openai, deepseek, or ollama
LLM_PROVIDER=anthropic

# Provider API keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=...
OLLAMA_BASE_URL=http://localhost:11434
```

### Operational Mode

```bash
# Mode: interactive, approval, or autonomous
AISE_MODE=approval
```

- **interactive**: Respond to CLI commands only
- **approval**: Pause before executing tools or posting replies (recommended)
- **autonomous**: Execute all operations without human intervention

### Database Configuration

```bash
POSTGRES_URL=postgresql://aise:password@localhost:5432/aise
REDIS_URL=redis://localhost:6379/0
CHROMA_HOST=localhost
CHROMA_PORT=8000
```

### Ticket System Configuration

Configure at least one ticket system integration:

#### Zendesk
```bash
ZENDESK_SUBDOMAIN=mycompany
ZENDESK_EMAIL=admin@mycompany.com
ZENDESK_API_TOKEN=...
ZENDESK_URL=https://mycompany.zendesk.com  # Optional, overrides subdomain
```

#### Freshdesk
```bash
FRESHDESK_DOMAIN=mycompany.freshdesk.com
FRESHDESK_API_KEY=...
FRESHDESK_URL=https://mycompany.freshdesk.com  # Optional, overrides domain
```

#### Email (IMAP/SMTP)
```bash
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993
EMAIL_IMAP_USERNAME=support@mycompany.com
EMAIL_IMAP_PASSWORD=...
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=support@mycompany.com
EMAIL_SMTP_PASSWORD=...
```

#### Slack
```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
```

### Browser Automation Configuration

```bash
# Enable browser fallback when APIs are unavailable
USE_BROWSER_FALLBACK=false

# Run browser in headless mode
BROWSER_HEADLESS=true

# Browser target URLs (only required if USE_BROWSER_FALLBACK=true)
ZENDESK_URL=https://mycompany.zendesk.com
FRESHDESK_URL=https://mycompany.freshdesk.com
CUSTOM_SUPPORT_URL=https://support.mycompany.com
```

### Cloud Provider Credentials

These are **automatically detected** from system-level configurations. Only set if you want to override:

```bash
# AWS (auto-detected from ~/.aws/config, ~/.aws/credentials)
# AWS_PROFILE=default
# AWS_DEFAULT_REGION=us-east-1
# AWS_ACCESS_KEY_ID=...
# AWS_SECRET_ACCESS_KEY=...

# Kubernetes (auto-detected from KUBECONFIG or ~/.kube/config)
# KUBECONFIG=/path/to/kubeconfig

# Google Cloud (auto-detected from gcloud CLI)
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# Azure (auto-detected from az CLI)
# AZURE_CONFIG_DIR=~/.azure
```

### Observability Configuration

```bash
LANGSMITH_API_KEY=...  # Optional
OTEL_EXPORTER_OTLP_ENDPOINT=...  # Optional
PROMETHEUS_PORT=9090
```

### Security Configuration

```bash
# Encryption key for credential vault (required for production)
CREDENTIAL_VAULT_KEY=...  # Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"

# Webhook signature secret
WEBHOOK_SECRET=...

# IP allowlist for webhook sources (comma-separated, optional)
# WEBHOOK_ALLOWED_IPS=192.168.1.0/24,10.0.0.0/8
```

### Tool Execution Configuration

```bash
TOOL_EXECUTION_TIMEOUT=30
MAX_CONCURRENT_TOOLS=5
```

### Knowledge Engine Configuration

```bash
EMBEDDING_MODEL=openai  # or sentence-transformers
LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2
MAX_CRAWL_PAGES=1000
MAX_CRAWL_DEPTH=3
CHUNK_SIZE=1000
CHUNK_OVERLAP=150
```

### Web UI Configuration

```bash
CONFIG_UI_PORT=8080
WEBHOOK_SERVER_PORT=8000
```

### Development Configuration

```bash
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
DEBUG=false
```

## Using the Config Class

### Loading Configuration

```python
from aise.core.config import load_config, get_config

# Load configuration (call once at startup)
config = load_config()

# Get configuration anywhere in the application
config = get_config()
```

### Accessing Configuration Values

```python
config = get_config()

# Access configuration values
llm_provider = config.LLM_PROVIDER
postgres_url = config.POSTGRES_URL
mode = config.AISE_MODE
```

### Masking Sensitive Values

```python
# Mask a sensitive value
masked = Config.mask_sensitive_value("sk-ant-1234567890abcdef")
# Returns: "sk-a****cdef"

# Get configuration as dictionary with masked values
config_dict = config.to_dict(mask_sensitive=True)

# Get configuration with revealed values
config_dict = config.to_dict(mask_sensitive=False)
```

### Tracking Configuration Sources

```python
# Get the source of each configuration value
sources = config.get_config_sources()

# Example output:
# {
#     "POSTGRES_URL": "environment variable",
#     "REDIS_URL": ".env file",
#     "CHROMA_HOST": "default",
#     "AWS_PROFILE": "system config"
# }
```

### Detecting System Credentials

```python
# Detect system-level credentials
system_creds = config.detect_system_credentials()

# Example output:
# {
#     "aws": {
#         "detected": True,
#         "sources": ["~/.aws/credentials", "~/.aws/config"],
#         "profile": "default",
#         "region": "us-east-1"
#     },
#     "kubernetes": {
#         "detected": True,
#         "path": "/home/user/.kube/config",
#         "source": "~/.kube/config"
#     }
# }
```

### Logging Configuration Sources

```python
# Log which configuration source is used for each value
config.log_configuration_sources()

# This will log:
# - Configuration loaded with sources grouped by type
# - System-level credentials detected
```

## CLI Configuration Commands (Future)

The following CLI commands will be available for configuration management:

```bash
# Display current configuration (masked)
aise config show

# Display with unmasked values
aise config show --reveal

# Set configuration value
aise config set LLM_PROVIDER openai

# Get specific configuration value
aise config get POSTGRES_URL

# Validate current configuration
aise config validate

# Export configuration to .env format
aise config export > .env.backup

# Import configuration from file
aise config import .env.backup

# Show configuration sources
aise config sources
```

## Validation

The Config class performs comprehensive validation:

### Required Fields
- `POSTGRES_URL` must be provided and start with `postgresql://` or `postgres://`
- `REDIS_URL` must be provided and start with `redis://`
- At least one LLM provider API key must be configured (unless using Ollama)

### LLM Provider Validation
- The selected `LLM_PROVIDER` must have corresponding credentials
- For `anthropic`, `openai`, or `deepseek`: API key is required
- For `ollama`: `OLLAMA_BASE_URL` is required

### Embedding Model Validation
- If `EMBEDDING_MODEL=openai`, then `OPENAI_API_KEY` is required

### Warnings
- If only one LLM provider is configured, a warning is logged suggesting fallback providers

## Environment Variables vs .env File

You can configure AiSE using either environment variables or a `.env` file:

### Using Environment Variables
```bash
export POSTGRES_URL="postgresql://aise:password@localhost:5432/aise"
export REDIS_URL="redis://localhost:6379/0"
export ANTHROPIC_API_KEY="sk-ant-..."
aise start
```

### Using .env File
Create a `.env` file in the project root:
```bash
POSTGRES_URL=postgresql://aise:password@localhost:5432/aise
REDIS_URL=redis://localhost:6379/0
ANTHROPIC_API_KEY=sk-ant-...
```

Then run:
```bash
aise start
```

## Best Practices

1. **Use .env for local development**: Keep sensitive credentials out of version control
2. **Use environment variables for production**: Set via container orchestration or secrets management
3. **Leverage system-level credentials**: Don't duplicate AWS, Kubernetes, or SSH credentials
4. **Configure multiple LLM providers**: Enable automatic failover for reliability
5. **Use approval mode initially**: Start with `AISE_MODE=approval` until you're confident
6. **Rotate credentials regularly**: Update API keys and encryption keys periodically
7. **Monitor configuration sources**: Use `config.log_configuration_sources()` to understand precedence

## Troubleshooting

### "POSTGRES_URL is required"
Ensure you've set the `POSTGRES_URL` environment variable or added it to your `.env` file.

### "API key for selected LLM provider 'anthropic' is not configured"
Set the `ANTHROPIC_API_KEY` environment variable or switch to a different provider.

### "OPENAI_API_KEY is required when EMBEDDING_MODEL is set to 'openai'"
Either set `OPENAI_API_KEY` or change `EMBEDDING_MODEL` to `sentence-transformers`.

### Configuration not loading from .env file
Ensure the `.env` file is in the project root directory and has proper formatting (no spaces around `=`).

## Security Considerations

1. **Never commit .env files**: Add `.env` to `.gitignore`
2. **Use credential vault**: Set `CREDENTIAL_VAULT_KEY` for encrypted storage
3. **Mask sensitive values**: Always use `mask_sensitive=True` when displaying configuration
4. **Audit configuration access**: Monitor who accesses sensitive configuration values
5. **Rotate encryption keys**: Periodically rotate `CREDENTIAL_VAULT_KEY` and re-encrypt credentials


## Credential Storage

AiSE provides a secure credential storage system that encrypts credentials at rest using AES-256-GCM encryption and stores them in PostgreSQL.

### Using CredentialStorage

```python
from aise.core.config import get_config
from aise.core.credential_vault import CredentialVault
from aise.core.credential_storage import CredentialStorage

# Initialize
config = get_config()
vault = CredentialVault(config)
storage = CredentialStorage(config, vault)
await storage.initialize()

# Store a credential (encrypted automatically)
await storage.store("zendesk_api_key", "your-secret-key", "api_key")

# Retrieve a credential (decrypted automatically)
api_key = await storage.retrieve("zendesk_api_key")

# List all stored credentials (metadata only, not values)
credentials = await storage.list_keys()

# Rotate a credential
await storage.rotate_key("zendesk_api_key", "new-secret-key")

# View audit log
audit_logs = await storage.get_audit_log("zendesk_api_key")

# Clean up
await storage.close()
```

### Database Schema

CredentialStorage creates two tables:

**credentials table:**
- `id`: Primary key
- `key`: Unique credential identifier
- `encrypted_value`: Encrypted credential (AES-256-GCM)
- `credential_type`: Type (api_key, password, token, ssh_key)
- `created_at`: Creation timestamp
- `updated_at`: Last update timestamp
- `accessed_at`: Last access timestamp
- `access_count`: Number of times accessed

**credential_audit_log table:**
- `id`: Primary key
- `credential_key`: Credential identifier
- `operation`: Operation performed (store, retrieve, delete, rotate)
- `component`: Component that performed the operation
- `timestamp`: Operation timestamp
- `success`: Whether operation succeeded
- `error_message`: Error message if failed

### Encryption Key Management

The encryption key is loaded in this priority order:

1. `CREDENTIAL_VAULT_KEY` environment variable
2. `~/.aise/vault.key` file
3. Auto-generated on first run (saved to `~/.aise/vault.key`)

**Production recommendation:** Use a key management system (AWS KMS, HashiCorp Vault, Azure Key Vault, Google Cloud KMS) and set `CREDENTIAL_VAULT_KEY` from there.

### Audit Logging

All credential operations are logged to the `credential_audit_log` table:

```python
# View all audit logs
all_logs = await storage.get_audit_log(limit=100)

# View logs for specific credential
key_logs = await storage.get_audit_log("zendesk_api_key", limit=50)
```

Each audit log entry includes:
- Credential key
- Operation type (store, retrieve, delete, rotate)
- Component that performed the operation
- Timestamp
- Success/failure status
- Error message (if failed)

### Security Best Practices

1. **Never commit .env files**: Add `.env` to `.gitignore`
2. **Use credential vault**: Set `CREDENTIAL_VAULT_KEY` for encrypted storage
3. **Use CredentialStorage for persistence**: Store credentials in PostgreSQL with encryption
4. **Mask sensitive values**: Always use `CredentialVault.mask_credential()` when displaying credentials
5. **Audit configuration access**: Monitor who accesses sensitive configuration values
6. **Rotate encryption keys periodically**: Use `CredentialStorage.rotate_key()` for key rotation
7. **Back up encryption key securely**: Store `CREDENTIAL_VAULT_KEY` in a key management system
8. **Review audit logs regularly**: Check `credential_audit_log` for unauthorized access attempts
9. **Use strong encryption keys**: Never use weak or predictable encryption keys
10. **Limit database access**: Restrict PostgreSQL access to only necessary components

### Example Usage

See `examples/credential_storage_example.py` for a complete working example demonstrating:
- Initialization
- Storing credentials
- Retrieving credentials
- Listing credentials
- Rotating credentials
- Viewing audit logs
- Cleanup
