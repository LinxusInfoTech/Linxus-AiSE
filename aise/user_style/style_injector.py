# aise/user_style/style_injector.py
"""Style prompt generation for AI responses.

Requirements: 12.5, 12.6, 12.9, 12.10
"""

import structlog
from typing import Dict, List, Any, Optional

logger = structlog.get_logger(__name__)

# How many recent interactions to use for style guidance
DEFAULT_RECENT_K = 5


class StyleInjector:
    """Retrieves recent user style examples and generates a style guidance prompt.

    Prioritizes the most recent interactions so the AI adapts to how the
    user communicates right now, not how they communicated months ago.
    """

    def __init__(self, style_embedder):
        """Initialize StyleInjector.

        Args:
            style_embedder: StyleEmbedder instance for retrieval
        """
        self._embedder = style_embedder
        logger.info("style_injector_initialized")

    async def get_style_context(
        self,
        query: str,
        top_k: int = DEFAULT_RECENT_K
    ) -> Optional[str]:
        """Retrieve recent style examples and generate a guidance prompt.

        Args:
            query: Current user message (used as search query)
            top_k: Number of recent examples to retrieve

        Returns:
            Style guidance string to inject into the LLM prompt, or None
            if no examples are available.
        """
        interactions = await self._embedder.search(query, top_k=top_k)

        if not interactions:
            logger.info("style_context_empty", reason="no_interactions_found")
            return None

        # Sort by timestamp descending so most recent come first
        interactions.sort(
            key=lambda x: x.get("timestamp") or "",
            reverse=True
        )

        guidance = self._build_guidance(interactions)

        logger.info(
            "style_context_generated",
            examples_used=len(interactions),
            guidance_length=len(guidance)
        )
        return guidance

    def _build_guidance(self, interactions: List[Dict[str, Any]]) -> str:
        """Build a style guidance string from interaction examples.

        Args:
            interactions: List of interaction dicts (most recent first)

        Returns:
            Formatted style guidance prompt
        """
        # Aggregate tone indicators across all examples
        all_tones: List[str] = []
        for interaction in interactions:
            all_tones.extend(interaction.get("tone_indicators") or [])

        # Count frequency
        tone_counts: Dict[str, int] = {}
        for tone in all_tones:
            tone_counts[tone] = tone_counts.get(tone, 0) + 1

        dominant_tones = sorted(tone_counts, key=tone_counts.get, reverse=True)[:3]

        lines = [
            "Adapt your response to match the user's communication style:",
        ]

        if dominant_tones:
            lines.append(f"- Tone: {', '.join(dominant_tones)}")

        # Add example snippets (up to 3, most recent first)
        lines.append("- Recent examples of how this user communicates:")
        for interaction in interactions[:3]:
            snippet = interaction["message"][:120].replace("\n", " ")
            lines.append(f'  • "{snippet}"')

        return "\n".join(lines)
