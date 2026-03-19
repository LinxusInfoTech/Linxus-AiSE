# AI Support Engineer System (AiSE)

Production-grade autonomous AI agent that acts as a senior cloud support engineer — diagnosing infrastructure issues, responding to support tickets, and executing safe CLI diagnostics.

## Features

- **Multi-LLM Support** — Claude, GPT-4, DeepSeek, Ollama with automatic failover and circuit breakers
- **Ticket Automation** — Zendesk, Freshdesk, Email (IMAP/SMTP), Slack integrations
- **Documentation Learning** — RAG-based knowledge retrieval from official cloud docs
- **Secure Tool Execution** — Allowlist-enforced CLI execution (AWS, kubectl, terraform, docker, git, ssh)
- **Browser Automation** — Playwright-based fallback when ticket APIs are unavailable
- **Three Operational Modes** — Interactive, Approval-required, Fully Autonomous
- **Web Configuration UI** — No-code setup at `http://localhost:8080/config`
- **Encrypted Credential Vault** — AES-256-GCM encryption for all sensitive data
- **Full Observability** — OpenTelemetry tracing, Prometheus metrics, LangSmith integration
- **Security Hardening** — HMAC webhook verification, IP allowlisting, per-ticket rate limiting, audit logging

## Quick Start

### Prerequisites

- Python 3.11+
- Docker and Docker Compose
- At least one LLM provider API key (Anthropic, OpenAI, DeepSeek, or local Ollama)

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd aise

# Install dependencies with Poetry
pip install poetry
poetry install

# Copy environment template and add your API keys
cp .env.example .env
nano .env          # Set LLM_PROVIDER and at least one API key

# Start infrastructure (PostgreSQL, Redis, ChromaDB)
docker compose up -d

# Verify services are healthy
docker compose ps
```

### Minimal .env configuration

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

POSTGRES_URL=postgresql://aise:aise@localhost:5432/aise
REDIS_URL=redis://localhost:6379
CHROMA_HOST=localhost
CHROMA_PORT=8001
```

### First run

```bash
# Ask a question (no ticket system needed)
poetry run aise ask "Why is my EC2 instance unreachable?"

# Open the web configuration UI
poetry run aise start
# Then visit http://localhost:8080/config
```

## Configuration

AiSE supports multiple configuration methods with the following precedence (highest to lowest):

1. Environment variables
2. `.env` file in project directory
3. Config UI database settings
4. System-level config files (`~/.aws/config`, `~/.kube/config`, etc.)
5. Default values

**System-level credential auto-detection:**
- AWS: `~/.aws/credentials`, `~/.aws/config`, `AWS_PROFILE`, IAM role
- Kubernetes: `KUBECONFIG`, `~/.kube/config`
- SSH: `~/.ssh/config`
- Docker: `~/.docker/config.json`

**CLI configuration commands:**
```bash
aise config show                     # Display current config (values masked)
aise config show --reveal            # Show unmasked values
aise config set LLM_PROVIDER openai  # Update a value
aise config get LLM_PROVIDER         # Read a specific value
aise config validate                 # Test connectivity to all services
aise config sources                  # Show where each value comes from
aise config export > my.env          # Export to .env format
aise config import my.env            # Import from file
```

See [docs/configuration.md](docs/configuration.md) for the full reference.

## Usage

### Ask a question

```bash
aise ask "Why is my pod crashlooping?"
aise ask "How do I allow SSH in a security group?"
```

### Learn from documentation

```bash
aise learn --list                              # Show available sources and status
aise learn --enable aws                        # Learn from AWS docs
aise learn --enable kubernetes                 # Learn from Kubernetes docs
aise learn https://docs.example.com --source-name myapp
```

### Manage tickets

```bash
aise ticket list                               # List open tickets
aise ticket show TICKET-123                    # Show full ticket thread
```

### Operational modes

```bash
aise mode                                      # Show current mode
aise mode set interactive                      # Only respond to direct commands
aise mode set approval                         # Propose actions, wait for approval
aise mode set autonomous                       # Act without human approval
```

### Daemon mode (process tickets continuously)

```bash
aise start                                     # Start webhook server + ticket worker
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for a full description.

| Component | Technology |
|-----------|-----------|
| Agent orchestration | LangGraph |
| Web API / webhooks | FastAPI |
| Conversation memory | PostgreSQL + Redis |
| Vector embeddings | ChromaDB |
| Browser automation | Playwright |
| Metrics | Prometheus |
| Tracing | OpenTelemetry + LangSmith |

## Documentation

| Document | Description |
|----------|-------------|
| [docs/configuration.md](docs/configuration.md) | All configuration options |
| [docs/deployment.md](docs/deployment.md) | Docker Compose and production deployment |
| [docs/api.md](docs/api.md) | CLI commands and webhook API reference |
| [docs/architecture.md](docs/architecture.md) | System design and agent flow |
| [docs/webhook_server.md](docs/webhook_server.md) | Webhook integration guide |
| [docs/learn_command.md](docs/learn_command.md) | Documentation learning system |
| [docs/logging.md](docs/logging.md) | Structured logging and observability |

## License

[Your License Here]
