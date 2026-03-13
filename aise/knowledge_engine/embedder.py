# aise/knowledge_engine/embedder.py
"""Embedding generation for documentation chunks.

This module provides embedding generation for documentation chunks using
various embedding providers (OpenAI, local sentence-transformers).

Example usage:
    >>> from aise.knowledge_engine.embedder import OpenAIEmbedder, LocalEmbedder
    >>> 
    >>> # Using OpenAI embeddings
    >>> embedder = OpenAIEmbedder(api_key="sk-...")
    >>> embeddings = await embedder.embed(["Hello world", "Another text"])
    >>> 
    >>> # Using local sentence-transformers
    >>> embedder = LocalEmbedder(model_name="all-MiniLM-L6-v2")
    >>> embeddings = await embedder.embed(["Hello world", "Another text"])
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import asyncio
import structlog

from aise.core.exceptions import KnowledgeEngineError

logger = structlog.get_logger(__name__)


class Embedder(ABC):
    """Abstract base class for embedding providers."""
    
    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
        
        Returns:
            List of embedding vectors (each vector is a list of floats)
        
        Raises:
            KnowledgeEngineError: If embedding generation fails
        """
        pass


class OpenAIEmbedder(Embedder):
    """OpenAI embeddings provider using text-embedding-3-small model."""
    
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        batch_size: int = 100
    ):
        """Initialize OpenAI embedder.
        
        Args:
            api_key: OpenAI API key
            model: Embedding model name (default: text-embedding-3-small)
            batch_size: Number of texts to embed in each batch (default: 100)
        """
        self.api_key = api_key
        self.model = model
        self.batch_size = batch_size
        
        # Lazy import to avoid requiring openai if not used
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=api_key)
        except ImportError:
            raise KnowledgeEngineError(
                "OpenAI package not installed. Install with: pip install openai",
                operation="initialization"
            )
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using OpenAI API.
        
        Args:
            texts: List of text strings to embed
        
        Returns:
            List of embedding vectors
        
        Raises:
            KnowledgeEngineError: If API call fails
        """
        if not texts:
            return []
        
        try:
            logger.debug(
                "openai_embedding_started",
                num_texts=len(texts),
                model=self.model,
                batch_size=self.batch_size
            )
            
            # Process in batches
            all_embeddings = []
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i:i + self.batch_size]
                
                logger.debug(
                    "openai_embedding_batch",
                    batch_num=i // self.batch_size + 1,
                    batch_size=len(batch)
                )
                
                # Call OpenAI API
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=batch
                )
                
                # Extract embeddings
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
            
            logger.info(
                "openai_embedding_complete",
                num_texts=len(texts),
                num_embeddings=len(all_embeddings),
                embedding_dim=len(all_embeddings[0]) if all_embeddings else 0
            )
            
            return all_embeddings
            
        except Exception as e:
            logger.error(
                "openai_embedding_failed",
                error=str(e),
                num_texts=len(texts)
            )
            raise KnowledgeEngineError(
                f"Failed to generate OpenAI embeddings: {str(e)}",
                operation="embed"
            )


class LocalEmbedder(Embedder):
    """Local embeddings provider using sentence-transformers."""
    
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        batch_size: int = 100,
        device: Optional[str] = None
    ):
        """Initialize local embedder.
        
        Args:
            model_name: Sentence-transformers model name (default: all-MiniLM-L6-v2)
            batch_size: Number of texts to embed in each batch (default: 100)
            device: Device to use for inference (cpu/cuda/mps, default: auto-detect)
        """
        self.model_name = model_name
        self.batch_size = batch_size
        self.device = device
        self._model = None
        
        # Lazy import to avoid requiring sentence-transformers if not used
        try:
            from sentence_transformers import SentenceTransformer
            self._SentenceTransformer = SentenceTransformer
        except ImportError:
            raise KnowledgeEngineError(
                "sentence-transformers package not installed. "
                "Install with: pip install sentence-transformers",
                operation="initialization"
            )
    
    def _load_model(self):
        """Lazy load the sentence-transformers model."""
        if self._model is None:
            logger.info(
                "loading_local_embedding_model",
                model_name=self.model_name,
                device=self.device or "auto"
            )
            
            self._model = self._SentenceTransformer(
                self.model_name,
                device=self.device
            )
            
            logger.info(
                "local_embedding_model_loaded",
                model_name=self.model_name,
                embedding_dim=self._model.get_sentence_embedding_dimension()
            )
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using local sentence-transformers model.
        
        Args:
            texts: List of text strings to embed
        
        Returns:
            List of embedding vectors
        
        Raises:
            KnowledgeEngineError: If embedding generation fails
        """
        if not texts:
            return []
        
        try:
            # Load model if not already loaded
            self._load_model()
            
            logger.debug(
                "local_embedding_started",
                num_texts=len(texts),
                model=self.model_name,
                batch_size=self.batch_size
            )
            
            # Process in batches
            all_embeddings = []
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i:i + self.batch_size]
                
                logger.debug(
                    "local_embedding_batch",
                    batch_num=i // self.batch_size + 1,
                    batch_size=len(batch)
                )
                
                # Run encoding in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                batch_embeddings = await loop.run_in_executor(
                    None,
                    lambda: self._model.encode(
                        batch,
                        convert_to_numpy=True,
                        show_progress_bar=False
                    )
                )
                
                # Convert numpy arrays to lists
                batch_embeddings_list = [
                    embedding.tolist() for embedding in batch_embeddings
                ]
                all_embeddings.extend(batch_embeddings_list)
            
            logger.info(
                "local_embedding_complete",
                num_texts=len(texts),
                num_embeddings=len(all_embeddings),
                embedding_dim=len(all_embeddings[0]) if all_embeddings else 0
            )
            
            return all_embeddings
            
        except Exception as e:
            logger.error(
                "local_embedding_failed",
                error=str(e),
                num_texts=len(texts)
            )
            raise KnowledgeEngineError(
                f"Failed to generate local embeddings: {str(e)}",
                operation="embed"
            )
