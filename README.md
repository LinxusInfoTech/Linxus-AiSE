# AI Support Engineer System (AiSE)

Production-grade autonomous AI agent that functions as a senior cloud support engineer.

## Features

- **Multi-LLM Support**: Claude, GPT-4, DeepSeek, Ollama with automatic failover
- **Ticket Automation**: Zendesk, Freshdesk, Email, Slack integrations
- **Documentation Learning**: RAG-based knowledge retrieval from official docs
- **Secure Tool Execution**: Allowlist-enforced CLI execution (AWS, kubectl, terraform, docker, git)
- **Browser Automation**: Playwright-based fallback for ticket systems
- **Three Operational Modes**: Interactive, Approval-required, Fully Autonomous
- **Web Configuration UI**: No-code setup for non-technical users
- **Encrypted Credential Vault**: AES-256-GCM encryption for sensitive data
- **Full Observability**: OpenTelemetry tracing, Prometheus metrics, LangSmith integration

## Quick Start

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- At least one LLM provider API key

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd aise

# Install dependencies with Poetry
poetry install

# Copy environment template
cp .env.example .env

# Edit .env and add your API keys
nano .env

# Start infrastructure services
docker compose up -d

# Run database migrations
poetry run python -m aise.core.init_db

# Install Playwright browsers (if using browser automation)
poetry run playwright install
```

### Configuration

AiSE supports multiple configuration methods with the following precedence:

1. Environment variables (highest priority)
2. .env file in project directory
3. Config UI database settings
4. System-level config files (~/.aws/config, ~/.kube/config, etc.)
5. Default values (lowest priority)

**System-Level Credential Detection**: AiSE automatically detects credentials from:
- AWS: `~/.aws/credentials`, `~/.aws/config`, `AWS_PROFILE`, IAM role
- Kubernetes: `KUBECONFIG`, `~/.kube/config`
- SSH: `~/.ssh/config`
- Docker: `~/.docker/config.json`

**CLI Configuration Commands**:
```bash
aise config show                    # Display current configuration (masked)
aise config show --reveal           # Display with unmasked values
aise config set LLM_PROVIDER openai # Set configuration value
aise config get LLM_PROVIDER        # Get specific value
aise config validate                # Test connectivity to all services
aise config export                  # Export to .env format
aise config import config.env       # Import from file
aise config sources                 # Show configuration provenance
```

### Usage

**Initialize documentation index** (first-time setup):
```bash
aise init                                   # Index all pre-configured sources
aise init --source aws                      # Index only AWS docs
aise init --force                           # Re-index everything
aise init --list                            # Show index status
```

**Ask a question**:
```bash
aise ask "Why is my EC2 instance unreachable?"
```

**Learn from documentation**:
```bash
aise learn --list                           # Show available sources
aise learn --enable aws                     # Learn from AWS docs
aise learn https://docs.example.com --source-name custom
```

**Manage tickets**:
```bash
aise ticket list                            # List open tickets
aise ticket show TICKET-123                 # Show ticket details
```

**Change operational mode**:
```bash
aise mode                                   # Show current mode
aise mode set approval                      # Set to approval mode
```

**Start daemon mode**:
```bash
aise start                                  # Run in background, process tickets
```

### Web Configuration UI

Access the configuration interface at `http://localhost:8080/config` to:
- Configure LLM providers with API key validation
- Set up ticket system integrations with connectivity tests
- Configure browser automation target URLs
- Manage encrypted credentials
- View system status and health

## Architecture

AiSE uses a modular architecture with:
- **LangGraph** for agent orchestration
- **FastAPI** for webhooks and web UI
- **PostgreSQL** for conversation memory and metadata
- **Redis** for caching
- **ChromaDB** for vector embeddings
- **Playwright** for browser automation

## License

[Your License Here]
