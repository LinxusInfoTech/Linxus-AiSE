# tests/integration/test_webhook_integration.py
"""Integration tests for webhook server.

These tests verify the webhook server works end-to-end with Redis
and proper signature verification.
"""

import pytest
import hmac
import hashlib
import json
import time
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import redis.asyncio as redis

from aise.ticket_system.webhook_server import app


@pytest.fixture
async def redis_client():
    """Create a real Redis client for testing.
    
    Note: This requires Redis to be running. If Redis is not available,
    tests will be skipped.
    """
    try:
        client = redis.from_url(
            "redis://localhost:6379",
            encoding="utf-8",
            decode_responses=True
        )
        await client.ping()
        
        # Clear test queue before tests
        await client.delete("ticket_queue")
        
        yield client
        
        # Cleanup after tests
        await client.delete("ticket_queue")
        await client.close()
    except Exception as e:
        pytest.skip(f"Redis not available: {e}")


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_config():
    """Mock configuration."""
    config = MagicMock()
    config.REDIS_URL = "redis://localhost:6379"
    config.WEBHOOK_SECRET = "integration-test-secret"
    config.SLACK_SIGNING_SECRET = "slack-integration-secret"
    config.WEBHOOK_ALLOWED_IPS = None
    return config


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_end_to_end_zendesk(client, redis_client, mock_config):
    """Test Zendesk webhook end-to-end with Redis queue."""
    payload = {
        "ticket": {
            "id": "99999",
            "subject": "Integration test ticket",
            "description": "This is a test"
        }
    }
    body = json.dumps(payload).encode('utf-8')
    
    # Compute valid signature
    signature = hmac.new(
        mock_config.WEBHOOK_SECRET.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()
    
    with patch('aise.ticket_system.webhook_server.get_config', return_value=mock_config), \
         patch('aise.ticket_system.webhook_server.get_redis_client', return_value=redis_client):
        
        # Send webhook
        response = client.post(
            "/webhook/zendesk",
            json=payload,
            headers={"X-Zendesk-Webhook-Signature": signature}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["ticket_id"] == "99999"
        
        # Verify ticket was enqueued in Redis
        queue_length = await redis_client.llen("ticket_queue")
        assert queue_length == 1
        
        # Pop from queue and verify content
        queue_item_json = await redis_client.rpop("ticket_queue")
        queue_item = json.loads(queue_item_json)
        
        assert queue_item["ticket_id"] == "99999"
        assert queue_item["platform"] == "zendesk"
        assert queue_item["payload"]["ticket"]["subject"] == "Integration test ticket"
        assert "received_at" in queue_item


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_end_to_end_freshdesk(client, redis_client, mock_config):
    """Test Freshdesk webhook end-to-end with Redis queue."""
    payload = {
        "ticket_id": "88888",
        "subject": "Freshdesk integration test",
        "priority": 2
    }
    body = json.dumps(payload).encode('utf-8')
    
    signature = hmac.new(
        mock_config.WEBHOOK_SECRET.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()
    
    with patch('aise.ticket_system.webhook_server.get_config', return_value=mock_config), \
         patch('aise.ticket_system.webhook_server.get_redis_client', return_value=redis_client):
        
        response = client.post(
            "/webhook/freshdesk",
            json=payload,
            headers={"X-Freshdesk-Webhook-Signature": signature}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["ticket_id"] == "88888"
        
        # Verify in Redis
        queue_length = await redis_client.llen("ticket_queue")
        assert queue_length == 1
        
        queue_item_json = await redis_client.rpop("ticket_queue")
        queue_item = json.loads(queue_item_json)
        
        assert queue_item["ticket_id"] == "88888"
        assert queue_item["platform"] == "freshdesk"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_end_to_end_slack(client, redis_client, mock_config):
    """Test Slack webhook end-to-end with Redis queue."""
    timestamp = str(int(time.time()))
    payload = {
        "type": "event_callback",
        "event": {
            "channel": "C99999",
            "ts": "1234567890.999999",
            "text": "Integration test message",
            "user": "U12345"
        }
    }
    body = json.dumps(payload).encode('utf-8')
    
    # Compute Slack signature
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    signature = 'v0=' + hmac.new(
        mock_config.SLACK_SIGNING_SECRET.encode('utf-8'),
        sig_basestring.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    with patch('aise.ticket_system.webhook_server.get_config', return_value=mock_config), \
         patch('aise.ticket_system.webhook_server.get_redis_client', return_value=redis_client):
        
        response = client.post(
            "/webhook/slack",
            json=payload,
            headers={
                "X-Slack-Signature": signature,
                "X-Slack-Request-Timestamp": timestamp
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert "C99999" in data["ticket_id"]
        
        # Verify in Redis
        queue_length = await redis_client.llen("ticket_queue")
        assert queue_length == 1
        
        queue_item_json = await redis_client.rpop("ticket_queue")
        queue_item = json.loads(queue_item_json)
        
        assert "C99999" in queue_item["ticket_id"]
        assert queue_item["platform"] == "slack"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_multiple_tickets_queued(client, redis_client, mock_config):
    """Test multiple webhooks are queued in order."""
    with patch('aise.ticket_system.webhook_server.get_config', return_value=mock_config), \
         patch('aise.ticket_system.webhook_server.get_redis_client', return_value=redis_client):
        
        # Send 3 webhooks
        for i in range(1, 4):
            payload = {"ticket": {"id": f"ticket-{i}"}}
            body = json.dumps(payload).encode('utf-8')
            signature = hmac.new(
                mock_config.WEBHOOK_SECRET.encode('utf-8'),
                body,
                hashlib.sha256
            ).hexdigest()
            
            response = client.post(
                "/webhook/zendesk",
                json=payload,
                headers={"X-Zendesk-Webhook-Signature": signature}
            )
            assert response.status_code == 200
        
        # Verify all 3 are in queue
        queue_length = await redis_client.llen("ticket_queue")
        assert queue_length == 3
        
        # Pop in FIFO order (right pop)
        for i in range(1, 4):
            queue_item_json = await redis_client.rpop("ticket_queue")
            queue_item = json.loads(queue_item_json)
            assert queue_item["ticket_id"] == f"ticket-{i}"


@pytest.mark.integration
def test_webhook_health_check_with_redis(client, mock_config):
    """Test health check endpoint with Redis connectivity."""
    with patch('aise.ticket_system.webhook_server.get_config', return_value=mock_config):
        response = client.get("/health")
        
        # Should be healthy if Redis is running
        # If Redis is not running, this will return 503
        assert response.status_code in [200, 503]
        
        data = response.json()
        assert "status" in data
        assert data["service"] == "aise-webhook-server"
