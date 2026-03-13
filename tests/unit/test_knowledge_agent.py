# tests/unit/test_knowledge_agent.py
"""Unit tests for Knowledge Agent."""

import pytest
from unittest.mock import Mock, AsyncMock
from aise.agents.knowledge_agent import KnowledgeAgent
from aise.knowledge_engine.vector_store import DocumentChunk


class TestKnowledgeAgent:
    """Tests for Knowledge Agent retrieval functionality."""
    
    @pytest.mark.asyncio
    async def test_retrieve_empty_index(self):
        """Test retrieval when index is empty."""
        mock_vector_store = AsyncMock()
        mock_vector_store.list_all_sources = AsyncMock(return_value=[])
        mock_embedder = AsyncMock()
        
        agent = KnowledgeAgent(mock_vector_store, mock_embedder)
        results = await agent.retrieve("test query")
        
        assert results == []
        mock_vector_store.list_all_sources.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_retrieve_with_results(self):
        """Test retrieval with results from vector store."""
        # Mock vector store
        mock_vector_store = AsyncMock()
        mock_vector_store.list_all_sources = AsyncMock(return_value=[
            {"source_name": "aws", "url": "https://docs.aws.amazon.com"}
        ])
        
        # Mock search results
        mock_chunks = [
            DocumentChunk(
                id="chunk1",
                content="AWS EC2 is a compute service",
                metadata={"source": "aws", "section": "EC2"},
                source_url="https://docs.aws.amazon.com/ec2/",
                heading_context="EC2 > Getting Started"
            ),
            DocumentChunk(
                id="chunk2",
                content="Launch an EC2 instance",
                metadata={"source": "aws", "section": "EC2"},
                source_url="https://docs.aws.amazon.com/ec2/launch",
                heading_context="EC2 > Launching Instances"
            )
        ]
        mock_vector_store.search = AsyncMock(return_value=mock_chunks)
        
        mock_embedder = AsyncMock()
        
        agent = KnowledgeAgent(mock_vector_store, mock_embedder)
        results = await agent.retrieve("How to launch EC2?", top_k=5)
        
        assert len(results) == 2
        assert results[0]["text"] == "AWS EC2 is a compute service"
        assert results[0]["source_url"] == "https://docs.aws.amazon.com/ec2/"
        assert results[0]["source_name"] == "aws"
        assert results[0]["heading_context"] == "EC2 > Getting Started"
        assert "score" in results[0]
        
        mock_vector_store.search.assert_called_once_with(
            query="How to launch EC2?",
            top_k=5,
            filter=None
        )
    
    @pytest.mark.asyncio
    async def test_retrieve_with_source_filter(self):
        """Test retrieval with source filter."""
        mock_vector_store = AsyncMock()
        mock_vector_store.list_all_sources = AsyncMock(return_value=[
            {"source_name": "aws", "url": "https://docs.aws.amazon.com"}
        ])
        mock_vector_store.search = AsyncMock(return_value=[])
        
        mock_embedder = AsyncMock()
        
        agent = KnowledgeAgent(mock_vector_store, mock_embedder)
        await agent.retrieve("test query", source_filter="aws")
        
        mock_vector_store.search.assert_called_once_with(
            query="test query",
            top_k=5,
            filter={"source": "aws"}
        )
    
    @pytest.mark.asyncio
    async def test_retrieve_handles_errors_gracefully(self):
        """Test that errors are handled gracefully."""
        mock_vector_store = AsyncMock()
        mock_vector_store.list_all_sources = AsyncMock(
            side_effect=Exception("Database error")
        )
        mock_embedder = AsyncMock()
        
        agent = KnowledgeAgent(mock_vector_store, mock_embedder)
        results = await agent.retrieve("test query")
        
        # Should return empty list on error
        assert results == []
    
    @pytest.mark.asyncio
    async def test_retrieve_relevance_scores(self):
        """Test that relevance scores are calculated correctly."""
        mock_vector_store = AsyncMock()
        mock_vector_store.list_all_sources = AsyncMock(return_value=[
            {"source_name": "aws"}
        ])
        
        # Mock 3 chunks
        mock_chunks = [
            DocumentChunk(
                id=f"chunk{i}",
                content=f"Content {i}",
                metadata={"source": "aws"},
                source_url=f"https://example.com/{i}",
                heading_context=f"Section {i}"
            )
            for i in range(3)
        ]
        mock_vector_store.search = AsyncMock(return_value=mock_chunks)
        
        mock_embedder = AsyncMock()
        
        agent = KnowledgeAgent(mock_vector_store, mock_embedder)
        results = await agent.retrieve("test query", top_k=3)
        
        # First result should have highest score
        assert results[0]["score"] == 1.0
        assert results[1]["score"] > results[2]["score"]
        assert all(0 <= r["score"] <= 1.0 for r in results)
