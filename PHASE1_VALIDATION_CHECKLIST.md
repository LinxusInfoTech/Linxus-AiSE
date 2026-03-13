# Phase 1 Validation Checklist

## Automated Validation

Run the automated validation script:
```bash
./scripts/validate_phase1.sh
```

This script will automatically test:
- Docker Compose services (PostgreSQL, Redis, ChromaDB)
- Database connectivity
- CLI installation and commands
- Project structure
- Key implementation files
- Unit tests

## Manual Validation Checklist

### 1. Infrastructure

- [ ] `docker compose up` starts all services without errors
- [ ] PostgreSQL is accessible on port 5432
- [ ] Redis is accessible on port 6379
- [ ] ChromaDB is accessible on port 8000

### 2. Configuration System

- [ ] `aise config show` displays configuration with masked values
- [ ] `aise config show --reveal` shows unmasked sensitive values
- [ ] `aise config set LLM_PROVIDER openai` updates configuration
- [ ] `aise config get LLM_PROVIDER` retrieves configuration value
- [ ] `aise config validate` checks connectivity to services
- [ ] `aise config export` creates .env file
- [ ] `aise config import` loads configuration from file
- [ ] `aise config sources` shows configuration precedence
- [ ] System-level AWS credentials detected from ~/.aws/config
- [ ] System-level Kubernetes credentials detected from ~/.kube/config

### 3. Web Configuration UI

- [ ] Config UI accessible at http://localhost:8080/config
- [ ] Configuration values displayed organized by section
- [ ] Sensitive values masked by default
- [ ] "Show Sensitive Values" button reveals/hides values
- [ ] Configuration can be updated via UI
- [ ] Validation errors displayed with remediation guidance

### 4. Credential Vault

- [ ] Credentials encrypted with AES-256-GCM
- [ ] Credentials stored in PostgreSQL
- [ ] Credentials retrieved and decrypted correctly
- [ ] Audit logging for credential access

### 5. Knowledge Persistence

- [ ] Documentation metadata stored in PostgreSQL
- [ ] Vector embeddings stored in ChromaDB
- [ ] Knowledge survives system restart
- [ ] `aise learn --list` shows pre-configured sources

### 6. Documentation Registry

- [ ] Pre-configured sources: AWS, Azure, GCP, Kubernetes, Docker, Terraform, Git
- [ ] Each source has metadata (name, URL, description, category)
- [ ] Registry is extensible for custom sources

### 7. LLM Provider Support

- [ ] Anthropic Claude provider implemented
- [ ] OpenAI GPT-4 provider implemented
- [ ] DeepSeek provider implemented
- [ ] Ollama local provider implemented
- [ ] LLM router with failover logic
- [ ] Provider priority ordering

### 8. CLI Commands

- [ ] `aise --version` shows version
- [ ] `aise --help` shows help text
- [ ] `aise ask "test question"` returns response
- [ ] `aise learn --list` shows documentation sources
- [ ] All config commands work (show, get, set, validate, export, import, sources)

### 9. Browser Target URL Configuration

- [ ] Zendesk URL configuration in Config
- [ ] Freshdesk URL configuration in Config
- [ ] Custom support URL configuration in Config
- [ ] URL validation before saving
- [ ] Browser test endpoint works

### 10. Tests

- [ ] Unit tests pass: `poetry run pytest tests/unit/`
- [ ] Integration tests pass: `poetry run pytest tests/integration/`
- [ ] Property-based tests pass: `poetry run pytest tests/property/`

## Success Criteria

All items in this checklist must be checked before Phase 1 is considered complete.

## Next Steps

After Phase 1 validation passes:
1. Commit all changes
2. Tag release as `v0.1.0-phase1`
3. Begin Phase 2: Documentation Learning System
