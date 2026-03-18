# aise/user_style/style_embedder.py
"""User communication style embedding.

Requirements: 12.4, 12.8
"""

import structlog
from typing import Dict, List, Any, Optional

logger = structlog.get_logger(__name__)


class StyleEmbedder:
    """Embeds user interactions into the dedicated user_style vector collection.

    Stores interactions separately from documentation so style retrieval
    doesn't pollute knowledge search results.
    """

    def __init__(self, vector_store):
        """Initialize StyleEmbedder.

        Args:
            vector_store: ChromaDBVectorStore instance with upsert_user_style support
        """
        self._vector_store = vector_store
        logger.info("style_embedder_initialized")

    async def embed(self, interaction: Dict[str, Any]) -> None:
        """Embed a single user interaction into the user_style collection.

        Args:
            interaction: Interaction dict from StyleObserver
        """
        await self.embed_batch([interaction])

    async def embed_batch(self, interactions: List[Dict[str, Any]]) -> None:
        """Embed multiple user interactions in one call.

        Args:
            interactions: List of interaction dicts from StyleObserver
        """
        if not interactions:
            return

        await self._vector_store.upsert_user_style(interactions)

        logger.info(
            "style_interactions_embedded",
            count=len(interactions)
        )

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar user style examples.

        Args:
            query: Query text (e.g., current user message)
            top_k: Number of examples to retrieve

        Returns:
            List of interaction dicts
        """
        results = await self._vector_store.search_user_style(query, top_k=top_k)
        logger.info("style_search_completed", results_count=len(results))
        return results
