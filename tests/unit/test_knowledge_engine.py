# tests/unit/test_knowledge_engine.py
"""Unit tests for knowledge engine components."""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from aise.knowledge_engine.embedder import Embedder, OpenAIEmbedder, LocalEmbedder
from aise.core.exceptions import KnowledgeEngineError


# Test Abstract Base Class
class TestEmbedder:
    """Tests for abstract Embedder base class."""
    
    def test_embedder_is_abstract(self):
        """Test that Embedder cannot be instantiated directly."""
        with pytest.raises(TypeError):
            Embedder()
    
    def test_embedder_requires_embed_method(self):
        """Test that subclasses must implement embed method."""
        class IncompleteEmbedder(Embedder):
            pass
        
        with pytest.raises(TypeError):
            IncompleteEmbedder()


# Test OpenAI Embedder
class TestOpenAIEmbedder:
    """Tests for OpenAI embeddings provider."""
    
    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        with patch('openai.AsyncOpenAI'):
            embedder = OpenAIEmbedder(api_key="test-key")
            
            assert embedder.api_key == "test-key"
            assert embedder.model == "text-embedding-3-small"
            assert embedder.batch_size == 100
    
    def test_init_with_custom_params(self):
        """Test initialization with custom parameters."""
        with patch('openai.AsyncOpenAI'):
            embedder = OpenAIEmbedder(
                api_key="test-key",
                model="text-embedding-ada-002",
                batch_size=50
            )
            
            assert embedder.model == "text-embedding-ada-002"
            assert embedder.batch_size == 50
    
    @pytest.mark.asyncio
    async def test_embed_empty_list(self):
        """Test embedding empty list returns empty list."""
        with patch('openai.AsyncOpenAI'):
            embedder = OpenAIEmbedder(api_key="test-key")
            result = await embedder.embed([])
            
            assert result == []
    
    @pytest.mark.asyncio
    async def test_embed_single_text(self):
        """Test embedding a single text."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            # Mock response
            mock_response = Mock()
            mock_response.data = [
                Mock(embedding=[0.1, 0.2, 0.3])
            ]
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            embedder = OpenAIEmbedder(api_key="test-key")
            result = await embedder.embed(["Hello world"])
            
            assert len(result) == 1
            assert result[0] == [0.1, 0.2, 0.3]
            mock_client.embeddings.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_embed_multiple_texts(self):
        """Test embedding multiple texts."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            # Mock response
            mock_response = Mock()
            mock_response.data = [
                Mock(embedding=[0.1, 0.2, 0.3]),
                Mock(embedding=[0.4, 0.5, 0.6]),
                Mock(embedding=[0.7, 0.8, 0.9])
            ]
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client
            
            embedder = OpenAIEmbedder(api_key="test-key")
            result = await embedder.embed(["Text 1", "Text 2", "Text 3"])
            
            assert len(result) == 3
            assert result[0] == [0.1, 0.2, 0.3]
            assert result[1] == [0.4, 0.5, 0.6]
            assert result[2] == [0.7, 0.8, 0.9]
    
    @pytest.mark.asyncio
    async def test_embed_batching(self):
        """Test that large lists are batched correctly."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            # Mock responses for each batch
            mock_response_1 = Mock()
            mock_response_1.data = [
                Mock(embedding=[0.1, 0.2]),
                Mock(embedding=[0.3, 0.4])
            ]
            
            mock_response_2 = Mock()
            mock_response_2.data = [
                Mock(embedding=[0.5, 0.6])
            ]
            
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(
                side_effect=[mock_response_1, mock_response_2]
            )
            mock_client_class.return_value = mock_client
            
            # Create embedder with small batch size
            embedder = OpenAIEmbedder(api_key="test-key", batch_size=2)
            
            # Embed 3 texts (should create 2 batches)
            result = await embedder.embed(["Text 1", "Text 2", "Text 3"])
            
            assert len(result) == 3
            assert mock_client.embeddings.create.call_count == 2
    
    @pytest.mark.asyncio
    async def test_embed_api_error(self):
        """Test handling of API errors."""
        with patch('openai.AsyncOpenAI') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.embeddings.create = AsyncMock(
                side_effect=Exception("API Error")
            )
            mock_client_class.return_value = mock_client
            
            embedder = OpenAIEmbedder(api_key="test-key")
            
            with pytest.raises(KnowledgeEngineError) as exc_info:
                await embedder.embed(["Test text"])
            
            assert "Failed to generate OpenAI embeddings" in str(exc_info.value)


# Test Local Embedder
class TestLocalEmbedder:
    """Tests for local sentence-transformers embeddings provider."""
    
    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        embedder = LocalEmbedder()
        
        assert embedder.model_name == "all-MiniLM-L6-v2"
        assert embedder.batch_size == 100
        assert embedder.device is None
        assert embedder._model is None
    
    def test_init_with_custom_params(self):
        """Test initialization with custom parameters."""
        embedder = LocalEmbedder(
            model_name="custom-model",
            batch_size=50,
            device="cuda"
        )
        
        assert embedder.model_name == "custom-model"
        assert embedder.batch_size == 50
        assert embedder.device == "cuda"
    
    @pytest.mark.asyncio
    async def test_embed_empty_list(self):
        """Test embedding empty list returns empty list."""
        embedder = LocalEmbedder()
        result = await embedder.embed([])
        
        assert result == []
    
    @pytest.mark.asyncio
    async def test_embed_lazy_loads_model(self):
        """Test that model is lazy loaded on first embed call."""
        import numpy as np
        
        with patch('sentence_transformers.SentenceTransformer') as mock_st_class:
            mock_model = Mock()
            mock_model.get_sentence_embedding_dimension = Mock(return_value=384)
            mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3]])
            mock_st_class.return_value = mock_model
            
            embedder = LocalEmbedder()
            assert embedder._model is None
            
            await embedder.embed(["Test text"])
            
            assert embedder._model is not None
            mock_st_class.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_embed_single_text(self):
        """Test embedding a single text."""
        import numpy as np
        
        with patch('sentence_transformers.SentenceTransformer') as mock_st_class:
            mock_model = Mock()
            mock_model.get_sentence_embedding_dimension = Mock(return_value=384)
            mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3]])
            mock_st_class.return_value = mock_model
            
            embedder = LocalEmbedder()
            result = await embedder.embed(["Hello world"])
            
            assert len(result) == 1
            assert result[0] == [0.1, 0.2, 0.3]
    
    @pytest.mark.asyncio
    async def test_embed_multiple_texts(self):
        """Test embedding multiple texts."""
        import numpy as np
        
        with patch('sentence_transformers.SentenceTransformer') as mock_st_class:
            mock_model = Mock()
            mock_model.get_sentence_embedding_dimension = Mock(return_value=384)
            mock_model.encode.return_value = np.array([
                [0.1, 0.2, 0.3],
                [0.4, 0.5, 0.6],
                [0.7, 0.8, 0.9]
            ])
            mock_st_class.return_value = mock_model
            
            embedder = LocalEmbedder()
            result = await embedder.embed(["Text 1", "Text 2", "Text 3"])
            
            assert len(result) == 3
            assert result[0] == [0.1, 0.2, 0.3]
            assert result[1] == [0.4, 0.5, 0.6]
            assert result[2] == [0.7, 0.8, 0.9]
    
    @pytest.mark.asyncio
    async def test_embed_batching(self):
        """Test that large lists are batched correctly."""
        import numpy as np
        
        with patch('sentence_transformers.SentenceTransformer') as mock_st_class:
            mock_model = Mock()
            mock_model.get_sentence_embedding_dimension = Mock(return_value=384)
            mock_model.encode.side_effect = [
                np.array([[0.1, 0.2], [0.3, 0.4]]),
                np.array([[0.5, 0.6]])
            ]
            mock_st_class.return_value = mock_model
            
            # Create embedder with small batch size
            embedder = LocalEmbedder(batch_size=2)
            
            # Embed 3 texts (should create 2 batches)
            result = await embedder.embed(["Text 1", "Text 2", "Text 3"])
            
            assert len(result) == 3
            assert mock_model.encode.call_count == 2
    
    @pytest.mark.asyncio
    async def test_embed_encoding_error(self):
        """Test handling of encoding errors."""
        with patch('sentence_transformers.SentenceTransformer') as mock_st_class:
            mock_model = Mock()
            mock_model.get_sentence_embedding_dimension = Mock(return_value=384)
            mock_model.encode.side_effect = Exception("Encoding Error")
            mock_st_class.return_value = mock_model
            
            embedder = LocalEmbedder()
            
            with pytest.raises(KnowledgeEngineError) as exc_info:
                await embedder.embed(["Test text"])
            
            assert "Failed to generate local embeddings" in str(exc_info.value)
