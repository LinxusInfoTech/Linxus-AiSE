#!/usr/bin/env python3
"""Example usage of AiSEGraph orchestration.

This example demonstrates how to use the AiSEGraph to process
tickets and questions through the complete workflow.
"""

import asyncio
from datetime import datetime

from aise.agents.graph import AiSEGraph
from aise.agents.state import create_initial_state, Ticket, TicketStatus
from aise.agents.ticket_agent import TicketAgent
from aise.agents.knowledge_agent import KnowledgeAgent
from aise.agents.engineer_agent import EngineerAgent
from aise.ai_engine.router import LLMRouter
from aise.core.config import get_config


async def example_interactive_mode():
    """Example: Interactive mode without ticket."""
    print("\n=== Interactive Mode Example ===\n")
    
    # Setup
    config = get_config()
    llm_router = LLMRouter(config)
    
    # Create agents
    ticket_agent = TicketAgent(llm_router)
    engineer_agent = EngineerAgent(llm_router)
    
    # Create graph (without knowledge agent for simplicity)
    graph = AiSEGraph(
        ticket_agent=ticket_agent,
        knowledge_agent=None,
        engineer_agent=engineer_agent,
        ticket_provider=None
    )
    
    # Create initial state
    state = create_initial_state(
        messages=[
            {"role": "user", "content": "Why can't I SSH to my EC2 instance?"}
        ],
        mode="interactive"
    )
    
    # Execute graph
    print("Processing question...")
    final_state = await graph.run(state)
    
    # Display results
    print(f"\nDiagnosis:\n{final_state['diagnosis']}\n")
    print(f"Actions taken: {', '.join(final_state['actions_taken'])}")


async def example_approval_mode():
    """Example: Approval mode with ticket."""
    print("\n=== Approval Mode Example ===\n")
    
    # Setup
    config = get_config()
    llm_router = LLMRouter(config)
    
    # Create mock ticket provider
    class MockTicketProvider:
        async def get(self, ticket_id):
            return Ticket(
                id=ticket_id,
                subject="EC2 instance unreachable",
                body="Cannot connect to i-1234567890 via SSH. Security groups look correct.",
                customer_email="user@example.com",
                status=TicketStatus.OPEN,
                tags=[],
                created_at=datetime.now(),
                updated_at=datetime.now(),
                thread=[]
            )
        
        async def reply(self, ticket_id, message):
            print(f"[MOCK] Posted reply to ticket {ticket_id}")
    
    # Create agents
    ticket_agent = TicketAgent(llm_router)
    engineer_agent = EngineerAgent(llm_router)
    
    # Create graph
    graph = AiSEGraph(
        ticket_agent=ticket_agent,
        knowledge_agent=None,
        engineer_agent=engineer_agent,
        ticket_provider=MockTicketProvider()
    )
    
    # Create initial state
    state = create_initial_state(
        messages=[{"role": "user", "content": "EC2 issue"}],
        mode="approval",
        ticket_id="ticket-123"
    )
    
    # Execute graph
    print("Processing ticket...")
    final_state = await graph.run(state)
    
    # Display results
    print(f"\nTicket Classification:")
    if final_state["ticket_analysis"]:
        print(f"  Category: {final_state['ticket_analysis'].category}")
        print(f"  Severity: {final_state['ticket_analysis'].severity}")
        print(f"  Service: {final_state['ticket_analysis'].affected_service}")
    
    print(f"\nDiagnosis:\n{final_state['diagnosis']}\n")
    
    # Check for pending approval
    if final_state["pending_approval"]:
        print("⚠️  Pending Approval Required:")
        print(f"  Action: {final_state['pending_approval']['action']}")
        print(f"  Reason: {final_state['pending_approval']['reason']}")
        print(f"\nProposed reply:\n{final_state['pending_approval']['message']}\n")
    else:
        print("✓ Reply posted automatically")


async def example_autonomous_mode():
    """Example: Autonomous mode with automatic reply."""
    print("\n=== Autonomous Mode Example ===\n")
    
    # Setup
    config = get_config()
    llm_router = LLMRouter(config)
    
    # Create mock ticket provider
    class MockTicketProvider:
        async def get(self, ticket_id):
            return Ticket(
                id=ticket_id,
                subject="Pod CrashLoopBackOff",
                body="My Kubernetes pod keeps crashing with OOMKilled error.",
                customer_email="user@example.com",
                status=TicketStatus.OPEN,
                tags=[],
                created_at=datetime.now(),
                updated_at=datetime.now(),
                thread=[]
            )
        
        async def reply(self, ticket_id, message):
            print(f"✓ Posted reply to ticket {ticket_id}")
            print(f"  Reply preview: {message[:100]}...")
    
    # Create agents
    ticket_agent = TicketAgent(llm_router)
    engineer_agent = EngineerAgent(llm_router)
    
    # Create graph
    graph = AiSEGraph(
        ticket_agent=ticket_agent,
        knowledge_agent=None,
        engineer_agent=engineer_agent,
        ticket_provider=MockTicketProvider()
    )
    
    # Create initial state
    state = create_initial_state(
        messages=[{"role": "user", "content": "Kubernetes pod issue"}],
        mode="autonomous",
        ticket_id="ticket-456"
    )
    
    # Execute graph
    print("Processing ticket in autonomous mode...")
    final_state = await graph.run(state)
    
    # Display results
    print(f"\nTicket Classification:")
    if final_state["ticket_analysis"]:
        print(f"  Category: {final_state['ticket_analysis'].category}")
        print(f"  Severity: {final_state['ticket_analysis'].severity}")
    
    print(f"\nActions taken: {', '.join(final_state['actions_taken'])}")
    print(f"Pending approval: {final_state['pending_approval'] is not None}")


async def main():
    """Run all examples."""
    try:
        await example_interactive_mode()
        await example_approval_mode()
        await example_autonomous_mode()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nNote: This example requires valid LLM API credentials.")
        print("Set ANTHROPIC_API_KEY or OPENAI_API_KEY in your .env file.")


if __name__ == "__main__":
    asyncio.run(main())
