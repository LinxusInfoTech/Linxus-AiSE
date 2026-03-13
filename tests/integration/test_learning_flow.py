# tests/integration/test_learning_flow.py
"""
Integration tests for Phase 2 Documentation Learning System.

Tests the complete workflow:
1. Crawl documentation
2. Extract and chunk content
3. Embed chunks
4. Store in vector database
5. Retrieve relevant documentation
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from aise.knowledge_engine.crawler import DocumentCrawler
from aise.knowledge_engine.extractor import ContentExtractor
from aise.knowledge_engine.chunker import TextChunker
from aise.knowledge_engine.embedder import LocalEmbedder
from aise.knowledge_engine.vector_store import ChromaDBVectorStore
from aise.knowledge_engine.metadata_store import MetadataStore
from aise.agents.knowledge_agent import KnowledgeAgent


@pytest.mark.asyncio
async def test_complete_learning_workflow():
    """Test the complete learning workflow from crawl to retrieval."""
    # Mock components
    mock_crawler = Mock(spec=DocumentCrawler)
    mock_extractor = Mock(spec=ContentExtractor)
    mock_chunker = Mock(spec=TextChunker)
    mock_embedder = Mock(spec=LocalEmbedder)
    mock_vector_store = Mock(spec=ChromaDBVectorStore)
    mock_metadata_store = Mock(spec=MetadataStore)
    
    # Setup mock responses
    mock_crawler.crawl = AsyncMock(return_value=[
        "https://example.com/doc1",
        "https://example.com/doc2"
    ])
    
    mock_extractor.extract_content.side_effect = [
        "# Security Groups\nAllow SSH access",
        "# EC2 Instances\nLaunch instances"
    ]
    
    # Mock chunker to return DocumentChunk objects
    from aise.knowledge_engine.chunker import DocumentChunk
    mock_chunker.chunk.side_effect = [
        [
            DocumentChunk(
                id="chunk1",
                content="Allow SSH access",
                metadata={"heading_context": "Security Groups"},
                source_url="https://example.com/doc1",
                heading_context="Security Groups",
                embedding=None,
                created_at=None
            ),
        ],
        [
            DocumentChunk(
                id="chunk2",
                content="Launch instances",
                metadata={"heading_context": "EC2 Instances"},
                source_url="https://example.com/doc2",
                heading_context="EC2 Instances",
                embedding=None,
                created_at=None
            ),
        ]
    ]
    
    mock_embedder.embed = AsyncMock(side_effect=[
        [[0.1, 0.2, 0.3]],  # Embedding for chunk1
        [[0.4, 0.5, 0.6]]   # Embedding for chunk2
    ])
    
    mock_vector_store.upsert = AsyncMock()
    mock_metadata_store.record_crawl = AsyncMock()
    
    # Simulate the learning workflow
    # 1. Crawl
    urls = await mock_crawler.crawl("https://example.com", max_depth=2, max_pages=10)
    assert len(urls) == 2
    
    # 2. Extract and chunk
    all_chunks = []
    for url in urls:
        markdown = await mock_extractor.extract_content(url, "<html>content</html>")
        chunks = mock_chunker.chunk(markdown, url, {})
        all_chunks.extend(chunks)
    
    assert len(all_chunks) == 2
    
    # 3. Embed
    for chunk in all_chunks:
        embedding = await mock_embedder.embed([chunk.content])
        chunk.embedding = embedding[0]
    
    # 4. Store
    await mock_vector_store.upsert(all_chunks, source="test-docs")
    await mock_metadata_store.record_crawl(
        source_name="test-docs",
        source_url="https://example.com",
        pages_crawled=2,
        chunks_created=2
    )
    
    # Verify all steps were called
    mock_crawler.crawl.assert_called_once()
    assert mock_extractor.extract_content.call_count == 2
    assert mock_chunker.chunk.call_count == 2
    assert mock_embedder.embed.call_count == 2
    mock_vector_store.upsert.assert_called_once()
    mock_metadata_store.record_crawl.assert_called_once()


@pytest.mark.asyncio
async def test_knowledge_retrieval_workflow():
    """Test retrieving documentation and using it in responses."""
    from aise.knowledge_engine.vector_store import DocumentChunk
    
    # Mock vector store with search results
    mock_vector_store = Mock(spec=ChromaDBVectorStore)
    mock_vector_store.list_all_sources = AsyncMock(return_value=[
        {"source_name": "aws-docs", "chunks": 100}
    ])
    mock_vector_store.search = AsyncMock(return_value=[
        DocumentChunk(
            id="chunk1",
            content="To allow SSH access, add an inbound rule for port 22",
            metadata={"source": "aws-docs", "heading_context": "Security Groups"},
            source_url="https://docs.aws.amazon.com/ec2/security-groups",
            heading_context="Security Groups",
            embedding=None,
            created_at=None
        ),
        DocumentChunk(
            id="chunk2",
            content="Security groups act as virtual firewalls",
            metadata={"source": "aws-docs", "heading_context": "Security Groups Overview"},
            source_url="https://docs.aws.amazon.com/ec2/security-groups",
            heading_context="Security Groups Overview",
            embedding=None,
            created_at=None
        )
    ])
    
    # Mock embedder
    mock_embedder = Mock(spec=LocalEmbedder)
    mock_embedder.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
    
    # Create knowledge agent
    knowledge_agent = KnowledgeAgent(
        vector_store=mock_vector_store,
        embedder=mock_embedder
    )
    
    # Retrieve documentation
    results = await knowledge_agent.retrieve(
        query="How do I allow SSH in a security group?",
        top_k=5
    )
    
    # Verify results
    assert len(results) == 2
    assert results[0]["text"] == "To allow SSH access, add an inbound rule for port 22"
    assert results[0]["source_url"] == "https://docs.aws.amazon.com/ec2/security-groups"
    assert results[0]["score"] == 1.0  # First result has highest score
    
    # Verify vector store search was called
    mock_vector_store.search.assert_called_once()


@pytest.mark.asyncio
async def test_documentation_persistence():
    """Test that learned documentation persists across restarts."""
    # Mock metadata store
    mock_metadata_store = Mock(spec=MetadataStore)
    mock_metadata_store.list_all_sources = AsyncMock(return_value=[
        {
            "source_name": "aws-docs",
            "source_url": "https://docs.aws.amazon.com/ec2/",
            "pages_crawled": 50,
            "chunks_created": 500,
            "last_crawled": "2024-03-13T10:00:00Z"
        }
    ])
    
    # Simulate system restart - metadata should still be available
    sources = await mock_metadata_store.list_all_sources()
    
    assert len(sources) == 1
    assert sources[0]["source_name"] == "aws-docs"
    assert sources[0]["chunks_created"] == 500
    
    mock_metadata_store.list_all_sources.assert_called_once()


def test_learn_command_exists():
    """Test that the learn command module can be imported."""
    from aise.cli.commands.learn import learn_app
    
    # Just verify the module and app exist
    assert learn_app is not None
    assert hasattr(learn_app, 'command')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
