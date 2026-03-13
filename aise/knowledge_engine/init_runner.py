# aise/knowledge_engine/init_runner.py
"""Orchestrator for the full crawl → extract → chunk → embed → store pipeline.

This module coordinates the documentation indexing process, managing the
workflow from crawling documentation URLs to storing embedded chunks in
the vector store.

Example usage:
    >>> from aise.knowledge_engine.init_runner import InitRunner
    >>> from aise.core.config import get_config
    >>> 
    >>> config = get_config()
    >>> runner = InitRunner(config, vector_store, crawler, extractor, chunker, embedder)
    >>> 
    >>> # Run for a single source
    >>> result = await runner.run_source("aws", "https://docs.aws.amazon.com/", force=False)
    >>> 
    >>> # Run for all registered sources
    >>> results = await runner.run_all(force=False)
"""

from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime, timedelta
import time
import structlog

from aise.knowledge_engine.sources import REGISTERED_SOURCES

logger = structlog.get_logger(__name__)


@dataclass
class InitResult:
    """Result of running init for a single source.
    
    Attributes:
        source_name: Name of the documentation source
        url: Source URL
        chunks_indexed: Number of chunks indexed
        skipped: True if already fresh and not forced
        skip_reason: Reason for skipping (if skipped)
        duration_seconds: Time taken to complete
        error: Error message (None if successful)
    """
    source_name: str
    url: str
    chunks_indexed: int
    skipped: bool
    skip_reason: Optional[str]
    duration_seconds: float
    error: Optional[str]


class InitRunner:
    """Orchestrates the full crawl → extract → chunk → embed → store pipeline.
    
    Coordinates between crawler, extractor, chunker, embedder, and vector store
    to index documentation sources.
    """

    
    def __init__(self, config, vector_store, crawler=None, extractor=None, chunker=None, embedder=None):
        """Initialize init runner.
        
        Args:
            config: Configuration instance
            vector_store: Vector store instance
            crawler: Web crawler instance (optional, for future implementation)
            extractor: Content extractor instance (optional, for future implementation)
            chunker: Text chunker instance (optional, for future implementation)
            embedder: Embedding engine instance (optional, for future implementation)
        """
        self._config = config
        self._vector_store = vector_store
        self._crawler = crawler
        self._extractor = extractor
        self._chunker = chunker
        self._embedder = embedder
    
    async def run_source(
        self,
        source_name: str,
        url: str,
        force: bool = False
    ) -> InitResult:
        """Run init for a single source.
        
        Logic:
        1. Check vector_store.get_source_status(source_name)
        2. If crawled within KNOWLEDGE_MIN_REINIT_HOURS and not force:
           log "source already indexed, skipping" and return early
        3. If force or never crawled:
           a. crawler.crawl(url, max_depth=config.KNOWLEDGE_CRAWL_MAX_DEPTH)
           b. extractor.extract(pages)
           c. chunker.chunk(markdown_text, source_name=source_name, url=page_url)
           d. embedder.embed(chunks)
           e. vector_store.upsert(chunks)
           f. vector_store.record_source_crawl(source_name, url, chunk_count, model)
           g. return InitResult with stats
        
        Args:
            source_name: Name of the documentation source
            url: Source URL to crawl
            force: If True, re-index regardless of age
        
        Returns:
            InitResult with indexing statistics
        """
        start_time = time.time()
        
        try:
            # Check if source was recently crawled
            status = await self._vector_store.get_source_status(source_name)
            
            if status and not force:
                # Check if crawled recently
                crawled_at = datetime.fromisoformat(status['crawled_at'])
                age_hours = (datetime.utcnow() - crawled_at).total_seconds() / 3600
                min_hours = self._config.KNOWLEDGE_MIN_REINIT_HOURS
                
                if age_hours < min_hours:
                    duration = time.time() - start_time
                    logger.info(
                        "source_already_indexed",
                        source_name=source_name,
                        age_hours=round(age_hours, 1),
                        min_hours=min_hours
                    )
                    return InitResult(
                        source_name=source_name,
                        url=url,
                        chunks_indexed=status.get('chunk_count', 0),
                        skipped=True,
                        skip_reason=f"Already indexed {round(age_hours, 1)}h ago (min: {min_hours}h)",
                        duration_seconds=duration,
                        error=None
                    )
            
            # TODO: Implement actual crawling and indexing
            # This is a placeholder that will be implemented in Phase 2
            logger.warning(
                "crawling_not_implemented",
                source_name=source_name,
                url=url,
                message="Crawling pipeline not yet implemented. This will be available in Phase 2."
            )
            
            duration = time.time() - start_time
            return InitResult(
                source_name=source_name,
                url=url,
                chunks_indexed=0,
                skipped=False,
                skip_reason=None,
                duration_seconds=duration,
                error="Crawling not yet implemented (Phase 2)"
            )
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                "init_source_failed",
                source_name=source_name,
                url=url,
                error=str(e)
            )
            return InitResult(
                source_name=source_name,
                url=url,
                chunks_indexed=0,
                skipped=False,
                skip_reason=None,
                duration_seconds=duration,
                error=str(e)
            )
    
    async def run_all(self, force: bool = False) -> List[InitResult]:
        """Run run_source() for every entry in sources.REGISTERED_SOURCES.
        
        Args:
            force: If True, re-index all sources regardless of age
        
        Returns:
            List of InitResult objects for each source
        """
        results = []
        
        logger.info(
            "init_all_started",
            source_count=len(REGISTERED_SOURCES),
            force=force
        )
        
        for source in REGISTERED_SOURCES:
            result = await self.run_source(
                source_name=source["name"],
                url=source["url"],
                force=force
            )
            results.append(result)
        
        # Log summary
        successful = sum(1 for r in results if r.error is None and not r.skipped)
        skipped = sum(1 for r in results if r.skipped)
        failed = sum(1 for r in results if r.error is not None)
        total_chunks = sum(r.chunks_indexed for r in results)
        
        logger.info(
            "init_all_completed",
            total_sources=len(results),
            successful=successful,
            skipped=skipped,
            failed=failed,
            total_chunks=total_chunks
        )
        
        return results
