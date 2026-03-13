# aise/ai_engine/base.py
"""Abstract base class for LLM providers.

This module defines the interface that all LLM providers must implement,
providing a unified API for completion generation across different providers.

Example usage:
    >>> from aise.ai_engine.anthropic_provider import AnthropicProvider
    >>> from aise.core.config import get_config
    >>> 
    >>> config = get_config()
    >>> provider = AnthropicProvider(config)
    >>> 
    >>> messages = [{"role": "user", "content": "Hello!"}]
    >>> response = await provider.complete(messages)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncIterator
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TokenUsage:
    """Token usage statistics for a completion.
    
    Attributes:
        prompt_tokens: Number of tokens in the prompt
        completion_tokens: Number of tokens in the completion
        total_tokens: Total tokens used
        estimated_cost_usd: Estimated cost in USD (if available)
    """
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: Optional[float] = None


@dataclass
class CompletionResult:
    """Result of a completion request.
    
    Attributes:
        content: The generated text
        model: Model used for generation
        usage: Token usage statistics
        provider: Provider name
        finish_reason: Reason completion finished (e.g., "stop", "length")
    """
    content: str
    model: str
    usage: TokenUsage
    provider: str
    finish_reason: Optional[str] = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers.
    
    All LLM providers (Anthropic, OpenAI, DeepSeek, Ollama) must implement
    this interface to ensure consistent behavior across the system.
    """
    
    def __init__(self, config):
        """Initialize provider with configuration.
        
        Args:
            config: Configuration instance containing API keys and settings
        """
        self._config = config
        self._provider_name = self.__class__.__name__.replace("Provider", "").lower()
    
    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return self._provider_name
    
    @abstractmethod
    async def complete(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None
    ) -> CompletionResult:
        """Generate a completion from messages.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys
                     Example: [{"role": "user", "content": "Hello!"}]
            system_prompt: Optional system prompt to prepend
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate (None for provider default)
            model: Specific model to use (None for provider default)
        
        Returns:
            CompletionResult with generated text and metadata
        
        Raises:
            ProviderError: If the provider API call fails
            AuthenticationError: If API key is invalid
        """
        pass
    
    @abstractmethod
    async def stream_complete(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Stream completion tokens as they are generated.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys
            system_prompt: Optional system prompt to prepend
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate (None for provider default)
            model: Specific model to use (None for provider default)
        
        Yields:
            String tokens as they are generated
        
        Raises:
            ProviderError: If the provider API call fails
            AuthenticationError: If API key is invalid
        """
        pass
    
    @abstractmethod
    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """Count tokens in text for the given model.
        
        Args:
            text: Text to count tokens for
            model: Model to use for tokenization (None for default)
        
        Returns:
            Number of tokens
        """
        pass
    
    @abstractmethod
    def estimate_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: Optional[str] = None
    ) -> float:
        """Estimate cost in USD for token usage.
        
        Args:
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            model: Model used (None for default)
        
        Returns:
            Estimated cost in USD
        """
        pass
    
    async def health_check(self) -> bool:
        """Check if the provider is available and credentials are valid.
        
        Returns:
            True if provider is healthy, False otherwise
        """
        try:
            # Simple test completion
            messages = [{"role": "user", "content": "test"}]
            await self.complete(messages, max_tokens=5)
            return True
        except Exception as e:
            logger.error(
                "provider_health_check_failed",
                provider=self.provider_name,
                error=str(e)
            )
            return False
