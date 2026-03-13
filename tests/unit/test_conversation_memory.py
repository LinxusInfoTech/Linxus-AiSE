# tests/unit/test_conversation_memory.py
"""Unit tests for ConversationMemory."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import json

from aise.ticket_system.memory import ConversationMemory
from aise.ticket_system.base import Message
from aise.core.exceptions import DatabaseError


@pytest.fixture
def mock_postgres_pool():
    """Create mock PostgreSQL pool."""
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    pool.acquire.return_value.__aexit__.return_value = None
    return pool


@pytest.fixture
def mock_redis_client():
    """Create mock Redis client."""
    client = AsyncMock()
    return client


@pytest.fixture
def conversation_memory(mock_postgres_pool, mock_redis_client):
    """Create ConversationMemory instance with mocks."""
    return ConversationMemory(
        postgres_pool=mock_postgres_pool,
        redis_client=mock_redis_client,
        retention_days=90,
        cache_size=10
    )


@pytest.fixture
def sample_message():
    """Create sample message."""
    return Message(
        id="msg_123",
        author="user@example.com",
        body="Hello, I need help with my EC2 instance",
        is_customer=True,
        created_at=datetime.utcnow()
    )


@pytest.mark.asyncio
async def test_store_message_success(conversation_memory, mock_postgres_pool, mock_redis_client, sample_message):
    """Test storing message successfully."""
    # Setup
    conn = mock_postgres_pool.acquire.return_value.__aenter__.return_value
    conn.execute = AsyncMock()
    
    # Execute
    await conversation_memory.store_message("ticket_123", sample_message)
    
    # Verify PostgreSQL insert
    conn.execute.assert_called_once()
    call_args = conn.execute.call_args[0]
    assert "INSERT INTO conversation_memory" in call_args[0]
    assert call_args[1] == "ticket_123"
    assert call_args[2] == "msg_123"
    assert call_args[3] == "user@example.com"
    
    # Verify Redis cache update
    mock_redis_client.rpush.assert_called_once()
    mock_redis_client.ltrim.assert_called_once()
    mock_redis_client.expire.assert_called_once()


@pytest.mark.asyncio
async def test_store_message_redis_failure_continues(conversation_memory, mock_postgres_pool, mock_redis_client, sample_message):
    """Test that Redis failure doesn't prevent PostgreSQL storage."""
    # Setup
    conn = mock_postgres_pool.acquire.return_value.__aenter__.return_value
    conn.execute = AsyncMock()
    mock_redis_client.rpush.side_effect = Exception("Redis connection failed")
    
    # Execute - should not raise exception
    await conversation_memory.store_message("ticket_123", sample_message)
    
    # Verify PostgreSQL insert still happened
    conn.execute.assert_called_once()


@pytest.mark.asyncio
async def test_store_message_postgres_failure_raises(conversation_memory, mock_postgres_pool, sample_message):
    """Test that PostgreSQL failure raises DatabaseError."""
    # Setup
    conn = mock_postgres_pool.acquire.return_value.__aenter__.return_value
    conn.execute.side_effect = Exception("Database connection failed")
    
    # Execute and verify exception
    with pytest.raises(DatabaseError) as exc_info:
        await conversation_memory.store_message("ticket_123", sample_message)
    
    assert "Failed to store message" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_thread_from_redis_cache(conversation_memory, mock_redis_client):
    """Test retrieving thread from Redis cache."""
    # Setup
    cached_data = [
        json.dumps({
            "id": "msg_1",
            "author": "user@example.com",
            "body": "First message",
            "is_customer": True,
            "created_at": datetime.utcnow().isoformat()
        }),
        json.dumps({
            "id": "msg_2",
            "author": "agent@example.com",
            "body": "Response",
            "is_customer": False,
            "created_at": datetime.utcnow().isoformat()
        })
    ]
    mock_redis_client.lrange.return_value = cached_data
    
    # Execute
    messages = await conversation_memory.get_thread("ticket_123", limit=2)
    
    # Verify
    assert len(messages) == 2
    assert messages[0].id == "msg_1"
    assert messages[0].is_customer is True
    assert messages[1].id == "msg_2"
    assert messages[1].is_customer is False
    
    # Verify Redis was called
    mock_redis_client.lrange.assert_called_once_with("conversation:ticket_123", -2, -1)


@pytest.mark.asyncio
async def test_get_thread_fallback_to_postgres(conversation_memory, mock_postgres_pool, mock_redis_client):
    """Test fallback to PostgreSQL when Redis cache misses."""
    # Setup
    mock_redis_client.lrange.return_value = []  # Cache miss
    
    conn = mock_postgres_pool.acquire.return_value.__aenter__.return_value
    conn.fetch.return_value = [
        {
            "message_id": "msg_1",
            "author": "user@example.com",
            "body": "First message",
            "is_customer": True,
            "created_at": datetime.utcnow()
        },
        {
            "message_id": "msg_2",
            "author": "agent@example.com",
            "body": "Response",
            "is_customer": False,
            "created_at": datetime.utcnow()
        }
    ]
    
    # Execute
    messages = await conversation_memory.get_thread("ticket_123", limit=2)
    
    # Verify
    assert len(messages) == 2
    assert messages[0].id == "msg_1"
    assert messages[1].id == "msg_2"
    
    # Verify PostgreSQL was called
    conn.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_get_thread_redis_failure_fallback(conversation_memory, mock_postgres_pool, mock_redis_client):
    """Test fallback to PostgreSQL when Redis fails."""
    # Setup
    mock_redis_client.lrange.side_effect = Exception("Redis connection failed")
    
    conn = mock_postgres_pool.acquire.return_value.__aenter__.return_value
    conn.fetch.return_value = [
        {
            "message_id": "msg_1",
            "author": "user@example.com",
            "body": "First message",
            "is_customer": True,
            "created_at": datetime.utcnow()
        }
    ]
    
    # Execute
    messages = await conversation_memory.get_thread("ticket_123", limit=1)
    
    # Verify
    assert len(messages) == 1
    assert messages[0].id == "msg_1"


@pytest.mark.asyncio
async def test_get_thread_no_limit(conversation_memory, mock_postgres_pool, mock_redis_client):
    """Test retrieving all messages without limit."""
    # Setup - should skip Redis and go to PostgreSQL
    conn = mock_postgres_pool.acquire.return_value.__aenter__.return_value
    conn.fetch.return_value = [
        {
            "message_id": f"msg_{i}",
            "author": "user@example.com",
            "body": f"Message {i}",
            "is_customer": True,
            "created_at": datetime.utcnow()
        }
        for i in range(20)
    ]
    
    # Execute
    messages = await conversation_memory.get_thread("ticket_123", limit=None)
    
    # Verify
    assert len(messages) == 20
    
    # Verify Redis was not called (limit=None)
    mock_redis_client.lrange.assert_not_called()


@pytest.mark.asyncio
async def test_get_recent_context(conversation_memory, mock_postgres_pool):
    """Test getting recent context formatted for LLM."""
    # Setup
    conn = mock_postgres_pool.acquire.return_value.__aenter__.return_value
    now = datetime.utcnow()
    conn.fetch.return_value = [
        {
            "message_id": "msg_1",
            "author": "user@example.com",
            "body": "I need help",
            "is_customer": True,
            "created_at": now - timedelta(minutes=10)
        },
        {
            "message_id": "msg_2",
            "author": "agent@example.com",
            "body": "How can I help?",
            "is_customer": False,
            "created_at": now - timedelta(minutes=5)
        }
    ]
    
    # Execute
    context = await conversation_memory.get_recent_context("ticket_123", turns=5)
    
    # Verify
    assert "Recent conversation history:" in context
    assert "Customer (user@example.com):" in context
    assert "Agent (agent@example.com):" in context
    assert "I need help" in context
    assert "How can I help?" in context


@pytest.mark.asyncio
async def test_get_recent_context_empty(conversation_memory, mock_postgres_pool):
    """Test getting context when no messages exist."""
    # Setup
    conn = mock_postgres_pool.acquire.return_value.__aenter__.return_value
    conn.fetch.return_value = []
    
    # Execute
    context = await conversation_memory.get_recent_context("ticket_123", turns=5)
    
    # Verify
    assert context == "No previous conversation history."


@pytest.mark.asyncio
async def test_cleanup_old_conversations(conversation_memory, mock_postgres_pool):
    """Test cleanup of old conversations."""
    # Setup
    conn = mock_postgres_pool.acquire.return_value.__aenter__.return_value
    conn.execute.return_value = "DELETE 42"
    
    # Execute
    deleted_count = await conversation_memory.cleanup_old_conversations()
    
    # Verify
    assert deleted_count == 42
    
    # Verify SQL was called with correct cutoff date
    conn.execute.assert_called_once()
    call_args = conn.execute.call_args[0]
    assert "DELETE FROM conversation_memory" in call_args[0]
    assert "WHERE created_at < $1" in call_args[0]
    
    # Verify cutoff date is approximately 90 days ago
    cutoff_date = call_args[1]
    expected_cutoff = datetime.utcnow() - timedelta(days=90)
    assert abs((cutoff_date - expected_cutoff).total_seconds()) < 60  # Within 1 minute


@pytest.mark.asyncio
async def test_cleanup_old_conversations_failure(conversation_memory, mock_postgres_pool):
    """Test cleanup failure raises DatabaseError."""
    # Setup
    conn = mock_postgres_pool.acquire.return_value.__aenter__.return_value
    conn.execute.side_effect = Exception("Database error")
    
    # Execute and verify exception
    with pytest.raises(DatabaseError) as exc_info:
        await conversation_memory.cleanup_old_conversations()
    
    assert "Failed to cleanup old conversations" in str(exc_info.value)


@pytest.mark.asyncio
async def test_redis_cache_update(conversation_memory, mock_redis_client, sample_message):
    """Test Redis cache update logic."""
    # Execute
    await conversation_memory._update_redis_cache("ticket_123", sample_message)
    
    # Verify Redis operations
    cache_key = "conversation:ticket_123"
    
    # Verify rpush was called with serialized message
    mock_redis_client.rpush.assert_called_once()
    call_args = mock_redis_client.rpush.call_args[0]
    assert call_args[0] == cache_key
    
    message_data = json.loads(call_args[1])
    assert message_data["id"] == "msg_123"
    assert message_data["author"] == "user@example.com"
    assert message_data["is_customer"] is True
    
    # Verify ltrim to keep only recent messages
    mock_redis_client.ltrim.assert_called_once_with(cache_key, -10, -1)
    
    # Verify expiration set to 1 hour
    mock_redis_client.expire.assert_called_once_with(cache_key, 3600)


@pytest.mark.asyncio
async def test_configurable_retention_days(mock_postgres_pool, mock_redis_client):
    """Test that retention days is configurable."""
    # Create with custom retention
    memory = ConversationMemory(
        postgres_pool=mock_postgres_pool,
        redis_client=mock_redis_client,
        retention_days=30
    )
    
    assert memory.retention_days == 30
    
    # Setup
    conn = mock_postgres_pool.acquire.return_value.__aenter__.return_value
    conn.execute.return_value = "DELETE 10"
    
    # Execute cleanup
    await memory.cleanup_old_conversations()
    
    # Verify cutoff date is 30 days ago
    call_args = conn.execute.call_args[0]
    cutoff_date = call_args[1]
    expected_cutoff = datetime.utcnow() - timedelta(days=30)
    assert abs((cutoff_date - expected_cutoff).total_seconds()) < 60


@pytest.mark.asyncio
async def test_configurable_cache_size(mock_postgres_pool, mock_redis_client):
    """Test that cache size is configurable."""
    # Create with custom cache size
    memory = ConversationMemory(
        postgres_pool=mock_postgres_pool,
        redis_client=mock_redis_client,
        cache_size=20
    )
    
    assert memory.cache_size == 20
    
    # Create sample message
    message = Message(
        id="msg_1",
        author="user@example.com",
        body="Test",
        is_customer=True,
        created_at=datetime.utcnow()
    )
    
    # Execute cache update
    await memory._update_redis_cache("ticket_123", message)
    
    # Verify ltrim uses custom cache size
    mock_redis_client.ltrim.assert_called_once_with("conversation:ticket_123", -20, -1)
