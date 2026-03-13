# aise/knowledge_engine/manager.py
"""Knowledge engine manager coordinating vector store and metadata.

This module provides a high-level interface for managing documentation
knowledge, coordinating between ChromaDB vector storage and PostgreSQL
metadata storage.

Example usage:
    >>> from aise.knowledge_engine.manager import KnowledgeManager
    >>> from aise.core.config import get_config
    >>> 
    >>> config = get_config()
    >>> manager = KnowledgeManager(config)
    >>> await manager.initialize()
    >>> 
    >>> # Manager automatically loads previously learned documentation
    >>> stats = await manager.get_stats()
    >>> print(f"Loaded {stats['document_count']} documents")
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import structlog

from aise.knowledge_engine.vector_store import ChromaDBVectorStore, DocumentChunk
from aise.knowledge_engine.metadata_store import MetadataStore
from aise.core.exceptions import KnowledgeEngineError

logger = structlog.get_logger(__name__)


class KnowledgeManager:
    """High-level manager for documentation knowledge.
    
    Coordinates between vector store (ChromaDB) and metadata store (PostgreSQL)
    to provide a unified interface for knowledge management.
    
    Attributes:
        _config: Configuration instance
        _vector_store: ChromaDB vector store
        _metadata_store: PostgreSQL metadata store
    
    Example:
        >>> manager = KnowledgeManager(config)
        >>> await manager.initialize()
        >>> sources = await manager.list_sources()
    """
    
    def __init__(self, config):
        """Initialize knowledge manager.
        
        Args:
            config: Configuration instance
        """
        self._config = config
        self._vector_store = ChromaDBVectorStore(config)
        self._metadata_store = MetadataStore(config)
    
    async def initialize(self) -> None:
        """Initialize knowledge manager and reload previous knowledge.
        
        Connects to vector store and metadata store, verifies data integrity,
        and loads previously learned documentation.
        """
        try:
            # Initialize stores
            await self._vector_store.initialize()
            await self._metadata_store.initialize()
            
            # Verify data integrity
            integrity = await self._metadata_store.verify_data_integrity()
            
            if not integrity.get('healthy', False):
                logger.warning(
                    "knowledge_integrity_issues_detected",
                    stale_records=integrity.get('stale_in_progress', 0)
                )
            
            # Get statistics
            stats = await self.get_stats()
            
            logger.info(
                "knowledge_manager_initialized",
                document_count=stats['document_count'],
                source_count=stats['source_count'],
                integrity_healthy=integrity.get('healthy', False)
            )
            
        except Exception as e:
            logger.error(
                "knowledge_manager_initialization_failed",
                error=str(e)
            )
            raise KnowledgeEngineError(
                f"Failed to initialize knowledge manager: {str(e)}",
                operation="initialization"
            )

    
    async def get_stats(self) -> Dict[str, Any]:
        """Get knowledge statistics.
        
        Returns:
            Dictionary with document counts, source counts, and metadata
        """
        try:
            # Get vector store stats
            vector_stats = await self._vector_store.get_collection_stats()
            
            # Get metadata stats
            sources = await self._metadata_store.list_all_sources()
            
            return {
                "document_count": vector_stats.get('document_count', 0),
                "user_style_count": vector_stats.get('user_style_count', 0),
                "source_count": len(sources),
                "sources": sources,
                "initialized": vector_stats.get('initialized', False)
            }
            
        except Exception as e:
            logger.error(
                "stats_retrieval_failed",
                error=str(e)
            )
            return {
                "error": str(e),
                "initialized": False
            }
    
    async def list_sources(self) -> List[Dict[str, Any]]:
        """List all learned documentation sources with metadata.
        
        Returns:
            List of source metadata dictionaries with age information
        """
        sources = await self._metadata_store.list_all_sources()
        
        # Add age information
        now = datetime.utcnow()
        for source in sources:
            crawl_time = source.get('crawl_timestamp')
            if crawl_time:
                age = now - crawl_time
                source['age_days'] = age.days
                source['age_hours'] = age.total_seconds() / 3600
        
        return sources
    
    async def get_source_info(self, source_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific documentation source.
        
        Args:
            source_name: Name of documentation source
        
        Returns:
            Source metadata dictionary with age information, or None if not found
        """
        metadata = await self._metadata_store.get_source_metadata(source_name)
        
        if metadata:
            # Add age information
            crawl_time = metadata.get('crawl_timestamp')
            if crawl_time:
                age = datetime.utcnow() - crawl_time
                metadata['age_days'] = age.days
                metadata['age_hours'] = age.total_seconds() / 3600
        
        return metadata
    
    async def search_documents(
        self,
        query: str,
        top_k: int = 5,
        source_filter: Optional[str] = None
    ) -> List[DocumentChunk]:
        """Search for relevant documentation chunks.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            source_filter: Optional source name to filter by
        
        Returns:
            List of relevant DocumentChunk objects
        """
        filter_dict = None
        if source_filter:
            filter_dict = {"source": source_filter}
        
        return await self._vector_store.search(query, top_k, filter_dict)
    
    async def close(self) -> None:
        """Close knowledge manager and all stores."""
        await self._vector_store.close()
        await self._metadata_store.close()
        logger.info("knowledge_manager_closed")


# Global knowledge manager instance
_knowledge_manager: Optional[KnowledgeManager] = None


async def get_knowledge_manager() -> KnowledgeManager:
    """Get global knowledge manager instance.
    
    Returns:
        KnowledgeManager instance
    
    Raises:
        KnowledgeEngineError: If not initialized
    """
    global _knowledge_manager
    
    if _knowledge_manager is None:
        raise KnowledgeEngineError(
            "Knowledge manager not initialized. Call initialize_knowledge_manager() first.",
            operation="get_knowledge_manager"
        )
    
    return _knowledge_manager


async def initialize_knowledge_manager(config) -> KnowledgeManager:
    """Initialize global knowledge manager.
    
    Args:
        config: Configuration instance
    
    Returns:
        KnowledgeManager instance
    """
    global _knowledge_manager
    
    if _knowledge_manager is None:
        _knowledge_manager = KnowledgeManager(config)
        await _knowledge_manager.initialize()
    
    return _knowledge_manager


async def close_knowledge_manager() -> None:
    """Close global knowledge manager."""
    global _knowledge_manager
    
    if _knowledge_manager:
        await _knowledge_manager.close()
        _knowledge_manager = None
