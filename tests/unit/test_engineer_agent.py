# tests/unit/test_engineer_agent.py
"""Unit tests for Engineer Agent."""

import pytest
from unittest.mock import Mock, AsyncMock
from aise.agents.engineer_agent import EngineerAgent
from aise.agents.state import create_initial_state
from aise.knowledge_engine.chunker import DocumentChunk


class TestEngineerAgent:
    """Tests for Engineer Agent diagnosis functionality."""
    
    @pytest.mark.asyncio
    async def test_diagnose_without_knowledge_context(self):
        """Test diagnosis without knowledge context."""
        # Mock LLM router
        mock_router = AsyncMock()
        mock_result = Mock()
        mock_result.content = "This is a diagnosis"
        mock_result.usage = Mock(total_tokens=100, estimated_cost_usd=0.001)
        mock_router.complete = AsyncMock(return_value=mock_result)
        
        agent = EngineerAgent(mock_router)
        
        state = create_initial_state(
            messages=[{"role": "user", "content": "Why is my EC2 unreachable?"}]
        )
        
        result_state = await agent.diagnose(state)
        
        assert result_state["diagnosis"] == "This is a diagnosis"
        assert "Generated diagnosis" in result_state["actions_taken"]
        mock_router.complete.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_diagnose_with_knowledge_context(self):
        """Test diagnosis with knowledge context includes citations."""
        # Mock LLM router
        mock_router = AsyncMock()
        mock_result = Mock()
        mock_result.content = "Based on the documentation, configure security groups."
        mock_result.usage = Mock(total_tokens=150, estimated_cost_usd=0.002)
        mock_router.complete = AsyncMock(return_value=mock_result)
        
        agent = EngineerAgent(mock_router)
        
        # Create state with knowledge context
        state = create_initial_state(
            messages=[{"role": "user", "content": "How do I allow SSH?"}]
        )
        state["knowledge_context"] = [
            DocumentChunk(
                id="chunk1",
                content="To allow SSH, add inbound rule on port 22",
                metadata={"source": "aws"},
                source_url="https://docs.aws.amazon.com/ec2/security-groups",
                heading_context="EC2 > Security Groups"
            )
        ]
        
        result_state = await agent.diagnose(state)
        
        assert result_state["diagnosis"] == "Based on the documentation, configure security groups."
        
        # Verify knowledge context was included in prompt
        call_args = mock_router.complete.call_args
        messages = call_args.kwargs["messages"]
        
        # First message should contain documentation
        assert any("Relevant documentation" in msg.get("content", "") for msg in messages)
        assert any("https://docs.aws.amazon.com/ec2/security-groups" in msg.get("content", "") for msg in messages)
    
    @pytest.mark.asyncio
    async def test_format_knowledge_context(self):
        """Test knowledge context formatting with citations."""
        mock_router = AsyncMock()
        agent = EngineerAgent(mock_router)
        
        chunks = [
            DocumentChunk(
                id="chunk1",
                content="Content 1",
                metadata={"source": "aws"},
                source_url="https://example.com/1",
                heading_context="Section 1"
            ),
            DocumentChunk(
                id="chunk2",
                content="Content 2",
                metadata={"source": "aws"},
                source_url="https://example.com/2",
                heading_context="Section 2"
            )
        ]
        
        formatted = agent._format_knowledge_context(chunks)
        
        assert "[1] Section 1" in formatted
        assert "Source: https://example.com/1" in formatted
        assert "Content 1" in formatted
        assert "[2] Section 2" in formatted
        assert "Source: https://example.com/2" in formatted
        assert "Content 2" in formatted
    
    @pytest.mark.asyncio
    async def test_diagnose_limits_knowledge_chunks(self):
        """Test that only top 5 knowledge chunks are included."""
        mock_router = AsyncMock()
        mock_result = Mock()
        mock_result.content = "Diagnosis"
        mock_result.usage = Mock(total_tokens=100, estimated_cost_usd=0.001)
        mock_router.complete = AsyncMock(return_value=mock_result)
        
        agent = EngineerAgent(mock_router)
        
        # Create 10 chunks
        chunks = [
            DocumentChunk(
                id=f"chunk{i}",
                content=f"Content {i}",
                metadata={"source": "aws"},
                source_url=f"https://example.com/{i}",
                heading_context=f"Section {i}"
            )
            for i in range(10)
        ]
        
        state = create_initial_state(
            messages=[{"role": "user", "content": "Test"}]
        )
        state["knowledge_context"] = chunks
        
        await agent.diagnose(state)
        
        # Check that formatted context only includes 5 chunks
        call_args = mock_router.complete.call_args
        messages = call_args.kwargs["messages"]
        doc_message = next(msg for msg in messages if "Relevant documentation" in msg.get("content", ""))
        
        # Should have [1] through [5] but not [6]
        assert "[1]" in doc_message["content"]
        assert "[5]" in doc_message["content"]
        assert "[6]" not in doc_message["content"]
