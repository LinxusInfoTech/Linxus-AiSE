# tests/integration/test_graph_workflow.py
"""Integration tests for AiSEGraph workflow."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from aise.agents.graph import AiSEGraph
from aise.agents.state import create_initial_state, Ticket, TicketStatus
from aise.agents.ticket_agent import TicketAgent
from aise.agents.knowledge_agent import KnowledgeAgent
from aise.agents.engineer_agent import EngineerAgent


@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_ticket_workflow():
    """Test complete ticket processing workflow end-to-end."""
    # Setup mock dependencies
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=MagicMock(
        content='{"category": "cloud_infra", "severity": "high", "affected_service": "EC2", "suggested_tags": ["ec2", "networking"]}',
        usage=MagicMock(total_tokens=100, estimated_cost_usd=0.001)
    ))
    
    mock_vector_store = MagicMock()
    mock_vector_store.search = AsyncMock(return_value=[])
    mock_vector_store.list_all_sources = AsyncMock(return_value=["aws"])
    
    mock_embedder = MagicMock()
    
    mock_ticket_provider = MagicMock()
    mock_ticket_provider.get = AsyncMock(return_value=Ticket(
        id="ticket-123",
        subject="EC2 instance unreachable",
        body="Cannot connect to i-1234567890 via SSH",
        customer_email="user@example.com",
        status=TicketStatus.OPEN,
        tags=[],
        created_at=datetime.now(),
        updated_at=datetime.now(),
        thread=[]
    ))
    mock_ticket_provider.reply = AsyncMock()
    
    # Create agents
    ticket_agent = TicketAgent(mock_llm)
    knowledge_agent = KnowledgeAgent(mock_vector_store, mock_embedder)
    engineer_agent = EngineerAgent(mock_llm)
    
    # Create graph
    graph = AiSEGraph(
        ticket_agent=ticket_agent,
        knowledge_agent=knowledge_agent,
        engineer_agent=engineer_agent,
        ticket_provider=mock_ticket_provider
    )
    
    # Create initial state
    state = create_initial_state(
        messages=[{"role": "user", "content": "EC2 instance unreachable"}],
        mode="autonomous",
        ticket_id="ticket-123"
    )
    
    # Execute workflow
    final_state = await graph.run(state)
    
    # Verify workflow completed
    assert final_state["ticket"] is not None
    assert final_state["ticket_analysis"] is not None
    assert final_state["diagnosis"] is not None
    assert len(final_state["actions_taken"]) > 0
    
    # Verify ticket was fetched
    mock_ticket_provider.get.assert_called_once_with("ticket-123")
    
    # Verify reply was posted (autonomous mode)
    mock_ticket_provider.reply.assert_called_once()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_approval_workflow_pauses():
    """Test that approval mode pauses before posting reply."""
    # Setup mock dependencies
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=MagicMock(
        content='{"category": "cloud_infra", "severity": "high", "affected_service": "EC2", "suggested_tags": ["ec2"]}',
        usage=MagicMock(total_tokens=100, estimated_cost_usd=0.001)
    ))
    
    mock_ticket_provider = MagicMock()
    mock_ticket_provider.get = AsyncMock(return_value=Ticket(
        id="ticket-456",
        subject="Test ticket",
        body="Test body",
        customer_email="user@example.com",
        status=TicketStatus.OPEN,
        tags=[],
        created_at=datetime.now(),
        updated_at=datetime.now(),
        thread=[]
    ))
    mock_ticket_provider.reply = AsyncMock()
    
    # Create agents
    ticket_agent = TicketAgent(mock_llm)
    engineer_agent = EngineerAgent(mock_llm)
    
    # Create graph without knowledge agent
    graph = AiSEGraph(
        ticket_agent=ticket_agent,
        knowledge_agent=None,
        engineer_agent=engineer_agent,
        ticket_provider=mock_ticket_provider
    )
    
    # Create initial state in approval mode
    state = create_initial_state(
        messages=[{"role": "user", "content": "Test"}],
        mode="approval",
        ticket_id="ticket-456"
    )
    
    # Execute workflow
    final_state = await graph.run(state)
    
    # Verify workflow paused for approval
    assert final_state["pending_approval"] is not None
    assert final_state["pending_approval"]["action"] == "post_reply"
    
    # Verify reply was NOT posted yet
    mock_ticket_provider.reply.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_interactive_mode_no_ticket():
    """Test interactive mode without ticket processing."""
    # Setup mock dependencies
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=MagicMock(
        content="The issue is likely due to security group configuration.",
        usage=MagicMock(total_tokens=50, estimated_cost_usd=0.0005)
    ))
    
    # Create agents
    ticket_agent = TicketAgent(mock_llm)
    engineer_agent = EngineerAgent(mock_llm)
    
    # Create graph
    graph = AiSEGraph(
        ticket_agent=ticket_agent,
        knowledge_agent=None,
        engineer_agent=engineer_agent,
        ticket_provider=None
    )
    
    # Create initial state without ticket
    state = create_initial_state(
        messages=[{"role": "user", "content": "Why can't I SSH to my EC2 instance?"}],
        mode="interactive"
    )
    
    # Execute workflow
    final_state = await graph.run(state)
    
    # Verify diagnosis generated
    assert final_state["diagnosis"] is not None
    assert "security group" in final_state["diagnosis"].lower()
    
    # Verify no ticket processing
    assert final_state["ticket"] is None
    assert final_state["ticket_analysis"] is None
    assert final_state["pending_approval"] is None
