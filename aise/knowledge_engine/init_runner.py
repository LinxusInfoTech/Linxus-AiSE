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

import asyncio
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
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
    """Orchestrates the full crawl → extract → chunk → embed → store pipeline."""

    def __init__(self, config, vector_store, crawler=None, extractor=None, chunker=None, embedder=None):
        """Initialize init runner.

        Args:
            config: Configuration instance
            vector_store: Vector store instance
            crawler: Web crawler instance
            extractor: Content extractor instance
            chunker: Text chunker instance
            embedder: Embedding engine instance
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
        """Run the full pipeline for a single documentation source.

        Steps:
        1. Check if source was recently crawled (skip if fresh and not forced)
        2. Crawl all pages from the URL
        3. Fetch HTML and extract Markdown content for each page
        4. Chunk the Markdown into overlapping segments
        5. Generate embeddings for all chunks
        6. Upsert chunks into the vector store
        7. Record crawl metadata

        Args:
            source_name: Name of the documentation source
            url: Source URL to crawl
            force: If True, re-index regardless of age

        Returns:
            InitResult with indexing statistics
        """
        start_time = time.time()

        try:
            # Step 1: Check if source was recently crawled
            status = await self._vector_store.get_source_status(source_name)

            if status and not force:
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

            logger.info("pipeline_started", source_name=source_name, url=url)

            # Step 2: Crawl pages (returns (url, html) pairs)
            crawled_pages = await self._crawler.crawl_with_content(url)

            if not crawled_pages:
                duration = time.time() - start_time
                return InitResult(
                    source_name=source_name,
                    url=url,
                    chunks_indexed=0,
                    skipped=False,
                    skip_reason=None,
                    duration_seconds=duration,
                    error="No pages were crawled"
                )

            logger.info("crawl_done", source_name=source_name, pages=len(crawled_pages))

            # Step 3: Extract + chunk content from cached HTML (no re-fetch needed)
            all_chunks = []

            for page_url, html in crawled_pages:
                try:
                    if not html:
                        continue

                    # Step 3a: Extract Markdown
                    markdown = await self._extractor.extract_content(page_url, html)
                    if not markdown or not markdown.strip():
                        continue

                    # Step 3b: Chunk
                    chunks = self._chunker.chunk(
                        markdown,
                        source_url=page_url,
                        metadata={"source": source_name}
                    )
                    all_chunks.extend(chunks)

                except Exception as e:
                    logger.warning("page_processing_failed", url=page_url, error=str(e))

            if not all_chunks:
                duration = time.time() - start_time
                return InitResult(
                    source_name=source_name,
                    url=url,
                    chunks_indexed=0,
                    skipped=False,
                    skip_reason=None,
                    duration_seconds=duration,
                    error="No content chunks were created from crawled pages"
                )

            logger.info("chunking_done", source_name=source_name, chunks=len(all_chunks))

            # Step 4: Generate embeddings
            chunk_texts = [chunk.content for chunk in all_chunks]
            embeddings = await self._embedder.embed(chunk_texts)

            for chunk, embedding in zip(all_chunks, embeddings):
                chunk.embedding = embedding

            logger.info("embedding_done", source_name=source_name, embeddings=len(embeddings))

            # Step 5: Upsert into vector store
            await self._vector_store.upsert(all_chunks)

            # Step 6: Record crawl metadata
            embedding_model = getattr(self._embedder, 'model', None) or getattr(self._embedder, 'model_name', 'unknown')
            await self._vector_store.record_source_crawl(
                source_name=source_name,
                url=url,
                chunk_count=len(all_chunks),
                embedding_model=embedding_model
            )

            duration = time.time() - start_time
            logger.info(
                "pipeline_completed",
                source_name=source_name,
                pages_crawled=len(crawled_pages),
                chunks_indexed=len(all_chunks),
                duration_seconds=round(duration, 1)
            )

            return InitResult(
                source_name=source_name,
                url=url,
                chunks_indexed=len(all_chunks),
                skipped=False,
                skip_reason=None,
                duration_seconds=duration,
                error=None
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.error("init_source_failed", source_name=source_name, url=url, error=str(e))
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
