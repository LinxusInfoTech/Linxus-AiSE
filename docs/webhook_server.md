# Webhook Server Documentation

The AiSE webhook server receives ticket notifications from various support platforms (Zendesk, Freshdesk, Slack) and queues them for processing.

## Features

- **HMAC Signature Verification**: Verifies webhook authenticity using HMAC-SHA256 (Requirement 19.3)
- **Rate Limiting**: Protects against abuse with configurable rate limits (Requirement 19.4)
- **IP Allowlisting**: Restricts webhook sources to trusted IPs (Requirement 19.9)
- **Redis Queue**: Asynchronous ticket processing via Redis queue (Requirement 8.2)
- **Immediate Response**: Returns 200 OK immediately after queuing

## Configuration

Configure the webhook server using environment variables:

```bash
# Redis connection (required)
REDIS_URL=redis://localhost:6379

# Webhook security (optional but recommended)
WEBHOOK_SECRET=your-secret-key-here
SLACK_SIGNING_SECRET=your-slack-secret-here

# IP allowlisting (optional, comma-separated)
WEBHOOK_ALLOWED_IPS=192.168.1.1,10.0.0.1

# Server port
WEBHOOK_SERVER_PORT=8000
```

## Running the Server

### Development

```bash
uvicorn aise.ticket_system.webhook_server:app --host 0.0.0.0 --port 8000 --reload
```

### Production

```bash
uvicorn aise.ticket_system.webhook_server:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker Compose

The webhook server is included in the docker-compose.yml:

```bash
docker compose up webhook-server
```

## Webhook Endpoints

### Zendesk Webhook

**Endpoint**: `POST /webhook/zendesk`

**Headers**:
- `X-Zendesk-Webhook-Signature`: HMAC-SHA256 signature of request body

**Payload Example**:
```json
{
  "ticket": {
    "id": "12345",
    "subject": "Customer issue",
    "description": "Help needed with...",
    "status": "open"
  }
}
```

**Response**:
```json
{
  "status": "queued",
  "ticket_id": "12345",
  "platform": "zendesk"
}
```

### Freshdesk Webhook

**Endpoint**: `POST /webhook/freshdesk`

**Headers**:
- `X-Freshdesk-Webhook-Signature`: HMAC-SHA256 signature of request body

**Payload Example**:
```json
{
  "ticket_id": "67890",
  "subject": "Support request",
  "priority": 2,
  "status": "open"
}
```

**Response**:
```json
{
  "status": "queued",
  "ticket_id": "67890",
  "platform": "freshdesk"
}
```

### Slack Webhook

**Endpoint**: `POST /webhook/slack`

**Headers**:
- `X-Slack-Signature`: Slack signature (v0=<signature>)
- `X-Slack-Request-Timestamp`: Request timestamp

**Payload Example**:
```json
{
  "type": "event_callback",
  "event": {
    "channel": "C12345",
    "ts": "1234567890.123456",
    "text": "Need help with deployment",
    "user": "U67890"
  }
}
```

**Response**:
```json
{
  "status": "queued",
  "ticket_id": "C12345:1234567890.123456",
  "platform": "slack"
}
```

**URL Verification**: Slack sends a verification challenge when you first configure the webhook. The server automatically responds with the challenge.

## Configuring Webhooks in Ticket Systems

### Zendesk

1. Go to Admin Center → Apps and integrations → Webhooks
2. Click "Create webhook"
3. Set URL to: `https://your-domain.com/webhook/zendesk`
4. Set HTTP method to POST
5. Add custom header: `X-Zendesk-Webhook-Signature` with your WEBHOOK_SECRET
6. Configure triggers to send webhooks on ticket events

### Freshdesk

1. Go to Admin → Workflows → Automations
2. Create new automation rule
3. Set action to "Trigger webhook"
4. Set URL to: `https://your-domain.com/webhook/freshdesk`
5. Add custom header: `X-Freshdesk-Webhook-Signature` with your WEBHOOK_SECRET
6. Configure conditions for when to trigger

### Slack

1. Go to https://api.slack.com/apps
2. Create or select your app
3. Go to "Event Subscriptions"
4. Enable events and set Request URL to: `https://your-domain.com/webhook/slack`
5. Subscribe to bot events: `message.channels`, `message.groups`, `message.im`
6. Copy the Signing Secret and set it as SLACK_SIGNING_SECRET

## Security

### HMAC Signature Verification

The webhook server verifies HMAC signatures to ensure webhooks are authentic:

- **Zendesk**: Uses `X-Zendesk-Webhook-Signature` header with SHA256
- **Freshdesk**: Uses `X-Freshdesk-Webhook-Signature` header with SHA256
- **Slack**: Uses `X-Slack-Signature` header with timestamp-based signature

If `WEBHOOK_SECRET` or `SLACK_SIGNING_SECRET` is not configured, signature verification is skipped (not recommended for production).

### IP Allowlisting

Configure `WEBHOOK_ALLOWED_IPS` to restrict webhook sources:

```bash
# Allow only specific IPs
WEBHOOK_ALLOWED_IPS=192.168.1.1,10.0.0.1,172.16.0.1

# Allow all (default if not set)
# WEBHOOK_ALLOWED_IPS=
```

### Rate Limiting

Default rate limits:
- **100 requests per minute** per IP per endpoint
- Configurable in code via `check_rate_limit()` function

Rate-limited requests receive HTTP 429 (Too Many Requests).

## Monitoring

### Health Check

**Endpoint**: `GET /health`

**Response (Healthy)**:
```json
{
  "status": "healthy",
  "service": "aise-webhook-server",
  "redis": "connected"
}
```

**Response (Unhealthy)**:
```json
{
  "status": "unhealthy",
  "service": "aise-webhook-server",
  "error": "Connection failed"
}
```

### Logs

The webhook server uses structured logging with the following events:

- `webhook_received`: Successful webhook reception
- `webhook_ip_blocked`: IP not in allowlist
- `webhook_rate_limit_exceeded`: Rate limit exceeded
- `webhook_missing_signature`: Missing signature header
- `webhook_invalid_signature`: Invalid signature
- `webhook_invalid_payload`: Malformed JSON
- `ticket_enqueued`: Ticket added to Redis queue

Example log entry:
```json
{
  "event": "webhook_received",
  "platform": "zendesk",
  "ticket_id": "12345",
  "client_ip": "192.168.1.1",
  "timestamp": "2024-03-13T10:30:00Z"
}
```

## Ticket Queue Processing

Tickets are enqueued to Redis list `ticket_queue` in FIFO order:

```python
# Queue item structure
{
  "ticket_id": "12345",
  "platform": "zendesk",
  "payload": { ... },  # Full webhook payload
  "received_at": "2024-03-13T10:30:00Z"
}
```

A separate worker process should consume from this queue:

```python
import redis.asyncio as redis
import json

async def process_tickets():
    redis_client = redis.from_url("redis://localhost:6379")
    
    while True:
        # Block until ticket available (right pop for FIFO)
        _, ticket_json = await redis_client.brpop("ticket_queue")
        ticket = json.loads(ticket_json)
        
        # Process ticket
        await handle_ticket(ticket)
```

## Error Handling

### HTTP Status Codes

- **200 OK**: Webhook received and queued successfully
- **400 Bad Request**: Invalid payload or missing required fields
- **401 Unauthorized**: Missing or invalid signature
- **403 Forbidden**: IP address not allowed
- **429 Too Many Requests**: Rate limit exceeded
- **503 Service Unavailable**: Redis connection failed

### Error Response Format

```json
{
  "detail": "Error message describing what went wrong"
}
```

## Testing

### Unit Tests

```bash
poetry run pytest tests/unit/test_webhook_server.py -v
```

### Integration Tests

Requires Redis to be running:

```bash
# Start Redis
docker run -d -p 6379:6379 redis:latest

# Run integration tests
poetry run pytest tests/integration/test_webhook_integration.py -v -m integration
```

### Manual Testing with curl

```bash
# Test Zendesk webhook
curl -X POST http://localhost:8000/webhook/zendesk \
  -H "Content-Type: application/json" \
  -H "X-Zendesk-Webhook-Signature: <computed-signature>" \
  -d '{"ticket": {"id": "12345", "subject": "Test"}}'

# Test health check
curl http://localhost:8000/health
```

## Troubleshooting

### Webhook not received

1. Check webhook server logs for errors
2. Verify webhook URL is accessible from ticket system
3. Check firewall rules and network connectivity
4. Verify Redis is running and accessible

### Signature verification fails

1. Ensure WEBHOOK_SECRET matches the secret configured in ticket system
2. Verify the signature header name matches expected format
3. Check that payload is not modified in transit (no proxies altering body)

### Rate limiting issues

1. Check if legitimate traffic is being rate limited
2. Adjust rate limits in code if needed
3. Consider implementing Redis-based rate limiting for distributed deployments

### Redis connection issues

1. Verify REDIS_URL is correct
2. Check Redis is running: `redis-cli ping`
3. Check network connectivity to Redis
4. Review Redis logs for errors

## Production Deployment

### Recommendations

1. **Use HTTPS**: Always use TLS for webhook endpoints
2. **Configure Secrets**: Set WEBHOOK_SECRET and SLACK_SIGNING_SECRET
3. **Enable IP Allowlisting**: Restrict to known ticket system IPs
4. **Monitor Queue Depth**: Alert if Redis queue grows too large
5. **Scale Workers**: Run multiple worker processes to handle load
6. **Set Up Logging**: Aggregate logs to centralized logging system
7. **Configure Alerts**: Alert on health check failures and error rates

### Example Production Setup

```yaml
# docker-compose.yml
services:
  webhook-server:
    image: aise:latest
    command: uvicorn aise.ticket_system.webhook_server:app --host 0.0.0.0 --port 8000 --workers 4
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379
      - WEBHOOK_SECRET=${WEBHOOK_SECRET}
      - SLACK_SIGNING_SECRET=${SLACK_SIGNING_SECRET}
      - WEBHOOK_ALLOWED_IPS=${WEBHOOK_ALLOWED_IPS}
    depends_on:
      - redis
    restart: unless-stopped
  
  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    restart: unless-stopped

volumes:
  redis-data:
```

## API Reference

See the interactive API documentation at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
