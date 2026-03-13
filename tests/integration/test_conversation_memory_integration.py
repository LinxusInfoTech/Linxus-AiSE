# tests/integration/test_conversation_memory_integration.py
"""Integration tests for ConversationMemory with real database connections."""

import pytest
import asyncio
from datetime import datetime, timedelta
import os

from aise.ticket_system.memory import ConversationMemory
from aise.ticket_system.cleanup_job import ConversationCleanupJob
from aise.ticket_system.base import Message
from aise.core.database import DatabaseManager
from aise.core.config import Config

# Skip integration tests if database not available
pytestmark = pytest.mark.skipif(
    not os.environ.get("POSTGRES_URL") or not os.environ.get("REDIS_URL"),
    reason="Database not configured for integration tests"
)


@pytest.fixture
async def database_manager():
    """Create database manager for tests."""
    # Use test database
    config = Config(
        POSTGRES_URL=os.environ.get("POSTGRES_URL", "postgresql://aise:password@localhost:5432/aise_test"),
        REDIS_URL=os.environ.get("REDIS_URL", "redis://localhost:6379/1"),
        ANTHROPIC_API_KEY="test-key"
    )
    
    db = DatabaseManager(config)
    await db.initialize()
    
    yield db
    
    await db.close()


@pytest.fixture
async def redis_client():
    """Create Redis client for tests."""
    import redis.asyncio as redis
    
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/1")
    client = redis.from_url(redis_url)
    
    yield client
    
    # Cleanup
    await client.flushdb()
    await client.close()


@pytest.fixture
async def conversation_memory(database_manager, redis_client):
    """Create ConversationMemory instance with real connections."""
    memory = ConversationMemory(
        postgres_pool=database_manager.pool,
        redis_client=redis_client,
        retention_days=90,
        cache_size=10
    )
    
    yield memory
    
    # Cleanup test data
    async with database_manager.pool.acquire() as conn:
        await conn.execute("DELETE FROM conversation_memory WHERE ticket_id LIKE 'test_%'")


@pytest.mark.asyncio
async def test_store_and_retrieve_message(conversation_memory):
    """Test storing and retrieving a message."""
    # Create message
    message = Message(
        id="test_msg_1",
        author="user@example.com",
        body="I need help with my EC2 instance",
        is_customer=True,
        created_at=datetime.utcnow()
    )
    
    # Store message
    await conversation_memory.store_message("test_ticket_1", message)
    
    # Retrieve thread
    thread = await conversation_memory.get_thread("test_ticket_1")
    
    # Verify
    assert len(thread) == 1
    assert thread[0].id == "test_msg_1"
    assert thread[0].author == "user@example.com"
    assert thread[0].body == "I need help with my EC2 instance"
    assert thread[0].is_customer is True


@pytest.mark.asyncio
async def test_multiple_messages_chronological_order(conversation_memory):
    """Test that messages are returned in chronological order."""
    # Create messages with different timestamps
    messages = []
    for i in range(5):
        message = Message(
            id=f"test_msg_{i}",
            author=f"user{i}@example.com",
            body=f"Message {i}",
            is_customer=i % 2 == 0,
            created_at=datetime.utcnow() + timedelta(seconds=i)
        )
        messages.append(message)
        await conversation_memory.store_message("test_ticket_2", message)
        await asyncio.sleep(0.1)  # Small delay to ensure different timestamps
    
    # Retrieve thread
    thread = await conversation_memory.get_thread("test_ticket_2")
    
    # Verify chronological order
    assert len(thread) == 5
    for i, msg in enumerate(thread):
        assert msg.id == f"test_msg_{i}"
        assert msg.body == f"Message {i}"


@pytest.mark.asyncio
async def test_redis_cache_hit(conversation_memory, redis_client):
    """Test that recent messages are cached in Redis."""
    # Store messages
    for i in range(3):
        message = Message(
            id=f"test_msg_{i}",
            author="user@example.com",
            body=f"Message {i}",
            is_customer=True,
            created_at=datetime.utcnow()
        )
        await conversation_memory.store_message("test_ticket_3", message)
    
    # Verify Redis cache contains messages
    cache_key = "conversation:test_ticket_3"
    cached_count = await redis_client.llen(cache_key)
    assert cached_count == 3
    
    # Retrieve from cache (limit within cache size)
    thread = await conversation_memory.get_thread("test_ticket_3", limit=3)
    assert len(thread) == 3


@pytest.mark.asyncio
async def test_redis_fallback_to_postgres(conversation_memory, redis_client):
    """Test fallback to PostgreSQL when Redis is unavailable."""
    # Store message
    message = Message(
        id="test_msg_fallback",
        author="user@example.com",
        body="Test fallback",
        is_customer=True,
        created_at=datetime.utcnow()
    )
    await conversation_memory.store_message("test_ticket_4", message)
    
    # Clear Redis cache
    await redis_client.delete("conversation:test_ticket_4")
    
    # Retrieve should fallback to PostgreSQL
    thread = await conversation_memory.get_thread("test_ticket_4", limit=1)
    assert len(thread) == 1
    assert thread[0].id == "test_msg_fallback"


@pytest.mark.asyncio
async def test_get_recent_context_formatting(conversation_memory):
    """Test that recent context is properly formatted."""
    # Store conversation
    messages = [
        Message(
            id="test_msg_1",
            author="customer@example.com",
            body="I have a problem",
            is_customer=True,
            created_at=datetime.utcnow()
        ),
        Message(
            id="test_msg_2",
            author="agent@example.com",
            body="How can I help?",
            is_customer=False,
            created_at=datetime.utcnow() + timedelta(seconds=1)
        )
    ]
    
    for msg in messages:
        await conversation_memory.store_message("test_ticket_5", msg)
    
    # Get context
    context = await conversation_memory.get_recent_context("test_ticket_5", turns=5)
    
    # Verify formatting
    assert "Recent conversation history:" in context
    assert "Customer (customer@example.com):" in context
    assert "Agent (agent@example.com):" in context
    assert "I have a problem" in context
    assert "How can I help?" in context


@pytest.mark.asyncio
async def test_cleanup_old_conversations(conversation_memory, database_manager):
    """Test cleanup of old conversations."""
    # Store old message (91 days ago)
    old_message = Message(
        id="test_msg_old",
        author="user@example.com",
        body="Old message",
        is_customer=True,
        created_at=datetime.utcnow() - timedelta(days=91)
    )
    
    # Manually insert old message
    async with database_manager.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO conversation_memory 
            (ticket_id, message_id, author, body, is_customer, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            "test_ticket_old",
            old_message.id,
            old_message.author,
            old_message.body,
            old_message.is_customer,
            old_message.created_at
        )
    
    # Store recent message
    recent_message = Message(
        id="test_msg_recent",
        author="user@example.com",
        body="Recent message",
        is_customer=True,
        created_at=datetime.utcnow()
    )
    await conversation_memory.store_message("test_ticket_recent", recent_message)
    
    # Run cleanup
    deleted_count = await conversation_memory.cleanup_old_conversations()
    
    # Verify old message was deleted
    assert deleted_count >= 1
    
    # Verify recent message still exists
    thread = await conversation_memory.get_thread("test_ticket_recent")
    assert len(thread) == 1
    assert thread[0].id == "test_msg_recent"


@pytest.mark.asyncio
async def test_cleanup_job_execution(conversation_memory):
    """Test background cleanup job."""
    # Create cleanup job with short interval for testing
    cleanup_job = ConversationCleanupJob(
        memory=conversation_memory,
        interval_hours=1
    )
    
    # Run cleanup once
    deleted_count = await cleanup_job.run_once()
    
    # Should complete without error
    assert deleted_count >= 0


@pytest.mark.asyncio
async def test_cache_size_limit(conversation_memory, redis_client):
    """Test that Redis cache respects size limit."""
    # Store more messages than cache size
    for i in range(15):
        message = Message(
            id=f"test_msg_{i}",
            author="user@example.com",
            body=f"Message {i}",
            is_customer=True,
            created_at=datetime.utcnow()
        )
        await conversation_memory.store_message("test_ticket_6", message)
    
    # Verify Redis cache is limited to cache_size (10)
    cache_key = "conversation:test_ticket_6"
    cached_count = await redis_client.llen(cache_key)
    assert cached_count == 10
    
    # Verify all messages are in PostgreSQL
    thread = await conversation_memory.get_thread("test_ticket_6", limit=None)
    assert len(thread) == 15


@pytest.mark.asyncio
async def test_duplicate_message_handling(conversation_memory):
    """Test that duplicate message IDs are handled correctly."""
    # Store message
    message = Message(
        id="test_msg_duplicate",
        author="user@example.com",
        body="Original message",
        is_customer=True,
        created_at=datetime.utcnow()
    )
    await conversation_memory.store_message("test_ticket_7", message)
    
    # Store same message ID with different content
    updated_message = Message(
        id="test_msg_duplicate",
        author="user@example.com",
        body="Updated message",
        is_customer=True,
        created_at=datetime.utcnow()
    )
    await conversation_memory.store_message("test_ticket_7", updated_message)
    
    # Verify only one message exists with updated content
    thread = await conversation_memory.get_thread("test_ticket_7")
    assert len(thread) == 1
    assert thread[0].body == "Updated message"


@pytest.mark.asyncio
async def test_configurable_retention_period(database_manager, redis_client):
    """Test that retention period is configurable."""
    # Create memory with 30-day retention
    memory = ConversationMemory(
        postgres_pool=database_manager.pool,
        redis_client=redis_client,
        retention_days=30
    )
    
    # Store old message (31 days ago)
    async with database_manager.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO conversation_memory 
            (ticket_id, message_id, author, body, is_customer, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            "test_ticket_retention",
            "test_msg_31days",
            "user@example.com",
            "Old message",
            True,
            datetime.utcnow() - timedelta(days=31)
        )
    
    # Run cleanup
    deleted_count = await memory.cleanup_old_conversations()
    
    # Verify message was deleted
    assert deleted_count >= 1
