#!/usr/bin/env python3
"""
Example usage of ConversationMemory for ticket thread management.

This example demonstrates:
1. Storing messages in conversation history
2. Retrieving conversation threads
3. Getting recent context for LLM
4. Running cleanup jobs
"""

import asyncio
from datetime import datetime
import redis.asyncio as redis

from aise.core.config import load_config
from aise.core.database import initialize_database
from aise.ticket_system.memory import ConversationMemory
from aise.ticket_system.cleanup_job import ConversationCleanupJob
from aise.ticket_system.base import Message


async def main():
    """Main example function."""
    print("=" * 80)
    print("ConversationMemory Example")
    print("=" * 80)
    
    # Load configuration
    print("\n1. Loading configuration...")
    config = load_config()
    print(f"   PostgreSQL: {config.POSTGRES_URL}")
    print(f"   Redis: {config.REDIS_URL}")
    
    # Initialize database
    print("\n2. Initializing database...")
    db = await initialize_database(config)
    print("   Database initialized")
    
    # Initialize Redis
    print("\n3. Initializing Redis...")
    redis_client = redis.from_url(config.REDIS_URL)
    await redis_client.ping()
    print("   Redis connected")
    
    # Create ConversationMemory
    print("\n4. Creating ConversationMemory...")
    memory = ConversationMemory(
        postgres_pool=db.pool,
        redis_client=redis_client,
        retention_days=90,
        cache_size=10
    )
    print(f"   Retention: {memory.retention_days} days")
    print(f"   Cache size: {memory.cache_size} messages")
    
    # Example ticket conversation
    ticket_id = "example_ticket_123"
    
    # Store customer message
    print(f"\n5. Storing customer message for ticket {ticket_id}...")
    customer_message = Message(
        id="msg_001",
        author="customer@example.com",
        body="Hello, my EC2 instance is not responding. Instance ID: i-1234567890abcdef0",
        is_customer=True,
        created_at=datetime.utcnow()
    )
    await memory.store_message(ticket_id, customer_message)
    print("   ✓ Customer message stored")
    
    # Store agent response
    print("\n6. Storing agent response...")
    agent_message = Message(
        id="msg_002",
        author="agent@example.com",
        body="I'll help you troubleshoot this. Let me check the instance status.",
        is_customer=False,
        created_at=datetime.utcnow()
    )
    await memory.store_message(ticket_id, agent_message)
    print("   ✓ Agent message stored")
    
    # Store another customer message
    print("\n7. Storing follow-up customer message...")
    followup_message = Message(
        id="msg_003",
        author="customer@example.com",
        body="Thank you! The instance is in us-east-1.",
        is_customer=True,
        created_at=datetime.utcnow()
    )
    await memory.store_message(ticket_id, followup_message)
    print("   ✓ Follow-up message stored")
    
    # Retrieve conversation thread
    print(f"\n8. Retrieving conversation thread for ticket {ticket_id}...")
    thread = await memory.get_thread(ticket_id)
    print(f"   Found {len(thread)} messages:")
    for i, msg in enumerate(thread, 1):
        role = "Customer" if msg.is_customer else "Agent"
        print(f"   {i}. [{role}] {msg.author}: {msg.body[:50]}...")
    
    # Get recent context for LLM
    print(f"\n9. Getting recent context for LLM...")
    context = await memory.get_recent_context(ticket_id, turns=5)
    print("   Context generated:")
    print("   " + "-" * 76)
    for line in context.split("\n")[:10]:  # Show first 10 lines
        print(f"   {line}")
    print("   " + "-" * 76)
    
    # Demonstrate cache behavior
    print("\n10. Demonstrating Redis cache...")
    cache_key = f"conversation:{ticket_id}"
    cached_count = await redis_client.llen(cache_key)
    print(f"   Messages in Redis cache: {cached_count}")
    
    # Retrieve with limit (should use cache)
    print("\n11. Retrieving recent messages (from cache)...")
    recent = await memory.get_thread(ticket_id, limit=3)
    print(f"   Retrieved {len(recent)} recent messages")
    
    # Cleanup demonstration
    print("\n12. Demonstrating cleanup job...")
    cleanup_job = ConversationCleanupJob(
        memory=memory,
        interval_hours=24
    )
    print(f"   Cleanup job configured:")
    print(f"   - Interval: {cleanup_job.interval_hours} hours")
    print(f"   - Retention: {memory.retention_days} days")
    
    # Run cleanup once
    print("\n13. Running cleanup (manual)...")
    deleted_count = await cleanup_job.run_once()
    print(f"   Deleted {deleted_count} old messages")
    
    # Verify thread still exists
    print("\n14. Verifying thread still exists...")
    thread_after = await memory.get_thread(ticket_id)
    print(f"   Thread still has {len(thread_after)} messages (recent messages preserved)")
    
    # Cleanup
    print("\n15. Cleaning up...")
    await redis_client.close()
    await db.close()
    print("   ✓ Connections closed")
    
    print("\n" + "=" * 80)
    print("Example completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
