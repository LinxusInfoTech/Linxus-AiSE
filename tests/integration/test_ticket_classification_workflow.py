# tests/integration/test_ticket_classification_workflow.py
"""Integration tests for ticket classification workflow."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

from aise.ticket_system.processor import TicketProcessor
from aise.ticket_system.base import Ticket, TicketStatus, Message
from aise.agents.state import TicketAnalysis
from aise.ai_engine.base import CompletionResult, TokenUsage


@pytest.fixture
def sample_ticket():
    """Create sample ticket."""
    return Ticket(
        id="ticket-123",
        subject="EC2 instance unreachable",
        body="My EC2 instance i-1234567890abcdef0 is not responding to SSH connections.",
        customer_email="customer@example.com",
        status=TicketStatus.OPEN,
        tags=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        thread=[]
    )


@pytest.fixture
def mock_ticket_provider(sample_ticket):
    """Create mock ticket provider."""
    provider = Mock()
    provider.get = AsyncMock(return_value=sample_ticket)
    provider.add_tags = AsyncMock()
    provider.reply = AsyncMock()
    return provider


@pytest.fixture
def mock_llm_router():
    """Create mock LLM router."""
    router = Mock()
    
    # Mock classification response
    classification_response = """{
  "category": "cloud_infra",
  "severity": "high",
  "affected_service": "EC2",
  "customer_context": "Customer cannot SSH to EC2 instance",
  "suggested_tags": ["ec2", "networking", "ssh"]
}"""
    
    # Mock diagnosis response
    diagnosis_response = """Based on the ticket, the EC2 instance is unreachable via SSH. 

Possible causes:
1. Security group rules blocking SSH (port 22)
2. Network ACL restrictions
3. Instance stopped or terminated
4. SSH service not running on instance

Recommended troubleshooting:
1. Check security group inbound rules for port 22
2. Verify instance state is 'running'
3. Check VPC network ACLs
4. Review system logs for SSH service status"""
    
    router.complete = AsyncMock(side_effect=[
        CompletionResult(
            content=classification_response,
            model="claude-3-sonnet",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            provider="anthropic"
        ),
        CompletionResult(
            content=diagnosis_response,
            model="claude-3-sonnet",
            usage=TokenUsage(prompt_tokens=200, completion_tokens=100, total_tokens=300),
            provider="anthropic"
        )
    ])
    
    return router


@pytest.mark.asyncio
async def test_process_ticket_with_classification(mock_ticket_provider, mock_llm_router):
    """Test complete ticket processing workflow with classification."""
    processor = TicketProcessor(
        ticket_provider=mock_ticket_provider,
        llm_router=mock_llm_router,
        mode="approval"
    )
    
    # Process ticket
    state = await processor.process_ticket("ticket-123")
    
    # Verify ticket was fetched
    mock_ticket_provider.get.assert_called_once_with("ticket-123")
    
    # Verify classification was performed
    assert state["ticket_analysis"] is not None
    assert state["ticket_analysis"].category == "cloud_infra"
    assert state["ticket_analysis"].severity == "high"
    assert state["ticket_analysis"].affected_service == "EC2"
    
    # Verify tags were added
    mock_ticket_provider.add_tags.assert_called_once()
    call_args = mock_ticket_provider.add_tags.call_args
    assert call_args[0][0] == "ticket-123"
    assert "ec2" in call_args[0][1]
    assert "networking" in call_args[0][1]
    
    # Verify diagnosis was generated
    assert state["diagnosis"] is not None
    assert "Security group" in state["diagnosis"]
    
    # Verify reply was NOT posted (approval mode)
    mock_ticket_provider.reply.assert_not_called()


@pytest.mark.asyncio
async def test_process_ticket_autonomous_mode(mock_ticket_provider, mock_llm_router):
    """Test ticket processing in autonomous mode posts reply."""
    processor = TicketProcessor(
        ticket_provider=mock_ticket_provider,
        llm_router=mock_llm_router,
        mode="autonomous"
    )
    
    # Process ticket with auto_reply
    state = await processor.process_ticket("ticket-123", auto_reply=True)
    
    # Verify reply was posted
    mock_ticket_provider.reply.assert_called_once()
    call_args = mock_ticket_provider.reply.call_args
    assert call_args[0][0] == "ticket-123"
    assert "Security group" in call_args[0][1]


@pytest.mark.asyncio
async def test_process_ticket_with_knowledge_agent(mock_ticket_provider, mock_llm_router):
    """Test ticket processing with knowledge retrieval."""
    # Create mock knowledge agent
    mock_knowledge_agent = Mock()
    mock_knowledge_agent.retrieve = AsyncMock(return_value=[
        {
            "text": "EC2 security groups control inbound and outbound traffic",
            "source_url": "https://docs.aws.amazon.com/ec2/security-groups",
            "source_name": "aws",
            "heading_context": "EC2 > Security Groups",
            "score": 0.95
        }
    ])
    
    processor = TicketProcessor(
        ticket_provider=mock_ticket_provider,
        llm_router=mock_llm_router,
        knowledge_agent=mock_knowledge_agent,
        mode="approval"
    )
    
    # Process ticket
    state = await processor.process_ticket("ticket-123")
    
    # Verify knowledge was retrieved
    mock_knowledge_agent.retrieve.assert_called_once()
    call_args = mock_knowledge_agent.retrieve.call_args
    
    # Verify query includes classification context
    query = call_args.kwargs["query"]
    assert "EC2" in query
    assert "cloud_infra" in query
    
    # Verify knowledge context in state
    assert len(state["knowledge_context"]) > 0


@pytest.mark.asyncio
async def test_process_ticket_with_conversation_memory(mock_ticket_provider, mock_llm_router):
    """Test ticket processing with conversation memory."""
    # Create mock conversation memory
    mock_memory = Mock()
    mock_memory.get_thread = AsyncMock(return_value=[
        Message(
            id="msg-1",
            author="customer@example.com",
            body="My EC2 instance is not responding",
            is_customer=True,
            created_at=datetime.utcnow()
        ),
        Message(
            id="msg-2",
            author="agent@support.com",
            body="Can you provide the instance ID?",
            is_customer=False,
            created_at=datetime.utcnow()
        )
    ])
    mock_memory.store_message = AsyncMock()
    
    processor = TicketProcessor(
        ticket_provider=mock_ticket_provider,
        llm_router=mock_llm_router,
        conversation_memory=mock_memory,
        mode="approval"
    )
    
    # Process ticket
    state = await processor.process_ticket("ticket-123")
    
    # Verify conversation memory was loaded
    mock_memory.get_thread.assert_called_once_with("ticket-123")
    
    # Verify messages in state
    assert len(state["messages"]) == 2
    assert state["messages"][0]["role"] == "user"
    assert state["messages"][1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_classification_filters_knowledge_retrieval(mock_ticket_provider, mock_llm_router):
    """Test that classification results filter knowledge retrieval."""
    # Create mock knowledge agent
    mock_knowledge_agent = Mock()
    mock_knowledge_agent.retrieve = AsyncMock(return_value=[])
    
    processor = TicketProcessor(
        ticket_provider=mock_ticket_provider,
        llm_router=mock_llm_router,
        knowledge_agent=mock_knowledge_agent,
        mode="approval"
    )
    
    # Process ticket
    await processor.process_ticket("ticket-123")
    
    # Verify knowledge retrieval was called with filtered query
    call_args = mock_knowledge_agent.retrieve.call_args
    
    # Query should include affected service and category
    query = call_args.kwargs["query"]
    assert "EC2" in query
    assert "cloud_infra" in query
    
    # Source filter should be set for AWS services
    source_filter = call_args.kwargs.get("source_filter")
    assert source_filter == "aws"


@pytest.mark.asyncio
async def test_process_ticket_stores_classification_in_state(mock_ticket_provider, mock_llm_router):
    """Test that classification results are stored in state."""
    processor = TicketProcessor(
        ticket_provider=mock_ticket_provider,
        llm_router=mock_llm_router,
        mode="approval"
    )
    
    # Process ticket
    state = await processor.process_ticket("ticket-123")
    
    # Verify classification in state
    assert "ticket_analysis" in state
    assert state["ticket_analysis"] is not None
    assert isinstance(state["ticket_analysis"], TicketAnalysis)
    assert state["ticket_analysis"].category == "cloud_infra"
    assert state["ticket_analysis"].severity == "high"
    assert state["ticket_analysis"].affected_service == "EC2"
    assert len(state["ticket_analysis"].suggested_tags) > 0


@pytest.mark.asyncio
async def test_process_ticket_adds_suggested_tags(mock_ticket_provider, mock_llm_router):
    """Test that suggested tags are added to ticket."""
    processor = TicketProcessor(
        ticket_provider=mock_ticket_provider,
        llm_router=mock_llm_router,
        mode="approval"
    )
    
    # Process ticket
    await processor.process_ticket("ticket-123")
    
    # Verify tags were added
    mock_ticket_provider.add_tags.assert_called_once()
    call_args = mock_ticket_provider.add_tags.call_args
    
    ticket_id = call_args[0][0]
    tags = call_args[0][1]
    
    assert ticket_id == "ticket-123"
    assert "ec2" in tags
    assert "networking" in tags
    assert "ssh" in tags
