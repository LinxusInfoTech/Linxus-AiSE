# tests/unit/test_graph.py
"""Unit tests for AiSEGraph orchestration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from aise.agents.graph import AiSEGraph
from aise.agents.state import (
    AiSEState,
    create_initial_state,
    Ticket,
    TicketStatus,
    TicketAnalysis,
    DocumentChunk
)
from aise.agents.ticket_agent import TicketAgent
from aise.agents.knowledge_agent import KnowledgeAgent
from aise.agents.engineer_agent import EngineerAgent


@pytest.fixture
def mock_ticket_agent():
    """Create mock ticket agent."""
    agent = MagicMock(spec=TicketAgent)
    agent.classify = AsyncMock(return_value=TicketAnalysis(
        category="cloud_infra",
        severity="high",
        affected_service="EC2",
        suggested_tags=["ec2", "networking"],
        confidence=0.85
    ))
    return agent


@pytest.fixture
def mock_knowledge_agent():
    """Create mock knowledge agent."""
    agent = MagicMock(spec=KnowledgeAgent)
    agent.retrieve = AsyncMock(return_value=[
        {
            "id": "chunk1",
            "text": "EC2 security groups control inbound and outbound traffic",
            "source_url": "https://docs.aws.amazon.com/ec2/security-groups",
            "source_name": "aws",
            "heading_context": "EC2 > Security Groups",
            "score": 0.95
        }
    ])
    return agent


@pytest.fixture
def mock_engineer_agent():
    """Create mock engineer agent."""
    agent = MagicMock(spec=EngineerAgent)
    
    async def mock_diagnose(state):
        from aise.agents.state import update_state
        return update_state(
            state,
            diagnosis="The EC2 instance is unreachable due to security group misconfiguration.",
            actions_taken=state["actions_taken"] + ["Generated diagnosis"]
        )
    
    agent.diagnose = AsyncMock(side_effect=mock_diagnose)
    return agent


@pytest.fixture
def mock_ticket_provider():
    """Create mock ticket provider."""
    provider = MagicMock()
    provider.get = AsyncMock(return_value=Ticket(
        id="ticket-123",
        subject="EC2 instance unreachable",
        body="Cannot connect to i-1234567890",
        customer_email="user@example.com",
        status=TicketStatus.OPEN,
        tags=[],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        thread=[]
    ))
    provider.reply = AsyncMock()
    return provider


@pytest.fixture
def aise_graph(mock_ticket_agent, mock_knowledge_agent, mock_engineer_agent, mock_ticket_provider):
    """Create AiSEGraph with mocked dependencies."""
    return AiSEGraph(
        ticket_agent=mock_ticket_agent,
        knowledge_agent=mock_knowledge_agent,
        engineer_agent=mock_engineer_agent,
        ticket_provider=mock_ticket_provider
    )


@pytest.mark.asyncio
async def test_graph_initialization(aise_graph):
    """Test graph initializes correctly."""
    assert aise_graph._ticket_agent is not None
    assert aise_graph._knowledge_agent is not None
    assert aise_graph._engineer_agent is not None
    assert aise_graph._ticket_provider is not None
    assert aise_graph._graph is not None


@pytest.mark.asyncio
async def test_graph_interactive_mode_no_ticket(aise_graph, mock_engineer_agent):
    """Test graph execution in interactive mode without ticket."""
    # Create initial state
    state = create_initial_state(
        messages=[{"role": "user", "content": "Why is my EC2 instance unreachable?"}],
        mode="interactive"
    )
    
    # Execute graph
    final_state = await aise_graph.run(state)
    
    # Verify diagnosis was generated
    assert final_state["diagnosis"] is not None
    assert "EC2" in final_state["diagnosis"]
    
    # Verify engineer agent was called
    mock_engineer_agent.diagnose.assert_called()
    
    # Verify no pending approval
    assert final_state["pending_approval"] is None


@pytest.mark.asyncio
async def test_graph_with_ticket_classification(
    aise_graph,
    mock_ticket_agent,
    mock_ticket_provider
):
    """Test graph classifies ticket when ticket_id present."""
    # Create initial state with ticket
    state = create_initial_state(
        messages=[{"role": "user", "content": "EC2 issue"}],
        mode="autonomous",
        ticket_id="ticket-123"
    )
    
    # Execute graph
    final_state = await aise_graph.run(state)
    
    # Verify ticket was fetched
    mock_ticket_provider.get.assert_called_once_with("ticket-123")
    
    # Verify ticket was classified
    mock_ticket_agent.classify.assert_called_once()
    
    # Verify classification in state
    assert final_state["ticket_analysis"] is not None
    assert final_state["ticket_analysis"].category == "cloud_infra"
    assert final_state["ticket_analysis"].severity == "high"


@pytest.mark.asyncio
async def test_graph_knowledge_retrieval(aise_graph, mock_knowledge_agent):
    """Test graph retrieves knowledge when available."""
    # Create initial state
    state = create_initial_state(
        messages=[{"role": "user", "content": "Security group issue"}],
        mode="interactive"
    )
    
    # Execute graph
    final_state = await aise_graph.run(state)
    
    # Verify knowledge was retrieved
    mock_knowledge_agent.retrieve.assert_called_once()
    
    # Verify knowledge context in state
    assert len(final_state["knowledge_context"]) > 0
    assert final_state["knowledge_context"][0].content == "EC2 security groups control inbound and outbound traffic"


@pytest.mark.asyncio
async def test_graph_approval_mode_pauses(aise_graph):
    """Test graph pauses in approval mode before posting reply."""
    # Create initial state with ticket in approval mode
    state = create_initial_state(
        messages=[{"role": "user", "content": "EC2 issue"}],
        mode="approval",
        ticket_id="ticket-123"
    )
    
    # Execute graph
    final_state = await aise_graph.run(state)
    
    # Verify pending approval is set
    assert final_state["pending_approval"] is not None
    assert final_state["pending_approval"]["action"] == "post_reply"
    assert final_state["pending_approval"]["ticket_id"] == "ticket-123"
    assert "EC2" in final_state["pending_approval"]["message"]


@pytest.mark.asyncio
async def test_graph_autonomous_mode_posts_reply(
    aise_graph,
    mock_ticket_provider
):
    """Test graph posts reply automatically in autonomous mode."""
    # Create initial state with ticket in autonomous mode
    state = create_initial_state(
        messages=[{"role": "user", "content": "EC2 issue"}],
        mode="autonomous",
        ticket_id="ticket-123"
    )
    
    # Execute graph
    final_state = await aise_graph.run(state)
    
    # Verify reply was posted
    mock_ticket_provider.reply.assert_called_once()
    call_args = mock_ticket_provider.reply.call_args
    assert call_args[0][0] == "ticket-123"
    assert "EC2" in call_args[0][1]
    
    # Verify no pending approval
    assert final_state["pending_approval"] is None


@pytest.mark.asyncio
async def test_graph_state_immutability(aise_graph):
    """Test graph maintains state immutability."""
    import copy
    
    # Create initial state
    initial_state = create_initial_state(
        messages=[{"role": "user", "content": "Test"}],
        mode="interactive"
    )
    
    # Deep copy for comparison
    original_copy = copy.deepcopy(initial_state)
    
    # Execute graph
    final_state = await aise_graph.run(initial_state)
    
    # Verify original state unchanged
    assert initial_state["messages"] == original_copy["messages"]
    assert initial_state["actions_taken"] == original_copy["actions_taken"]
    
    # Verify final state is different
    assert final_state != initial_state
    assert len(final_state["actions_taken"]) > len(initial_state["actions_taken"])


@pytest.mark.asyncio
async def test_graph_without_knowledge_agent():
    """Test graph works without knowledge agent."""
    mock_ticket_agent = MagicMock(spec=TicketAgent)
    mock_engineer_agent = MagicMock(spec=EngineerAgent)
    
    async def mock_diagnose(state):
        from aise.agents.state import update_state
        return update_state(state, diagnosis="Test diagnosis")
    
    mock_engineer_agent.diagnose = AsyncMock(side_effect=mock_diagnose)
    
    # Create graph without knowledge agent
    graph = AiSEGraph(
        ticket_agent=mock_ticket_agent,
        knowledge_agent=None,
        engineer_agent=mock_engineer_agent,
        ticket_provider=None
    )
    
    # Create initial state
    state = create_initial_state(
        messages=[{"role": "user", "content": "Test"}],
        mode="interactive"
    )
    
    # Execute graph
    final_state = await graph.run(state)
    
    # Verify diagnosis generated without knowledge
    assert final_state["diagnosis"] == "Test diagnosis"
    assert len(final_state["knowledge_context"]) == 0


@pytest.mark.asyncio
async def test_graph_actions_taken_tracking(aise_graph):
    """Test graph tracks all actions taken."""
    # Create initial state with ticket
    state = create_initial_state(
        messages=[{"role": "user", "content": "EC2 issue"}],
        mode="autonomous",
        ticket_id="ticket-123"
    )
    
    # Execute graph
    final_state = await aise_graph.run(state)
    
    # Verify actions were tracked
    assert len(final_state["actions_taken"]) > 0
    assert "Classified ticket" in final_state["actions_taken"]
    assert "Retrieved documentation" in final_state["actions_taken"]
    assert "Generated diagnosis" in final_state["actions_taken"]


@pytest.mark.asyncio
async def test_graph_handles_classification_error(aise_graph, mock_ticket_agent):
    """Test graph continues when classification fails."""
    # Make classification fail
    mock_ticket_agent.classify.side_effect = Exception("Classification failed")
    
    # Create initial state with ticket
    state = create_initial_state(
        messages=[{"role": "user", "content": "EC2 issue"}],
        mode="autonomous",
        ticket_id="ticket-123"
    )
    
    # Execute graph - should not raise
    final_state = await aise_graph.run(state)
    
    # Verify diagnosis still generated
    assert final_state["diagnosis"] is not None
    
    # Verify no classification in state
    assert final_state["ticket_analysis"] is None


@pytest.mark.asyncio
async def test_graph_handles_knowledge_retrieval_error(
    aise_graph,
    mock_knowledge_agent
):
    """Test graph continues when knowledge retrieval fails."""
    # Make retrieval fail
    mock_knowledge_agent.retrieve.side_effect = Exception("Retrieval failed")
    
    # Create initial state
    state = create_initial_state(
        messages=[{"role": "user", "content": "Test"}],
        mode="interactive"
    )
    
    # Execute graph - should not raise
    final_state = await aise_graph.run(state)
    
    # Verify diagnosis still generated
    assert final_state["diagnosis"] is not None
    
    # Verify no knowledge context
    assert len(final_state["knowledge_context"]) == 0


@pytest.mark.asyncio
async def test_graph_updated_at_timestamp(aise_graph):
    """Test graph updates timestamp."""
    # Create initial state
    state = create_initial_state(
        messages=[{"role": "user", "content": "Test"}],
        mode="interactive"
    )
    
    initial_timestamp = state["updated_at"]
    
    # Execute graph
    final_state = await aise_graph.run(state)
    
    # Verify timestamp was updated
    assert final_state["updated_at"] != initial_timestamp
