# tests/unit/test_webhook_server.py
"""Unit tests for webhook server."""

import pytest
import hmac
import hashlib
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from aise.ticket_system.webhook_server import (
    app,
    verify_hmac_signature,
    check_ip_allowlist,
    check_rate_limit,
    enqueue_ticket,
    _rate_limit_state
)


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock()
    redis_mock.lpush = AsyncMock()
    redis_mock.close = AsyncMock()
    return redis_mock


@pytest.fixture
def mock_config():
    """Mock configuration."""
    config = MagicMock()
    config.REDIS_URL = "redis://localhost:6379"
    config.WEBHOOK_SECRET = "test-secret-key"
    config.SLACK_SIGNING_SECRET = "slack-secret"
    config.WEBHOOK_ALLOWED_IPS = None  # Allow all by default
    return config


class TestHMACVerification:
    """Test HMAC signature verification."""
    
    def test_verify_hmac_signature_valid(self):
        """Test valid HMAC signature verification."""
        payload = b'{"ticket_id": "12345"}'
        secret = "test-secret"
        
        # Compute valid signature
        signature = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        assert verify_hmac_signature(payload, signature, secret) is True
    
    def test_verify_hmac_signature_invalid(self):
        """Test invalid HMAC signature verification."""
        payload = b'{"ticket_id": "12345"}'
        secret = "test-secret"
        invalid_signature = "invalid-signature"
        
        assert verify_hmac_signature(payload, invalid_signature, secret) is False
    
    def test_verify_hmac_signature_no_secret(self):
        """Test HMAC verification with no secret configured."""
        payload = b'{"ticket_id": "12345"}'
        signature = "any-signature"
        
        assert verify_hmac_signature(payload, signature, "") is False
        assert verify_hmac_signature(payload, signature, None) is False
    
    def test_verify_hmac_signature_different_payload(self):
        """Test HMAC verification fails with different payload."""
        payload1 = b'{"ticket_id": "12345"}'
        payload2 = b'{"ticket_id": "67890"}'
        secret = "test-secret"
        
        signature = hmac.new(
            secret.encode('utf-8'),
            payload1,
            hashlib.sha256
        ).hexdigest()
        
        assert verify_hmac_signature(payload2, signature, secret) is False


class TestIPAllowlist:
    """Test IP allowlist functionality."""
    
    def test_check_ip_allowlist_no_restriction(self):
        """Test IP allowlist with no restrictions (allow all)."""
        assert check_ip_allowlist("192.168.1.1", None) is True
        assert check_ip_allowlist("10.0.0.1", "") is True
    
    def test_check_ip_allowlist_single_ip(self):
        """Test IP allowlist with single allowed IP."""
        allowed_ips = "192.168.1.1"
        
        assert check_ip_allowlist("192.168.1.1", allowed_ips) is True
        assert check_ip_allowlist("192.168.1.2", allowed_ips) is False
    
    def test_check_ip_allowlist_multiple_ips(self):
        """Test IP allowlist with multiple allowed IPs."""
        allowed_ips = "192.168.1.1, 10.0.0.1, 172.16.0.1"
        
        assert check_ip_allowlist("192.168.1.1", allowed_ips) is True
        assert check_ip_allowlist("10.0.0.1", allowed_ips) is True
        assert check_ip_allowlist("172.16.0.1", allowed_ips) is True
        assert check_ip_allowlist("192.168.1.2", allowed_ips) is False


class TestRateLimiting:
    """Test rate limiting functionality."""
    
    def setup_method(self):
        """Clear rate limit state before each test."""
        _rate_limit_state.clear()
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_within_limit(self):
        """Test rate limiting within allowed limit."""
        endpoint = "test"
        client_ip = "192.168.1.1"
        
        # Make 5 requests (well within default limit of 100)
        for _ in range(5):
            result = await check_rate_limit(endpoint, client_ip, max_requests=100)
            assert result is True
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_exceeded(self):
        """Test rate limiting when limit is exceeded."""
        endpoint = "test"
        client_ip = "192.168.1.1"
        max_requests = 3
        
        # Make requests up to limit
        for _ in range(max_requests):
            result = await check_rate_limit(endpoint, client_ip, max_requests=max_requests)
            assert result is True
        
        # Next request should be rate limited
        result = await check_rate_limit(endpoint, client_ip, max_requests=max_requests)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_different_ips(self):
        """Test rate limiting is per-IP."""
        endpoint = "test"
        max_requests = 3
        
        # IP 1 makes requests up to limit
        for _ in range(max_requests):
            result = await check_rate_limit(endpoint, "192.168.1.1", max_requests=max_requests)
            assert result is True
        
        # IP 1 is rate limited
        result = await check_rate_limit(endpoint, "192.168.1.1", max_requests=max_requests)
        assert result is False
        
        # IP 2 should still be allowed
        result = await check_rate_limit(endpoint, "192.168.1.2", max_requests=max_requests)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_window_expiry(self):
        """Test rate limiting window expiry."""
        endpoint = "test"
        client_ip = "192.168.1.1"
        max_requests = 2
        window_seconds = 1
        
        # Make requests up to limit
        for _ in range(max_requests):
            result = await check_rate_limit(
                endpoint, client_ip,
                max_requests=max_requests,
                window_seconds=window_seconds
            )
            assert result is True
        
        # Should be rate limited
        result = await check_rate_limit(
            endpoint, client_ip,
            max_requests=max_requests,
            window_seconds=window_seconds
        )
        assert result is False
        
        # Wait for window to expire
        time.sleep(1.1)
        
        # Should be allowed again
        result = await check_rate_limit(
            endpoint, client_ip,
            max_requests=max_requests,
            window_seconds=window_seconds
        )
        assert result is True


class TestEnqueueTicket:
    """Test ticket enqueueing."""
    
    @pytest.mark.asyncio
    async def test_enqueue_ticket(self, mock_redis):
        """Test ticket is enqueued to Redis."""
        with patch('aise.ticket_system.webhook_server.get_redis_client', return_value=mock_redis):
            ticket_id = "12345"
            platform = "zendesk"
            payload = {"ticket": {"id": "12345", "subject": "Test"}}
            
            await enqueue_ticket(ticket_id, platform, payload)
            
            # Verify Redis lpush was called
            mock_redis.lpush.assert_called_once()
            call_args = mock_redis.lpush.call_args[0]
            
            assert call_args[0] == "ticket_queue"
            
            # Verify queue item structure
            queue_item = json.loads(call_args[1])
            assert queue_item["ticket_id"] == ticket_id
            assert queue_item["platform"] == platform
            assert queue_item["payload"] == payload
            assert "received_at" in queue_item


class TestWebhookEndpoints:
    """Test webhook endpoints."""
    
    def setup_method(self):
        """Clear rate limit state before each test."""
        _rate_limit_state.clear()
    
    @pytest.mark.asyncio
    async def test_root_endpoint(self, client):
        """Test root endpoint returns service info."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "aise-webhook-server"
        assert "/webhook/zendesk" in data["endpoints"]
    
    @pytest.mark.asyncio
    async def test_health_check_healthy(self, client, mock_redis):
        """Test health check when Redis is connected."""
        with patch('aise.ticket_system.webhook_server.get_redis_client', return_value=mock_redis):
            response = client.get("/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["redis"] == "connected"
    
    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, client):
        """Test health check when Redis is disconnected."""
        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = Exception("Connection failed")
        
        with patch('aise.ticket_system.webhook_server.get_redis_client', return_value=mock_redis):
            response = client.get("/health")
            
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"
    
    @pytest.mark.asyncio
    async def test_zendesk_webhook_success(self, client, mock_redis, mock_config):
        """Test successful Zendesk webhook reception."""
        payload = {"ticket": {"id": "12345", "subject": "Test ticket"}}
        body = json.dumps(payload).encode('utf-8')
        
        # Compute valid signature
        signature = hmac.new(
            mock_config.WEBHOOK_SECRET.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()
        
        with patch('aise.ticket_system.webhook_server.get_config', return_value=mock_config), \
             patch('aise.ticket_system.webhook_server.get_redis_client', return_value=mock_redis):
            
            response = client.post(
                "/webhook/zendesk",
                json=payload,
                headers={"X-Zendesk-Webhook-Signature": signature}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "queued"
            assert data["ticket_id"] == "12345"
            assert data["platform"] == "zendesk"
            
            # Verify ticket was enqueued
            mock_redis.lpush.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_zendesk_webhook_missing_signature(self, client, mock_config):
        """Test Zendesk webhook with missing signature."""
        payload = {"ticket": {"id": "12345"}}
        
        with patch('aise.ticket_system.webhook_server.get_config', return_value=mock_config):
            response = client.post("/webhook/zendesk", json=payload)
            
            assert response.status_code == 401
            assert "Missing webhook signature" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_zendesk_webhook_invalid_signature(self, client, mock_redis, mock_config):
        """Test Zendesk webhook with invalid signature."""
        payload = {"ticket": {"id": "12345"}}
        
        with patch('aise.ticket_system.webhook_server.get_config', return_value=mock_config), \
             patch('aise.ticket_system.webhook_server.get_redis_client', return_value=mock_redis):
            
            response = client.post(
                "/webhook/zendesk",
                json=payload,
                headers={"X-Zendesk-Webhook-Signature": "invalid-signature"}
            )
            
            assert response.status_code == 401
            assert "Invalid webhook signature" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_zendesk_webhook_missing_ticket_id(self, client, mock_redis, mock_config):
        """Test Zendesk webhook with missing ticket ID."""
        payload = {"ticket": {}}  # No ID
        body = json.dumps(payload).encode('utf-8')
        
        signature = hmac.new(
            mock_config.WEBHOOK_SECRET.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()
        
        with patch('aise.ticket_system.webhook_server.get_config', return_value=mock_config), \
             patch('aise.ticket_system.webhook_server.get_redis_client', return_value=mock_redis):
            
            response = client.post(
                "/webhook/zendesk",
                json=payload,
                headers={"X-Zendesk-Webhook-Signature": signature}
            )
            
            assert response.status_code == 400
            assert "Missing or invalid ticket ID" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_zendesk_webhook_ip_blocked(self, client, mock_config):
        """Test Zendesk webhook with blocked IP."""
        mock_config.WEBHOOK_ALLOWED_IPS = "192.168.1.1"
        payload = {"ticket": {"id": "12345"}}
        
        with patch('aise.ticket_system.webhook_server.get_config', return_value=mock_config):
            response = client.post("/webhook/zendesk", json=payload)
            
            assert response.status_code == 403
            assert "IP address not allowed" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_freshdesk_webhook_success(self, client, mock_redis, mock_config):
        """Test successful Freshdesk webhook reception."""
        payload = {"ticket_id": "67890", "subject": "Test ticket"}
        body = json.dumps(payload).encode('utf-8')
        
        signature = hmac.new(
            mock_config.WEBHOOK_SECRET.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()
        
        with patch('aise.ticket_system.webhook_server.get_config', return_value=mock_config), \
             patch('aise.ticket_system.webhook_server.get_redis_client', return_value=mock_redis):
            
            response = client.post(
                "/webhook/freshdesk",
                json=payload,
                headers={"X-Freshdesk-Webhook-Signature": signature}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "queued"
            assert data["ticket_id"] == "67890"
            assert data["platform"] == "freshdesk"
    
    @pytest.mark.asyncio
    async def test_slack_webhook_url_verification(self, client, mock_config):
        """Test Slack URL verification challenge."""
        payload = {
            "type": "url_verification",
            "challenge": "test-challenge-string"
        }
        
        with patch('aise.ticket_system.webhook_server.get_config', return_value=mock_config):
            response = client.post("/webhook/slack", json=payload)
            
            assert response.status_code == 200
            data = response.json()
            assert data["challenge"] == "test-challenge-string"
    
    @pytest.mark.asyncio
    async def test_slack_webhook_success(self, client, mock_redis, mock_config):
        """Test successful Slack webhook reception."""
        timestamp = str(int(time.time()))
        payload = {
            "type": "event_callback",
            "event": {
                "channel": "C12345",
                "ts": "1234567890.123456",
                "text": "Help needed"
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
             patch('aise.ticket_system.webhook_server.get_redis_client', return_value=mock_redis):
            
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
            assert "C12345" in data["ticket_id"]
            assert data["platform"] == "slack"
    
    @pytest.mark.asyncio
    async def test_slack_webhook_timestamp_expired(self, client, mock_config):
        """Test Slack webhook with expired timestamp."""
        old_timestamp = str(int(time.time()) - 400)  # 400 seconds ago (> 5 min)
        payload = {
            "type": "event_callback",
            "event": {"channel": "C12345", "ts": "1234567890.123456"}
        }
        body = json.dumps(payload).encode('utf-8')
        
        sig_basestring = f"v0:{old_timestamp}:{body.decode('utf-8')}"
        signature = 'v0=' + hmac.new(
            mock_config.SLACK_SIGNING_SECRET.encode('utf-8'),
            sig_basestring.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        with patch('aise.ticket_system.webhook_server.get_config', return_value=mock_config):
            response = client.post(
                "/webhook/slack",
                json=payload,
                headers={
                    "X-Slack-Signature": signature,
                    "X-Slack-Request-Timestamp": old_timestamp
                }
            )
            
            assert response.status_code == 401
            assert "timestamp too old" in response.json()["detail"]
