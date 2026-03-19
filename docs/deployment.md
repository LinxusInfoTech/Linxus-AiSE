# Deployment Guide

## Docker Compose (recommended)

### Infrastructure only (development)

Start PostgreSQL, Redis, and ChromaDB without the AiSE application containers:

```bash
docker compose up -d
```

This starts:
- **PostgreSQL 16** on port 5432 — conversation memory, credentials, audit log
- **Redis 7** on port 6379 — ticket queue and short-term cache
- **ChromaDB** on port 8000 — vector embeddings for knowledge and user style

Verify all services are healthy:

```bash
docker compose ps
```

### Full stack (production)

Run the complete stack including the AiSE API and worker:

```bash
docker compose --profile full up -d
```

This adds:
- **aise-api** on port 8080 (Config UI) and 8001 (webhook server)
- **aise-worker** — background ticket processing daemon

### With monitoring

```bash
docker compose --profile full --profile monitoring up -d
```

Adds Prometheus (port 9090) and Grafana (port 3000, default password: `admin`).

---

## Environment configuration

Copy `.env.example` to `.env` and fill in your values before starting:

```bash
cp .env.example .env
```

### Required variables

| Variable | Description |
|----------|-------------|
| `LLM_PROVIDER` | Primary LLM: `anthropic`, `openai`, `deepseek`, or `ollama` |
| `ANTHROPIC_API_KEY` | Anthropic API key (if using Claude) |
| `OPENAI_API_KEY` | OpenAI API key (if using GPT-4) |
| `DEEPSEEK_API_KEY` | DeepSeek API key (if using DeepSeek) |
| `POSTGRES_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `CHROMA_HOST` | ChromaDB hostname |
| `CHROMA_PORT` | ChromaDB port (default: 8000) |

### Ticket system variables (optional)

| Variable | Description |
|----------|-------------|
| `ZENDESK_SUBDOMAIN` | Your Zendesk subdomain |
| `ZENDESK_EMAIL` | Admin email for Zendesk API |
| `ZENDESK_API_TOKEN` | Zendesk API token |
| `FRESHDESK_DOMAIN` | Your Freshdesk domain |
| `FRESHDESK_API_KEY` | Freshdesk API key |
| `SLACK_BOT_TOKEN` | Slack bot OAuth token |
| `SLACK_SIGNING_SECRET` | Slack signing secret for webhook verification |

### Security variables

| Variable | Description |
|----------|-------------|
| `CREDENTIAL_VAULT_KEY` | Base64-encoded 32-byte AES-256 encryption key |
| `WEBHOOK_SECRET` | Shared secret for HMAC webhook signature verification |
| `WEBHOOK_ALLOWED_IPS` | Comma-separated IP allowlist for webhooks (empty = allow all) |

Generate a vault key:
```bash
python3 -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

---

## Production considerations

### Secrets management

Never commit `.env` to version control. In production, inject secrets via:
- Environment variables from your CI/CD system
- A secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.)
- Kubernetes Secrets

### Database

The schema is initialized automatically on first startup via `scripts/init-db.sql`. It is idempotent — safe to run multiple times.

For production, consider:
- Enabling PostgreSQL SSL (`?sslmode=require` in `POSTGRES_URL`)
- Setting up automated backups
- Using a managed database service (RDS, Cloud SQL, etc.)

### Scaling

- The **webhook server** is stateless and can be scaled horizontally behind a load balancer
- The **ticket worker** should run as a single instance (or use distributed locking) to avoid duplicate processing
- **Redis** is used for the ticket queue — ensure it has persistence enabled (`appendonly yes`)

### Health checks

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Basic liveness check |
| `GET /status` | Full component health (DB, Redis, ChromaDB, LLM) |
| `GET /metrics` | Prometheus metrics |

### Graceful shutdown

The `aise start` command handles `SIGTERM` and `SIGINT` for graceful shutdown, draining in-flight ticket processing before exiting.

---

## Troubleshooting

**Services won't start:**
```bash
docker compose logs postgres
docker compose logs redis
```

**Database connection errors:**
- Verify `POSTGRES_URL` matches the Docker Compose service credentials
- Default: `postgresql://aise:aise_password@localhost:5432/aise`

**ChromaDB connection errors:**
- Default host is `localhost`, port `8000` (not 8001 — that's the webhook server)
- Check: `curl http://localhost:8000/api/v1/heartbeat`

**LLM provider errors:**
```bash
aise config validate    # Tests connectivity to all configured services
```

**Webhook not receiving events:**
- Ensure `WEBHOOK_SECRET` matches what's configured in your ticket system
- Check `WEBHOOK_ALLOWED_IPS` — if set, your ticket system's IP must be in the list
- Verify the webhook URL points to port 8001 (webhook server), not 8080 (Config UI)
