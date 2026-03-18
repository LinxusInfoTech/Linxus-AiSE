# aise/user_style/observer.py
"""User interaction observation and capture.

Requirements: 12.1, 12.2, 12.3
"""

import hashlib
import structlog
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = structlog.get_logger(__name__)

# Tone indicator patterns
FORMAL_INDICATORS = ["please", "kindly", "would you", "could you", "thank you", "regards"]
CASUAL_INDICATORS = ["hey", "hi", "thanks", "yeah", "nope", "ok", "cool", "asap"]
TECHNICAL_INDICATORS = ["kubectl", "aws", "terraform", "docker", "pod", "instance", "vpc", "iam"]
TERSE_INDICATORS = ["fix", "broken", "down", "error", "fail", "crash"]


class StyleObserver:
    """Captures and analyzes user communication style from interactions.

    Observes ticket replies and CLI interactions to extract tone indicators
    that inform how the AI should adapt its responses.
    """

    def observe_ticket_reply(
        self,
        ticket_id: str,
        message: str,
        context: str = "ticket_reply"
    ) -> Dict[str, Any]:
        """Capture a user ticket response and extract style indicators.

        Args:
            ticket_id: Ticket identifier for context
            message: The user's message text
            context: Context label for the interaction

        Returns:
            Interaction dict with id, message, timestamp, context, tone_indicators
        """
        tone_indicators = self._extract_tone_indicators(message)
        interaction = self._build_interaction(message, context, tone_indicators)

        logger.info(
            "style_observed_ticket_reply",
            ticket_id=ticket_id,
            tone_indicators=tone_indicators,
            message_length=len(message)
        )
        return interaction

    def observe_cli_interaction(
        self,
        message: str,
        context: str = "cli"
    ) -> Dict[str, Any]:
        """Capture a CLI interaction and extract style indicators.

        Args:
            message: The user's CLI input or question
            context: Context label for the interaction

        Returns:
            Interaction dict with id, message, timestamp, context, tone_indicators
        """
        tone_indicators = self._extract_tone_indicators(message)
        interaction = self._build_interaction(message, context, tone_indicators)

        logger.info(
            "style_observed_cli_interaction",
            tone_indicators=tone_indicators,
            message_length=len(message)
        )
        return interaction

    def _extract_tone_indicators(self, message: str) -> List[str]:
        """Extract tone indicators from a message.

        Args:
            message: Message text to analyze

        Returns:
            List of tone indicator labels
        """
        lower = message.lower()
        indicators = []

        if any(kw in lower for kw in FORMAL_INDICATORS):
            indicators.append("formal")
        if any(kw in lower for kw in CASUAL_INDICATORS):
            indicators.append("casual")
        if any(kw in lower for kw in TECHNICAL_INDICATORS):
            indicators.append("technical")
        if any(kw in lower for kw in TERSE_INDICATORS):
            indicators.append("terse")
        if "?" in message:
            indicators.append("inquisitive")
        if len(message.split()) > 50:
            indicators.append("verbose")
        elif len(message.split()) < 10:
            indicators.append("concise")

        return indicators

    def _build_interaction(
        self,
        message: str,
        context: str,
        tone_indicators: List[str]
    ) -> Dict[str, Any]:
        """Build a standardized interaction dict.

        Args:
            message: Message text
            context: Context label
            tone_indicators: Extracted tone indicators

        Returns:
            Interaction dictionary
        """
        timestamp = datetime.utcnow().isoformat()
        interaction_id = hashlib.sha256(
            f"{message}{timestamp}".encode()
        ).hexdigest()[:16]

        return {
            "id": interaction_id,
            "message": message,
            "timestamp": timestamp,
            "context": context,
            "tone_indicators": tone_indicators,
        }
