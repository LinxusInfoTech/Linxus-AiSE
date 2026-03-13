# aise/knowledge_engine/metadata_store.py
"""PostgreSQL storage for documentation metadata.

This module provides persistent storage for documentation crawl metadata
including source URLs, timestamps, chunk counts, and status tracking.

Example usage:
    >>> from aise.knowledge_engine.metadata_store import MetadataStore
    >>> from aise.core.config import get_config
    >>> 
    >>> config = get_config()
    >>> store = MetadataStore(config)
    >>> await store.initialize()
    >>> 
    >>> # Store crawl metadata
    >>> await store.store_crawl_metadata(
    ...     source_name="aws",
    ...     source_url="https://docs.aws.amazon.com/ec2/",
    ...     chunk_count=150,
    ...     total_tokens=50000,
    ...     status="completed"
    ... )
    >>> 
    >>> # Retrieve metadata
    >>> metadata = await store.get_source_metadata("aws")
"""

import asyncpg
from typing import Optional, List, Dict, Any
from datetime import datetime
import structlog

from aise.core.exceptions import KnowledgeEngineError, ConfigurationError

logger = structlog.get_logger(__name__)


class MetadataStore:
    """PostgreSQL storage for documentation metadata.
    
    Manages persistent storage of crawl metadata including source information,
    timestamps, chunk counts, and status tracking.
    
    Attributes:
        _config: Configuration instance
        _pool: asyncpg connection pool
    
    Example:
        >>> store = MetadataStore(config)
        >>> await store.initialize()
        >>> await store.store_crawl_metadata("aws", "https://...", 150)
    """
    
    def __init__(self, config):
        """Initialize metadata store.
        
        Args:
            config: Configuration instance with database settings
        """
        self._config = config
        self._pool: Optional[asyncpg.Pool] = None
    
    async def initialize(self) -> None:
        """Initialize database connection pool.
        
        Raises:
            ConfigurationError: If database connection fails
        """
        database_url = getattr(self._config, 'DATABASE_URL', None) or getattr(self._config, 'POSTGRES_URL', None)
        
        if not database_url:
            raise ConfigurationError(
                "DATABASE_URL or POSTGRES_URL not configured",
                field="DATABASE_URL"
            )
        
        try:
            self._pool = await asyncpg.create_pool(
                database_url,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            
            logger.info("metadata_store_initialized")
            
        except Exception as e:
            logger.error(
                "metadata_store_initialization_failed",
                error=str(e)
            )
            raise ConfigurationError(
                f"Failed to initialize metadata store: {str(e)}",
                field="DATABASE_URL"
            )
    
    async def store_crawl_metadata(
        self,
        source_name: str,
        source_url: str,
        chunk_count: int,
        total_tokens: Optional[int] = None,
        status: str = "completed",
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Store documentation crawl metadata.
        
        Args:
            source_name: Name of documentation source (e.g., "aws", "kubernetes")
            source_url: Base URL of documentation
            chunk_count: Number of chunks created
            total_tokens: Total tokens in all chunks (optional)
            status: Crawl status (completed, in_progress, error)
            error_message: Error message if status is error
            metadata: Additional metadata as JSON
        
        Returns:
            ID of inserted metadata record
        
        Raises:
            KnowledgeEngineError: If storage fails
        """
        if not self._pool:
            raise KnowledgeEngineError(
                "Metadata store not initialized",
                operation="store_crawl_metadata"
            )
        
        try:
            async with self._pool.acquire() as conn:
                record_id = await conn.fetchval("""
                    INSERT INTO documentation_metadata 
                        (source_name, source_url, crawl_timestamp, chunk_count, 
                         total_tokens, status, error_message, metadata)
                    VALUES ($1, $2, NOW(), $3, $4, $5, $6, $7)
                    RETURNING id
                """, source_name, source_url, chunk_count, total_tokens, 
                    status, error_message, metadata)
            
            logger.info(
                "crawl_metadata_stored",
                source_name=source_name,
                chunk_count=chunk_count,
                status=status,
                record_id=record_id
            )
            
            return record_id
            
        except Exception as e:
            logger.error(
                "crawl_metadata_storage_failed",
                error=str(e),
                source_name=source_name
            )
            raise KnowledgeEngineError(
                f"Failed to store crawl metadata: {str(e)}",
                operation="store_crawl_metadata"
            )

    
    async def get_source_metadata(
        self,
        source_name: str,
        latest_only: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Retrieve metadata for a documentation source.
        
        Args:
            source_name: Name of documentation source
            latest_only: If True, return only the most recent crawl
        
        Returns:
            Metadata dictionary or None if not found
        
        Raises:
            KnowledgeEngineError: If retrieval fails
        """
        if not self._pool:
            raise KnowledgeEngineError(
                "Metadata store not initialized",
                operation="get_source_metadata"
            )
        
        try:
            async with self._pool.acquire() as conn:
                if latest_only:
                    row = await conn.fetchrow("""
                        SELECT id, source_name, source_url, crawl_timestamp,
                               chunk_count, total_tokens, status, error_message, metadata
                        FROM documentation_metadata
                        WHERE source_name = $1
                        ORDER BY crawl_timestamp DESC
                        LIMIT 1
                    """, source_name)
                    
                    if row:
                        return dict(row)
                    return None
                else:
                    rows = await conn.fetch("""
                        SELECT id, source_name, source_url, crawl_timestamp,
                               chunk_count, total_tokens, status, error_message, metadata
                        FROM documentation_metadata
                        WHERE source_name = $1
                        ORDER BY crawl_timestamp DESC
                    """, source_name)
                    
                    return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(
                "source_metadata_retrieval_failed",
                error=str(e),
                source_name=source_name
            )
            raise KnowledgeEngineError(
                f"Failed to retrieve source metadata: {str(e)}",
                operation="get_source_metadata"
            )
    
    async def list_all_sources(self) -> List[Dict[str, Any]]:
        """List all documentation sources with their latest metadata.
        
        Returns:
            List of metadata dictionaries for all sources
        
        Raises:
            KnowledgeEngineError: If retrieval fails
        """
        if not self._pool:
            raise KnowledgeEngineError(
                "Metadata store not initialized",
                operation="list_all_sources"
            )
        
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT DISTINCT ON (source_name)
                        id, source_name, source_url, crawl_timestamp,
                        chunk_count, total_tokens, status, error_message, metadata
                    FROM documentation_metadata
                    ORDER BY source_name, crawl_timestamp DESC
                """)
            
            sources = [dict(row) for row in rows]
            
            logger.info(
                "sources_listed",
                count=len(sources)
            )
            
            return sources
            
        except Exception as e:
            logger.error(
                "source_listing_failed",
                error=str(e)
            )
            raise KnowledgeEngineError(
                f"Failed to list sources: {str(e)}",
                operation="list_all_sources"
            )
    
    async def update_crawl_status(
        self,
        record_id: int,
        status: str,
        chunk_count: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Update crawl status for a metadata record.
        
        Args:
            record_id: ID of metadata record to update
            status: New status (in_progress, completed, error)
            chunk_count: Updated chunk count (optional)
            error_message: Error message if status is error
        
        Raises:
            KnowledgeEngineError: If update fails
        """
        if not self._pool:
            raise KnowledgeEngineError(
                "Metadata store not initialized",
                operation="update_crawl_status"
            )
        
        try:
            async with self._pool.acquire() as conn:
                if chunk_count is not None:
                    await conn.execute("""
                        UPDATE documentation_metadata
                        SET status = $1, chunk_count = $2, error_message = $3
                        WHERE id = $4
                    """, status, chunk_count, error_message, record_id)
                else:
                    await conn.execute("""
                        UPDATE documentation_metadata
                        SET status = $1, error_message = $2
                        WHERE id = $3
                    """, status, error_message, record_id)
            
            logger.info(
                "crawl_status_updated",
                record_id=record_id,
                status=status
            )
            
        except Exception as e:
            logger.error(
                "status_update_failed",
                error=str(e),
                record_id=record_id
            )
            raise KnowledgeEngineError(
                f"Failed to update crawl status: {str(e)}",
                operation="update_crawl_status"
            )
    
    async def delete_source_metadata(self, source_name: str) -> int:
        """Delete all metadata for a documentation source.
        
        Args:
            source_name: Name of documentation source to delete
        
        Returns:
            Number of records deleted
        
        Raises:
            KnowledgeEngineError: If deletion fails
        """
        if not self._pool:
            raise KnowledgeEngineError(
                "Metadata store not initialized",
                operation="delete_source_metadata"
            )
        
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute("""
                    DELETE FROM documentation_metadata
                    WHERE source_name = $1
                """, source_name)
            
            # Extract count from result string "DELETE N"
            count = int(result.split()[-1]) if result else 0
            
            logger.info(
                "source_metadata_deleted",
                source_name=source_name,
                count=count
            )
            
            return count
            
        except Exception as e:
            logger.error(
                "metadata_deletion_failed",
                error=str(e),
                source_name=source_name
            )
            raise KnowledgeEngineError(
                f"Failed to delete source metadata: {str(e)}",
                operation="delete_source_metadata"
            )
    
    async def verify_data_integrity(self) -> Dict[str, Any]:
        """Verify data integrity on startup.
        
        Checks for orphaned metadata, inconsistent states, etc.
        
        Returns:
            Dictionary with integrity check results
        """
        if not self._pool:
            raise KnowledgeEngineError(
                "Metadata store not initialized",
                operation="verify_data_integrity"
            )
        
        try:
            async with self._pool.acquire() as conn:
                # Count total records
                total_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM documentation_metadata
                """)
                
                # Count by status
                status_counts = await conn.fetch("""
                    SELECT status, COUNT(*) as count
                    FROM documentation_metadata
                    GROUP BY status
                """)
                
                # Find stale in_progress records (older than 24 hours)
                stale_count = await conn.fetchval("""
                    SELECT COUNT(*)
                    FROM documentation_metadata
                    WHERE status = 'in_progress'
                    AND crawl_timestamp < NOW() - INTERVAL '24 hours'
                """)
            
            results = {
                "total_records": total_count,
                "status_breakdown": {row['status']: row['count'] for row in status_counts},
                "stale_in_progress": stale_count,
                "healthy": stale_count == 0
            }
            
            logger.info(
                "data_integrity_verified",
                **results
            )
            
            return results
            
        except Exception as e:
            logger.error(
                "integrity_verification_failed",
                error=str(e)
            )
            return {
                "error": str(e),
                "healthy": False
            }
    
    async def close(self) -> None:
        """Close database connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("metadata_store_closed")
            self._pool = None
    
    async def record_crawl(
        self,
        source_name: str,
        url: str,
        pages_crawled: int,
        chunks_created: int,
        embedding_model: str
    ) -> int:
        """Convenience method to record a completed crawl.
        
        Args:
            source_name: Name of documentation source
            url: Source URL
            pages_crawled: Number of pages crawled
            chunks_created: Number of chunks created
            embedding_model: Name of embedding model used
        
        Returns:
            ID of inserted metadata record
        """
        # Estimate tokens (rough approximation: 1 token ≈ 0.75 words)
        # We don't have the actual chunks here, so we'll set it to None
        # and let the caller calculate if needed
        
        metadata = {
            "pages_crawled": pages_crawled,
            "embedding_model": embedding_model
        }
        
        return await self.store_crawl_metadata(
            source_name=source_name,
            source_url=url,
            chunk_count=chunks_created,
            total_tokens=None,
            status="completed",
            metadata=metadata
        )
