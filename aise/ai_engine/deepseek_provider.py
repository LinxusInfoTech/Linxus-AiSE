# aise/ai_engine/deepseek_provider.py
"""DeepSeek LLM provider implementation.

This module implements the LLMProvider interface for DeepSeek models using
httpx for direct API calls, supporting both streaming and non-streaming.

Example usage:
    >>> from aise.ai_engine.deepseek_provider import DeepSeekProvider
    >>> from aise.core.config import get_config
    >>> 
    >>> config = get_config()
    >>> provider = DeepSeekProvider(config)
    >>> 
    >>> messages = [{"role": "user", "content": "Explain Docker containers"}]
    >>> result = await provider.complete(messages)
    >>> print(result.content)
"""

from typing import List, Dict, Optional, AsyncIterator
import httpx
import json
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


# DeepSeek pricing per 1M tokens (as of 2024)
DEEPSEEK_PRICING = {
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-coder": {"input": 0.14, "output": 0.28},
}


class DeepSeekProvider(LLMProvider):
    """DeepSeek provider implementation using httpx.
    
    Supports DeepSeek Chat and Coder models with streaming and retry logic.
    """
    
    def __init__(self, config):
        """Initialize DeepSeek provider.
        
        Args:
            config: Configuration instance with DEEPSEEK_API_KEY
        
        Raises:
            AuthenticationError: If API key is not configured
        """
        super().__init__(config)
        
        if not config.DEEPSEEK_API_KEY:
            raise AuthenticationError(
                "DEEPSEEK_API_KEY not configured. "
                "Set it in .env or via 'aise config set DEEPSEEK_API_KEY <key>'"
            )
        
        self._api_key = config.DEEPSEEK_API_KEY
        self._base_url = getattr(config, "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        self._default_model = getattr(config, "DEEPSEEK_MODEL", "deepseek-chat")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json"
            },
            timeout=60.0
        )
        
        logger.info(
            "deepseek_provider_initialized",
            default_model=self._default_model,
            base_url=self._base_url
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError)),
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
        """Generate a completion using DeepSeek.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate (default: 4096)
            model: Specific DeepSeek model (default: deepseek-chat)
        
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
                "deepseek_completion_request",
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
            
            # Build request payload
            payload = {
                "model": model,
                "messages": full_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False
            }
            
            # Make API call
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract content
            content = data["choices"][0]["message"]["content"]
            
            # Build usage stats
            usage_data = data.get("usage", {})
            usage = TokenUsage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
                estimated_cost_usd=self.estimate_cost(
                    usage_data.get("prompt_tokens", 0),
                    usage_data.get("completion_tokens", 0),
                    model
                )
            )
            
            logger.info(
                "deepseek_completion_success",
                model=model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                cost_usd=usage.estimated_cost_usd
            )
            
            return CompletionResult(
                content=content,
                model=model,
                usage=usage,
                provider="deepseek",
                finish_reason=data["choices"][0].get("finish_reason")
            )
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("deepseek_auth_error", error=str(e))
                raise AuthenticationError(f"DeepSeek authentication failed: {str(e)}")
            elif e.response.status_code == 429:
                logger.error("deepseek_rate_limit", error=str(e))
                raise ProviderError(f"DeepSeek rate limit exceeded: {str(e)}")
            else:
                logger.error("deepseek_http_error", status=e.response.status_code, error=str(e))
                raise ProviderError(f"DeepSeek API error: {str(e)}")
        
        except Exception as e:
            logger.error("deepseek_completion_failed", error=str(e), model=model)
            raise ProviderError(f"DeepSeek completion failed: {str(e)}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError)),
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
        """Stream completion tokens from DeepSeek.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate (default: 4096)
            model: Specific DeepSeek model (default: deepseek-chat)
        
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
                "deepseek_stream_request",
                model=model,
                message_count=len(messages),
                temperature=temperature
            )
            
            # Prepend system prompt if provided
            full_messages = []
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            full_messages.extend(messages)
            
            # Build request payload
            payload = {
                "model": model,
                "messages": full_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True
            }
            
            # Stream response
            async with self._client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix
                        
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0]["delta"]
                            
                            if "content" in delta:
                                yield delta["content"]
                        except json.JSONDecodeError:
                            continue
            
            logger.info("deepseek_stream_complete", model=model)
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("deepseek_auth_error", error=str(e))
                raise AuthenticationError(f"DeepSeek authentication failed: {str(e)}")
            elif e.response.status_code == 429:
                logger.error("deepseek_rate_limit", error=str(e))
                raise ProviderError(f"DeepSeek rate limit exceeded: {str(e)}")
            else:
                logger.error("deepseek_http_error", status=e.response.status_code, error=str(e))
                raise ProviderError(f"DeepSeek API error: {str(e)}")
        
        except Exception as e:
            logger.error("deepseek_stream_failed", error=str(e), model=model)
            raise ProviderError(f"DeepSeek streaming failed: {str(e)}")
    
    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """Count tokens in text (approximate).
        
        Args:
            text: Text to count tokens for
            model: Model to use (ignored)
        
        Returns:
            Approximate token count
        """
        # DeepSeek uses a similar tokenizer to GPT
        # Rough approximation: 1 token ≈ 4 characters
        return len(text) // 4
    
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
            model: Model used (default: deepseek-chat)
        
        Returns:
            Estimated cost in USD
        """
        model = model or self._default_model
        
        # Get pricing for model (default to deepseek-chat if not found)
        pricing = DEEPSEEK_PRICING.get(
            model,
            DEEPSEEK_PRICING["deepseek-chat"]
        )
        
        # Calculate cost (pricing is per 1M tokens)
        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        
        return input_cost + output_cost
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close httpx client."""
        await self._client.aclose()
