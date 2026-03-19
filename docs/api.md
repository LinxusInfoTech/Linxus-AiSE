# API Documentation

## CLI Commands

### `aise ask`

Ask a cloud infrastructure question. AiSE diagnoses the issue using its knowledge base and, in autonomous/approval mode, can execute safe CLI diagnostics.

```bash
aise ask "Why is my EC2 instance unreachable?"
aise ask "How do I allow SSH in a security group?"
aise ask "Why is my pod crashlooping?"
```

Options:
- `--provider TEXT` — Override the default LLM provider for this query
- `--no-stream` — Disable streaming output (wait for full response)

---

### `aise learn`

Crawl and index documentation into the knowledge base.

```bash
aise learn --list                                        # Show all available sources and their status
aise learn --enable aws                                  # Learn from a pre-configured source
aise learn --enable kubernetes --enable docker           # Learn from multiple sources
aise learn https://docs.example.com --source-name myapp  # Learn from a custom URL
```

Options:
- `--list` — Display the documentation registry with status
- `--enable TEXT` — Enable and crawl a pre-configured source (repeatable)
- `--source-name TEXT` — Name for a custom URL source
- `--max-pages INT` — Maximum pages to crawl (default: 500)
- `--max-depth INT` — Maximum crawl depth (default: 3)

Pre-configured sources: `aws`, `azure`, `gcp`, `kubernetes`, `docker`, `terraform`, `git`

---

### `aise ticket`

Manage support tickets.

```bash
aise ticket list                  # List open tickets (table view)
aise ticket show TICKET-123       # Show full ticket with thread
```

---

### `aise mode`

View or change the operational mode.

```bash
aise mode                         # Show current mode
aise mode set interactive         # Only respond to direct CLI commands
aise mode set approval            # Propose actions, require human approval
aise mode set autonomous          # Act without human approval
```

**Modes:**
- `interactive` — AiSE only responds when directly asked via `aise ask`
- `approval` — AiSE processes tickets and proposes replies/actions, but waits for approval before posting
- `autonomous` — AiSE processes tickets and acts without human intervention

---

### `aise config`

Manage configuration.

```bash
aise config show                          # Display all config (values masked)
aise config show --reveal                 # Display with unmasked values
aise config get LLM_PROVIDER              # Get a specific value
aise config set LLM_PROVIDER openai       # Set a value (persisted to DB)
aise config validate                      # Test connectivity to all services
aise config sources                       # Show where each value comes from
aise config export                        # Print config in .env format
aise config export > backup.env           # Save to file
aise config import backup.env             # Import from file
```

---

### `aise start`

Start the daemon — runs the webhook server and ticket worker in the foreground.

```bash
aise start
aise start --port 8001          # Override webhook server port
aise start --config-port 8080   # Override Config UI port
```

Handles `SIGTERM`/`SIGINT` for graceful shutdown.

---

### `aise init`

Initialize the documentation index on first setup.

```bash
aise init                        # Index all pre-configured sources
aise init --source aws           # Index only AWS docs
aise init --force                # Re-index everything (clears existing)
aise init --list                 # Show index status
```

---

## Webhook API

The webhook server listens on port 8001 by default.

### `POST /webhook/zendesk`

Receive Zendesk ticket events.

**Headers:**
- `X-Zendesk-Webhook-Signature` — HMAC-SHA256 signature (required if `WEBHOOK_SECRET` is set)

**Body:** Zendesk webhook payload (JSON)

**Response:**
```json
{"status": "queued", "ticket_id": "12345", "platform": "zendesk"}
```

**Error responses:**
- `401` — Missing or invalid signature
- `403` — IP not in allowlist
- `429` — Rate limit exceeded (100 req/min per IP)

---

### `POST /webhook/freshdesk`

Receive Freshdesk ticket events.

**Headers:**
- `X-Freshdesk-Webhook-Signature` — HMAC-SHA256 signature (required if `WEBHOOK_SECRET` is set)

**Body:** Freshdesk webhook payload (JSON)

**Response:**
```json
{"status": "queued", "ticket_id": "67890", "platform": "freshdesk"}
```

---

### `POST /webhook/slack`

Receive Slack events.

**Headers:**
- `X-Slack-Signature` — Slack v0 signature
- `X-Slack-Request-Timestamp` — Unix timestamp (must be within 5 minutes)

**Body:** Slack Events API payload (JSON)

Handles URL verification challenge automatically.

**Response:**
```json
{"status": "queued", "ticket_id": "C123:1234567890.123", "platform": "slack"}
```

---

### `GET /health`

Basic liveness check.

**Response:**
```json
{"status": "healthy", "service": "aise-webhook-server", "redis": "connected"}
```

---

### `GET /status`

Full component health snapshot.

**Response:**
```json
{
  "status": "healthy",
  "components": {
    "redis": {"status": "healthy"},
    "postgres": {"status": "healthy"},
    "chromadb": {"status": "healthy"},
    "llm_provider": {"status": "healthy", "provider": "anthropic"}
  },
  "metrics": {
    "tickets_processed": 42,
    "tool_success_rate": 0.97,
    "avg_llm_latency_ms": 1240
  }
}
```

Returns `503` if any critical component is unhealthy.

---

### `GET /metrics`

Prometheus metrics endpoint.

**Content-Type:** `text/plain; version=0.0.4`

Key metrics exposed:
- `aise_tickets_processed_total` — tickets processed by platform and status
- `aise_llm_calls_total` — LLM calls by provider and model
- `aise_llm_tokens_total` — token usage by provider
- `aise_tool_executions_total` — tool executions by tool and status
- `aise_request_duration_seconds` — request latency histogram

---

## Config UI API

The Config UI runs on port 8080.

### `GET /config`

Returns current configuration as JSON (sensitive values masked).

### `POST /config`

Update configuration values. Validates and persists changes without restart.

**Body:**
```json
{"key": "LLM_PROVIDER", "value": "openai"}
```

### `POST /config/validate`

Test connectivity to a specific service.

**Body:**
```json
{"service": "anthropic", "api_key": "sk-ant-..."}
```

### `POST /config/test-browser`

Test browser navigation to the configured ticket system URL.
