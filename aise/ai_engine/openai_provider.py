# aise/ai_engine/openai_provider.py
"""OpenAI GPT LLM provider implementation.

This module implements the LLMProvider interface for OpenAI's GPT models,
supporting GPT-4, GPT-4 Turbo, and GPT-3.5 with streaming and retry logic.

Example usage:
    >>> from aise.ai_engine.openai_provider import OpenAIProvider
    >>> from aise.core.config import get_config
    >>> 
    >>> config = get_config()
    >>> provider = OpenAIProvider(config)
    >>> 
    >>> messages = [{"role": "user", "content": "Explain Kubernetes pods"}]
    >>> result = await provider.complete(messages)
    >>> print(result.content)
"""

from typing import List, Dict, Optional, AsyncIterator
import openai
import tiktoken
import structlog
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from aise.ai_engine.base import LLMProvider, CompletionResult, TokenUsage
from aise.core.exceptions import ProviderError, AuthenticationError

logger = structlog.get_logger(__name__)


# OpenAI pricing per 1M tokens (as of 2024)
OPENAI_PRICING = {
    "gpt-4-turbo-preview": {"input": 10.00, "output": 30.00},
    "gpt-4-0125-preview": {"input": 10.00, "output": 30.00},
    "gpt-4-1106-preview": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-4-32k": {"input": 60.00, "output": 120.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "gpt-3.5-turbo-16k": {"input": 3.00, "output": 4.00},
}


class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider implementation.
    
    Supports GPT-4, GPT-4 Turbo, and GPT-3.5 models with streaming,
    retry logic, and accurate token counting via tiktoken.
    """
    
    def __init__(self, config):
        """Initialize OpenAI provider.
        
        Args:
            config: Configuration instance with OPENAI_API_KEY
        
        Raises:
            AuthenticationError: If API key is not configured
        """
        super().__init__(config)
        
        if not config.OPENAI_API_KEY:
            raise AuthenticationError(
                "OPENAI_API_KEY not configured. "
                "Set it in .env or via 'aise config set OPENAI_API_KEY <key>'"
            )
        
        self._client = openai.AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        self._default_model = getattr(config, "OPENAI_MODEL", "gpt-4-turbo-preview")
        
        logger.info(
            "openai_provider_initialized",
            default_model=self._default_model
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.APIConnectionError)),
        reraise=True
    )
    async def complete(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None
    ) -> CompletionResult:
        """Generate a completion using GPT.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate (default: 4096)
            model: Specific GPT model (default: gpt-4-turbo-preview)
        
        Returns:
            CompletionResult with generated text and metadata
        
        Raises:
            ProviderError: If API call fails
            AuthenticationError: If API key is invalid
        """
        model = model or self._default_model
        max_tokens = max_tokens or 4096
        
        try:
            logger.info(
                "openai_completion_request",
                model=model,
                message_count=len(messages),
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # Prepend system prompt if provided
            full_messages = []
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            full_messages.extend(messages)
            
            # Make API call
            response = await self._client.chat.completions.create(
                model=model,
                messages=full_messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # Extract content
            content = response.choices[0].message.content or ""
            
            # Build usage stats
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                estimated_cost_usd=self.estimate_cost(
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                    model
                )
            )
            
            logger.info(
                "openai_completion_success",
                model=model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                cost_usd=usage.estimated_cost_usd
            )
            
            return CompletionResult(
                content=content,
                model=model,
                usage=usage,
                provider="openai",
                finish_reason=response.choices[0].finish_reason
            )
            
        except openai.AuthenticationError as e:
            logger.error("openai_auth_error", error=str(e))
            raise AuthenticationError(f"OpenAI authentication failed: {str(e)}")
        
        except openai.RateLimitError as e:
            logger.error("openai_rate_limit", error=str(e))
            raise ProviderError(f"OpenAI rate limit exceeded: {str(e)}")
        
        except Exception as e:
            logger.error("openai_completion_failed", error=str(e), model=model)
            raise ProviderError(f"OpenAI completion failed: {str(e)}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((openai.RateLimitError, openai.APIConnectionError)),
        reraise=True
    )
    async def stream_complete(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Stream completion tokens from GPT.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate (default: 4096)
            model: Specific GPT model (default: gpt-4-turbo-preview)
        
        Yields:
            String tokens as they are generated
        
        Raises:
            ProviderError: If API call fails
            AuthenticationError: If API key is invalid
        """
        model = model or self._default_model
        max_tokens = max_tokens or 4096
        
        try:
            logger.info(
                "openai_stream_request",
                model=model,
                message_count=len(messages),
                temperature=temperature
            )
            
            # Prepend system prompt if provided
            full_messages = []
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            full_messages.extend(messages)
            
            # Stream response
            stream = await self._client.chat.completions.create(
                model=model,
                messages=full_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            
            logger.info("openai_stream_complete", model=model)
            
        except openai.AuthenticationError as e:
            logger.error("openai_auth_error", error=str(e))
            raise AuthenticationError(f"OpenAI authentication failed: {str(e)}")
        
        except openai.RateLimitError as e:
            logger.error("openai_rate_limit", error=str(e))
            raise ProviderError(f"OpenAI rate limit exceeded: {str(e)}")
        
        except Exception as e:
            logger.error("openai_stream_failed", error=str(e), model=model)
            raise ProviderError(f"OpenAI streaming failed: {str(e)}")
    
    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """Count tokens in text using tiktoken.
        
        Args:
            text: Text to count tokens for
            model: Model to use for tokenization (default: gpt-4)
        
        Returns:
            Exact token count
        """
        model = model or self._default_model
        
        try:
            # Get encoding for model
            encoding = tiktoken.encoding_for_model(model)
            return len(encoding.encode(text))
        except Exception:
            # Fallback to cl100k_base encoding (used by GPT-4)
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
    
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
            model: Model used (default: gpt-4-turbo-preview)
        
        Returns:
            Estimated cost in USD
        """
        model = model or self._default_model
        
        # Get pricing for model (default to GPT-4 Turbo if not found)
        pricing = OPENAI_PRICING.get(
            model,
            OPENAI_PRICING["gpt-4-turbo-preview"]
        )
        
        # Calculate cost (pricing is per 1M tokens)
        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        
        return input_cost + output_cost
