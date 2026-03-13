# aise/knowledge_engine/__init__.py
"""Documentation learning and retrieval system.

This module provides functionality for crawling, chunking, embedding,
and retrieving documentation for context-aware AI responses.
"""

from aise.knowledge_engine.vector_store import (
    VectorStore,
    ChromaDBVectorStore,
    DocumentChunk
)
from aise.knowledge_engine.sources import (
    DocumentationRegistry,
    DocumentationSource,
    SourceCategory,
    get_registry
)

__all__ = [
    'VectorStore',
    'ChromaDBVectorStore',
    'DocumentChunk',
    'DocumentationRegistry',
    'DocumentationSource',
    'SourceCategory',
    'get_registry'
]
