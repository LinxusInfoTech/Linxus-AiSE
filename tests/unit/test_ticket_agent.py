# tests/unit/test_ticket_agent.py
"""Unit tests for Ticket Agent."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock

from aise.agents.ticket_agent import TicketAgent
from aise.agents.state import TicketAnalysis
from aise.ticket_system.base import Ticket, TicketStatus, Message
from aise.ai_engine.base import CompletionResult, TokenUsage
from aise.core.exceptions import ProviderError


@pytest.fixture
def mock_llm_router():
    """Create mock LLM router."""
    router = Mock()
    router.complete = AsyncMock()
    return router


@pytest.fixture
def sample_ticket():
    """Create sample ticket for testing."""
    return Ticket(
        id="ticket-123",
        subject="EC2 instance unreachable",
        body="My EC2 instance i-1234567890abcdef0 is not responding to SSH connections. I recently modified the security group.",
        customer_email="customer@example.com",
        status=TicketStatus.OPEN,
        tags=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        thread=[]
    )


@pytest.fixture
def sample_classification_response():
    """Sample LLM classification response."""
    return """{
  "category": "cloud_infra",
  "severity": "high",
  "affected_service": "EC2",
  "customer_context": "Customer cannot SSH to EC2 instance after security group modification",
  "suggested_tags": ["ec2", "networking", "ssh", "security-group"]
}"""


@pytest.mark.asyncio
async def test_classify_ticket_success(mock_llm_router, sample_ticket, sample_classification_response):
    """Test successful ticket classification."""
    # Setup mock response
    mock_llm_router.complete.return_value = CompletionResult(
        content=sample_classification_response,
        model="claude-3-sonnet",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150, estimated_cost_usd=0.001),
        provider="anthropic"
    )
    
    # Create agent and classify
    agent = TicketAgent(mock_llm_router)
    analysis = await agent.classify(sample_ticket)
    
    # Verify result
    assert isinstance(analysis, TicketAnalysis)
    assert analysis.category == "cloud_infra"
    assert analysis.severity == "high"
    assert analysis.affected_service == "EC2"
    assert "ec2" in analysis.suggested_tags
    assert "networking" in analysis.suggested_tags
    assert analysis.confidence == 0.85
    
    # Verify LLM was called correctly
    mock_llm_router.complete.assert_called_once()
    call_args = mock_llm_router.complete.call_args
    assert call_args.kwargs["temperature"] == 0.3
    assert call_args.kwargs["max_tokens"] == 512


@pytest.mark.asyncio
async def test_classify_billing_ticket(mock_llm_router):
    """Test classification of billing ticket."""
    billing_ticket = Ticket(
        id="ticket-456",
        subject="Unexpected charges on my bill",
        body="I see charges for S3 storage that I don't recognize. Can you help me understand what these are for?",
        customer_email="customer@example.com",
        status=TicketStatus.OPEN,
        tags=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        thread=[]
    )
    
    billing_response = """{
  "category": "billing",
  "severity": "medium",
  "affected_service": "S3",
  "customer_context": "Customer has unexpected S3 storage charges and needs explanation",
  "suggested_tags": ["billing", "s3", "cost-analysis"]
}"""
    
    mock_llm_router.complete.return_value = CompletionResult(
        content=billing_response,
        model="claude-3-sonnet",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        provider="anthropic"
    )
    
    agent = TicketAgent(mock_llm_router)
    analysis = await agent.classify(billing_ticket)
    
    assert analysis.category == "billing"
    assert analysis.severity == "medium"
    assert analysis.affected_service == "S3"


@pytest.mark.asyncio
async def test_classify_critical_severity(mock_llm_router):
    """Test classification of critical severity ticket."""
    critical_ticket = Ticket(
        id="ticket-789",
        subject="URGENT: Production database down",
        body="Our production RDS database is completely unresponsive. All services are down. This is affecting thousands of users.",
        customer_email="customer@example.com",
        status=TicketStatus.OPEN,
        tags=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        thread=[]
    )
    
    critical_response = """{
  "category": "cloud_infra",
  "severity": "critical",
  "affected_service": "RDS",
  "customer_context": "Production database outage affecting thousands of users",
  "suggested_tags": ["rds", "database", "outage", "production", "critical"]
}"""
    
    mock_llm_router.complete.return_value = CompletionResult(
        content=critical_response,
        model="claude-3-sonnet",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        provider="anthropic"
    )
    
    agent = TicketAgent(mock_llm_router)
    analysis = await agent.classify(critical_ticket)
    
    assert analysis.severity == "critical"
    assert analysis.category == "cloud_infra"


@pytest.mark.asyncio
async def test_classify_with_thread_context(mock_llm_router):
    """Test classification includes thread context."""
    ticket_with_thread = Ticket(
        id="ticket-999",
        subject="Lambda function timeout",
        body="My Lambda function keeps timing out",
        customer_email="customer@example.com",
        status=TicketStatus.OPEN,
        tags=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        thread=[
            Message(
                id="msg-1",
                author="customer@example.com",
                body="The timeout happens when processing large files",
                is_customer=True,
                created_at=datetime.utcnow()
            ),
            Message(
                id="msg-2",
                author="agent@support.com",
                body="What is your current timeout setting?",
                is_customer=False,
                created_at=datetime.utcnow()
            ),
            Message(
                id="msg-3",
                author="customer@example.com",
                body="It's set to 30 seconds",
                is_customer=True,
                created_at=datetime.utcnow()
            )
        ]
    )
    
    lambda_response = """{
  "category": "cloud_infra",
  "severity": "medium",
  "affected_service": "Lambda",
  "customer_context": "Lambda function timing out at 30 seconds when processing large files",
  "suggested_tags": ["lambda", "timeout", "performance"]
}"""
    
    mock_llm_router.complete.return_value = CompletionResult(
        content=lambda_response,
        model="claude-3-sonnet",
        usage=TokenUsage(prompt_tokens=150, completion_tokens=60, total_tokens=210),
        provider="anthropic"
    )
    
    agent = TicketAgent(mock_llm_router)
    analysis = await agent.classify(ticket_with_thread)
    
    # Verify thread context was included in prompt
    call_args = mock_llm_router.complete.call_args
    prompt_content = call_args.kwargs["messages"][0]["content"]
    assert "Recent conversation:" in prompt_content
    assert "large files" in prompt_content


@pytest.mark.asyncio
async def test_classify_handles_invalid_category(mock_llm_router, sample_ticket):
    """Test classification handles invalid category gracefully."""
    invalid_response = """{
  "category": "invalid_category",
  "severity": "high",
  "affected_service": "EC2",
  "customer_context": "Test",
  "suggested_tags": ["test"]
}"""
    
    mock_llm_router.complete.return_value = CompletionResult(
        content=invalid_response,
        model="claude-3-sonnet",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        provider="anthropic"
    )
    
    agent = TicketAgent(mock_llm_router)
    analysis = await agent.classify(sample_ticket)
    
    # Should default to "general"
    assert analysis.category == "general"


@pytest.mark.asyncio
async def test_classify_handles_invalid_severity(mock_llm_router, sample_ticket):
    """Test classification handles invalid severity gracefully."""
    invalid_response = """{
  "category": "cloud_infra",
  "severity": "super_urgent",
  "affected_service": "EC2",
  "customer_context": "Test",
  "suggested_tags": ["test"]
}"""
    
    mock_llm_router.complete.return_value = CompletionResult(
        content=invalid_response,
        model="claude-3-sonnet",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        provider="anthropic"
    )
    
    agent = TicketAgent(mock_llm_router)
    analysis = await agent.classify(sample_ticket)
    
    # Should default to "medium"
    assert analysis.severity == "medium"


@pytest.mark.asyncio
async def test_classify_handles_empty_tags(mock_llm_router, sample_ticket):
    """Test classification handles empty suggested_tags."""
    response_no_tags = """{
  "category": "general",
  "severity": "low",
  "affected_service": "unknown",
  "customer_context": "General inquiry",
  "suggested_tags": []
}"""
    
    mock_llm_router.complete.return_value = CompletionResult(
        content=response_no_tags,
        model="claude-3-sonnet",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        provider="anthropic"
    )
    
    agent = TicketAgent(mock_llm_router)
    analysis = await agent.classify(sample_ticket)
    
    # Should default to category as tag
    assert len(analysis.suggested_tags) > 0
    assert "general" in analysis.suggested_tags


@pytest.mark.asyncio
async def test_classify_handles_json_with_extra_text(mock_llm_router, sample_ticket):
    """Test classification handles JSON with extra text around it."""
    response_with_text = """Here's the classification:

{
  "category": "cloud_infra",
  "severity": "high",
  "affected_service": "EC2",
  "customer_context": "Test",
  "suggested_tags": ["ec2"]
}

This ticket requires immediate attention."""
    
    mock_llm_router.complete.return_value = CompletionResult(
        content=response_with_text,
        model="claude-3-sonnet",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        provider="anthropic"
    )
    
    agent = TicketAgent(mock_llm_router)
    analysis = await agent.classify(sample_ticket)
    
    assert analysis.category == "cloud_infra"
    assert analysis.severity == "high"


@pytest.mark.asyncio
async def test_classify_empty_subject_raises_error(mock_llm_router):
    """Test classification raises error for empty subject."""
    invalid_ticket = Ticket(
        id="ticket-invalid",
        subject="",
        body="Some body",
        customer_email="customer@example.com",
        status=TicketStatus.OPEN,
        tags=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        thread=[]
    )
    
    agent = TicketAgent(mock_llm_router)
    
    with pytest.raises(ValueError, match="non-empty subject and body"):
        await agent.classify(invalid_ticket)


@pytest.mark.asyncio
async def test_classify_empty_body_raises_error(mock_llm_router):
    """Test classification raises error for empty body."""
    invalid_ticket = Ticket(
        id="ticket-invalid",
        subject="Some subject",
        body="",
        customer_email="customer@example.com",
        status=TicketStatus.OPEN,
        tags=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        thread=[]
    )
    
    agent = TicketAgent(mock_llm_router)
    
    with pytest.raises(ValueError, match="non-empty subject and body"):
        await agent.classify(invalid_ticket)


@pytest.mark.asyncio
async def test_classify_llm_failure_raises_provider_error(mock_llm_router, sample_ticket):
    """Test classification raises ProviderError on LLM failure."""
    mock_llm_router.complete.side_effect = Exception("LLM API error")
    
    agent = TicketAgent(mock_llm_router)
    
    with pytest.raises(ProviderError, match="Ticket classification failed"):
        await agent.classify(sample_ticket)


@pytest.mark.asyncio
async def test_classify_invalid_json_raises_error(mock_llm_router, sample_ticket):
    """Test classification raises error for invalid JSON response."""
    mock_llm_router.complete.return_value = CompletionResult(
        content="This is not JSON at all",
        model="claude-3-sonnet",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        provider="anthropic"
    )
    
    agent = TicketAgent(mock_llm_router)
    
    with pytest.raises(ProviderError, match="Ticket classification failed"):
        await agent.classify(sample_ticket)


@pytest.mark.asyncio
async def test_classify_missing_required_field_raises_error(mock_llm_router, sample_ticket):
    """Test classification raises error for missing required fields."""
    incomplete_response = """{
  "category": "cloud_infra",
  "severity": "high"
}"""
    
    mock_llm_router.complete.return_value = CompletionResult(
        content=incomplete_response,
        model="claude-3-sonnet",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        provider="anthropic"
    )
    
    agent = TicketAgent(mock_llm_router)
    
    with pytest.raises(ProviderError, match="Ticket classification failed"):
        await agent.classify(sample_ticket)
