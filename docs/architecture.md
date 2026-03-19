# Architecture

## Overview

AiSE is a modular, event-driven system built around a LangGraph agent orchestration core. It ingests support tickets from multiple sources, retrieves relevant documentation context, executes safe CLI diagnostics, and generates contextual replies — all with configurable human oversight.

```
┌─────────────────────────────────────────────────────────────────┐
│                         Entry Points                            │
│  CLI (aise ask)    Webhook Server    Config UI (port 8080)      │
└────────┬───────────────────┬──────────────────────────────────┘
         │                   │
         ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                      LangGraph Orchestrator                     │
│                                                                 │
│  classify → retrieve_knowledge → diagnose → plan_tools          │
│      → execute_tools → generate_response → post_reply          │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Ticket Agent │  │Knowledge Agent│  │  Engineer Agent      │  │
│  │ (classify)   │  │ (RAG search) │  │  (LLM diagnosis)     │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Tool Agent  │  │Browser Agent │  │  Approval Gate       │  │
│  │ (CLI exec)   │  │ (Playwright) │  │  (approval mode)     │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │                   │                    │
         ▼                   ▼                    ▼
┌──────────────┐   ┌──────────────────┐   ┌──────────────────┐
│  LLM Router  │   │  Knowledge Engine │   │  Tool Executor   │
│  (failover)  │   │  (ChromaDB RAG)  │   │  (allowlist CLI) │
└──────────────┘   └──────────────────┘   └──────────────────┘
         │                   │                    │
         ▼                   ▼                    ▼
┌──────────────┐   ┌──────────────────┐   ┌──────────────────┐
│  Anthropic   │   │    ChromaDB      │   │  aws / kubectl   │
│  OpenAI      │   │    (vectors)     │   │  terraform/docker│
│  DeepSeek    │   │                  │   │  git / ssh       │
│  Ollama      │   │    PostgreSQL    │   └──────────────────┘
└──────────────┘   │    (metadata)    │
                   └──────────────────┘
```

---

## Components

### LangGraph Orchestrator (`aise/agents/graph.py`)

The central state machine that coordinates all agents. Implements the workflow as a directed graph with conditional routing:

- **classify** — Ticket Agent categorizes the ticket (category, severity, affected service)
- **retrieve_knowledge** — Knowledge Agent searches ChromaDB for relevant documentation
- **diagnose** — Engineer Agent generates diagnosis using LLM + knowledge context
- **plan_tools** — Tool Agent determines which CLI commands to run
- **execute_tools** — Tool Agent executes commands via ToolExecutor
- **generate_response** — Engineer Agent synthesizes final reply from all context
- **post_reply** — Posts reply to ticket system (or pauses for approval)

**Approval gate:** In `approval` mode, the graph pauses before `post_reply` and surfaces the proposed action to the operator. Execution resumes or aborts based on the decision.

### Agent State (`aise/agents/state.py`)

All agents communicate through an immutable `AiSEState` TypedDict. Each agent receives the current state and returns a new state — never mutating the input. This enables safe parallel execution and deterministic replay.

Key state fields:
- `ticket_id`, `messages` — ticket identity and thread
- `classification` — Ticket Agent output
- `knowledge_context` — retrieved documentation chunks with citations
- `diagnosis` — Engineer Agent analysis
- `tool_results` — CLI execution outputs
- `pending_approval` — proposed action awaiting human decision
- `mode` — current operational mode

### LLM Router (`aise/ai_engine/router.py`)

Manages multiple LLM providers with automatic failover:
- Priority order: configured default → anthropic → openai → deepseek → ollama
- **Circuit breaker** per provider: opens after 3 consecutive failures, half-opens after 5-minute cooldown
- Tracks token usage and estimated cost per provider

### Knowledge Engine (`aise/knowledge_engine/`)

RAG pipeline for documentation:
1. **Crawler** (`crawler.py`) — async web crawler respecting robots.txt and rate limits
2. **Extractor** (`extractor.py`) — HTML → Markdown conversion preserving heading structure
3. **Chunker** (`chunker.py`) — semantic chunking with configurable size/overlap and deterministic IDs
4. **Embedder** (`embedder.py`) — OpenAI or local sentence-transformers embeddings
5. **Vector Store** (`vector_store.py`) — ChromaDB with persistent storage
6. **Metadata Store** (`metadata_store.py`) — PostgreSQL for crawl metadata and source tracking

### Tool Executor (`aise/tool_executor/`)

Secure CLI execution:
- **Allowlist** (`allowlist.py`) — explicit permit list for commands and subcommands
- **Runner** (`runner.py`) — `asyncio.create_subprocess_exec` (never `shell=True`), restricted environment
- **ToolExecutor** (`base.py`) — integrates allowlist + runner, enforces per-ticket rate limit (10 cmd/min), writes to PostgreSQL audit log
- **Tool wrappers** (`tools/`) — typed wrappers for aws, kubectl, terraform, docker, git, ssh

### Ticket System (`aise/ticket_system/`)

Unified `TicketProvider` interface with implementations for:
- Zendesk (API v2 with exponential backoff retry)
- Freshdesk (API v2)
- Email (IMAP/SMTP via aioimaplib/aiosmtplib)
- Slack (Events API)

**Conversation memory** (`memory.py`) persists message threads to PostgreSQL with Redis caching (last 10 messages per ticket). Automatic 90-day retention cleanup.

### Browser Operator (`aise/browser_operator/`)

Playwright-based fallback when ticket APIs are unavailable:
- **BrowserSession** — singleton with 30-minute idle timeout
- **BrowserActions** — navigate, click, fill, read_text, wait_for primitives
- **Platform drivers** — Zendesk and Freshdesk-specific login and ticket interaction flows
- **BrowserAgent** — integrates with LangGraph, triggers only when `USE_BROWSER_FALLBACK=true` and API fails

### Credential Vault (`aise/core/credential_vault.py`)

AES-256-GCM encryption for all sensitive credentials. Encryption key loaded from `CREDENTIAL_VAULT_KEY` environment variable. All access is audit-logged.

### Observability (`aise/observability/`)

- **Tracer** (`tracer.py`) — OpenTelemetry SDK with OTLP export; spans for all LLM calls, tool executions, and agent transitions
- **Metrics** (`metrics.py`) — Prometheus counters and histograms; exposed at `GET /metrics`
- **LangSmith** (`langsmith.py`) — LangChain/LangGraph trace export with ticket metadata
- **Dashboard** (`dashboard.py`) — `GET /status` aggregates component health and key metrics

---

## Data Models

### AiSEState

```python
class AiSEState(TypedDict):
    ticket_id: Optional[str]
    messages: List[Dict]          # conversation thread
    classification: Optional[Dict] # category, severity, affected_service
    knowledge_context: List[Dict]  # retrieved chunks with source URLs
    diagnosis: Optional[str]       # LLM analysis
    tool_results: List[ToolResult] # CLI execution outputs
    response: Optional[str]        # final reply to post
    pending_approval: Optional[Dict]
    mode: str                      # interactive | approval | autonomous
    error: Optional[str]
```

### Ticket

```python
@dataclass
class Ticket:
    id: str
    subject: str
    body: str
    customer_email: str
    status: TicketStatus
    tags: List[str]
    created_at: datetime
    updated_at: datetime
    thread: List[Message]
```

---

## Security Model

- **Credential encryption** — AES-256-GCM at rest via credential vault
- **TLS enforcement** — all external HTTP clients use `verify=True`
- **Webhook security** — HMAC-SHA256 signature verification + IP allowlisting + rate limiting
- **Tool allowlist** — explicit permit list; `ForbiddenCommandError` on any unlisted command
- **Per-ticket rate limiting** — 10 tool executions per minute per ticket
- **Audit logging** — all security events written to PostgreSQL `audit_log` table with 90-day retention
- **PII redaction** — emails, phone numbers, IPs redacted from logs and traces

---

## Configuration Precedence

```
Environment variables  (highest)
    ↓
.env file
    ↓
Config UI database settings
    ↓
System configs (~/.aws/config, ~/.kube/config, etc.)
    ↓
Default values         (lowest)
```
