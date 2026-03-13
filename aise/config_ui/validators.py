# aise/config_ui/validators.py
"""Configuration validation functions for Config UI.

This module provides validation functions to test API keys, database connectivity,
and other configuration values before persisting them.

Example usage:
    >>> from aise.config_ui.validators import validate_llm_provider
    >>> 
    >>> is_valid, error = await validate_llm_provider("anthropic", "sk-ant-...")
    >>> if is_valid:
    ...     print("API key is valid")
    ... else:
    ...     print(f"Validation failed: {error}")
"""

from typing import Tuple, Optional
import structlog
import asyncpg
import httpx

logger = structlog.get_logger(__name__)


async def validate_anthropic_key(api_key: str) -> Tuple[bool, Optional[str]]:
    """Validate Anthropic API key by making a test API call.
    
    Args:
        api_key: Anthropic API key to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        import anthropic
        
        client = anthropic.AsyncAnthropic(api_key=api_key)
        
        # Make a minimal test request
        response = await client.messages.create(
            model="claude-3-haiku-20240307",  # Use cheapest model
            max_tokens=10,
            messages=[{"role": "user", "content": "test"}]
        )
        
        logger.info("anthropic_key_validated")
        return True, None
        
    except anthropic.AuthenticationError as e:
        logger.warning("anthropic_key_invalid", error=str(e))
        return False, (
            "Invalid Anthropic API key. "
            "Remediation: Get your API key from https://console.anthropic.com/settings/keys "
            "and ensure it starts with 'sk-ant-'"
        )
    
    except Exception as e:
        logger.error("anthropic_validation_failed", error=str(e))
        return False, (
            f"Failed to validate Anthropic API key: {str(e)}. "
            "Remediation: Check your internet connection and ensure the Anthropic API is accessible."
        )


async def validate_openai_key(api_key: str) -> Tuple[bool, Optional[str]]:
    """Validate OpenAI API key by making a test API call.
    
    Args:
        api_key: OpenAI API key to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        import openai
        
        client = openai.AsyncOpenAI(api_key=api_key)
        
        # Make a minimal test request
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",  # Use cheapest model
            max_tokens=10,
            messages=[{"role": "user", "content": "test"}]
        )
        
        logger.info("openai_key_validated")
        return True, None
        
    except openai.AuthenticationError as e:
        logger.warning("openai_key_invalid", error=str(e))
        return False, (
            "Invalid OpenAI API key. "
            "Remediation: Get your API key from https://platform.openai.com/api-keys "
            "and ensure it starts with 'sk-'"
        )
    
    except Exception as e:
        logger.error("openai_validation_failed", error=str(e))
        return False, (
            f"Failed to validate OpenAI API key: {str(e)}. "
            "Remediation: Check your internet connection and ensure the OpenAI API is accessible."
        )


async def validate_deepseek_key(api_key: str) -> Tuple[bool, Optional[str]]:
    """Validate DeepSeek API key by making a test API call.
    
    Args:
        api_key: DeepSeek API key to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": "test"}],
                    "max_tokens": 10
                },
                timeout=10.0
            )
            
            if response.status_code == 401:
                logger.warning("deepseek_key_invalid")
                return False, "Invalid DeepSeek API key. Please check your key and try again."
            
            response.raise_for_status()
            
            logger.info("deepseek_key_validated")
            return True, None
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return False, "Invalid DeepSeek API key. Please check your key and try again."
        logger.error("deepseek_validation_failed", error=str(e))
        return False, f"Failed to validate DeepSeek API key: {str(e)}"
    
    except Exception as e:
        logger.error("deepseek_validation_failed", error=str(e))
        return False, f"Failed to validate DeepSeek API key: {str(e)}"


async def validate_llm_provider(provider: str, api_key: str) -> Tuple[bool, Optional[str]]:
    """Validate LLM provider API key.
    
    Args:
        provider: Provider name (anthropic, openai, deepseek)
        api_key: API key to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not api_key or not api_key.strip():
        return False, "API key cannot be empty"
    
    if provider == "anthropic":
        return await validate_anthropic_key(api_key)
    elif provider == "openai":
        return await validate_openai_key(api_key)
    elif provider == "deepseek":
        return await validate_deepseek_key(api_key)
    elif provider == "ollama":
        # Ollama doesn't need API key validation
        return True, None
    else:
        return False, f"Unknown provider: {provider}"


async def validate_postgres_url(postgres_url: str) -> Tuple[bool, Optional[str]]:
    """Validate PostgreSQL connection string by attempting to connect.
    
    Args:
        postgres_url: PostgreSQL connection string
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not postgres_url or not postgres_url.strip():
        return False, "PostgreSQL URL cannot be empty"
    
    if not postgres_url.startswith(("postgresql://", "postgres://")):
        return False, "PostgreSQL URL must start with postgresql:// or postgres://"
    
    try:
        # Attempt to connect
        conn = await asyncpg.connect(postgres_url, timeout=5)
        
        # Test query
        version = await conn.fetchval("SELECT version()")
        
        await conn.close()
        
        logger.info("postgres_url_validated", version=version)
        return True, None
        
    except asyncpg.InvalidPasswordError:
        logger.warning("postgres_auth_failed")
        return False, (
            "PostgreSQL authentication failed. "
            "Remediation: Check your username and password in the connection string. "
            "Format: postgresql://username:password@host:port/database"
        )
    
    except asyncpg.InvalidCatalogNameError:
        logger.warning("postgres_database_not_found")
        return False, (
            "PostgreSQL database does not exist. "
            "Remediation: Create the database first using: CREATE DATABASE your_database_name; "
            "or update the connection string to use an existing database."
        )
    
    except Exception as e:
        logger.error("postgres_validation_failed", error=str(e))
        return False, (
            f"Failed to connect to PostgreSQL: {str(e)}. "
            "Remediation: Ensure PostgreSQL is running and accessible. "
            "Check host, port, and firewall settings."
        )


async def validate_redis_url(redis_url: str) -> Tuple[bool, Optional[str]]:
    """Validate Redis connection string by attempting to connect.
    
    Args:
        redis_url: Redis connection string
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not redis_url or not redis_url.strip():
        return False, "Redis URL cannot be empty"
    
    if not redis_url.startswith("redis://"):
        return False, "Redis URL must start with redis://"
    
    try:
        import redis.asyncio as redis
        
        # Attempt to connect
        client = redis.from_url(redis_url, socket_connect_timeout=5)
        
        # Test ping
        await client.ping()
        
        await client.close()
        
        logger.info("redis_url_validated")
        return True, None
        
    except Exception as e:
        logger.error("redis_validation_failed", error=str(e))
        return False, (
            f"Failed to connect to Redis: {str(e)}. "
            "Remediation: Ensure Redis is running and accessible. "
            "Check host, port, and firewall settings. "
            "Start Redis with: docker run -d -p 6379:6379 redis:latest"
        )


async def validate_zendesk_credentials(
    subdomain: str,
    email: str,
    api_token: str
) -> Tuple[bool, Optional[str]]:
    """Validate Zendesk credentials by making a test API call.
    
    Args:
        subdomain: Zendesk subdomain
        email: Zendesk admin email
        api_token: Zendesk API token
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not all([subdomain, email, api_token]):
        return False, "Zendesk subdomain, email, and API token are required"
    
    try:
        async with httpx.AsyncClient() as client:
            url = f"https://{subdomain}.zendesk.com/api/v2/users/me.json"
            
            response = await client.get(
                url,
                auth=(f"{email}/token", api_token),
                timeout=10.0
            )
            
            if response.status_code == 401:
                logger.warning("zendesk_auth_failed")
                return False, "Zendesk authentication failed. Please check your credentials."
            
            response.raise_for_status()
            
            logger.info("zendesk_credentials_validated")
            return True, None
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return False, "Zendesk authentication failed. Please check your credentials."
        logger.error("zendesk_validation_failed", error=str(e))
        return False, f"Failed to validate Zendesk credentials: {str(e)}"
    
    except Exception as e:
        logger.error("zendesk_validation_failed", error=str(e))
        return False, f"Failed to validate Zendesk credentials: {str(e)}"


async def validate_freshdesk_credentials(
    domain: str,
    api_key: str
) -> Tuple[bool, Optional[str]]:
    """Validate Freshdesk credentials by making a test API call.
    
    Args:
        domain: Freshdesk domain
        api_key: Freshdesk API key
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not all([domain, api_key]):
        return False, "Freshdesk domain and API key are required"
    
    try:
        async with httpx.AsyncClient() as client:
            url = f"https://{domain}.freshdesk.com/api/v2/tickets"
            
            response = await client.get(
                url,
                auth=(api_key, "X"),
                timeout=10.0
            )
            
            if response.status_code == 401:
                logger.warning("freshdesk_auth_failed")
                return False, "Freshdesk authentication failed. Please check your API key."
            
            response.raise_for_status()
            
            logger.info("freshdesk_credentials_validated")
            return True, None
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return False, "Freshdesk authentication failed. Please check your API key."
        logger.error("freshdesk_validation_failed", error=str(e))
        return False, f"Failed to validate Freshdesk credentials: {str(e)}"
    
    except Exception as e:
        logger.error("freshdesk_validation_failed", error=str(e))
        return False, f"Failed to validate Freshdesk credentials: {str(e)}"


# URL Templates for common platforms
URL_TEMPLATES = {
    "zendesk": "https://{subdomain}.zendesk.com",
    "freshdesk": "https://{domain}.freshdesk.com",
    "custom": "{url}"
}


def get_url_templates() -> dict:
    """Get URL templates for common support platforms.
    
    Returns:
        Dictionary of platform names to URL templates
    """
    return URL_TEMPLATES.copy()


async def validate_url_accessible(url: str) -> Tuple[bool, Optional[str]]:
    """Validate that a URL is accessible via HTTP GET request.
    
    Args:
        url: URL to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url or not url.strip():
        return False, "URL cannot be empty"
    
    # Basic URL format validation
    if not url.startswith(("http://", "https://")):
        return False, "URL must start with http:// or https://"
    
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                url,
                timeout=10.0
            )
            
            # Accept any 2xx or 3xx status code as valid
            if 200 <= response.status_code < 400:
                logger.info("url_validated", url=url, status_code=response.status_code)
                return True, None
            elif response.status_code == 401 or response.status_code == 403:
                # Authentication required is acceptable - means URL exists
                logger.info("url_validated_auth_required", url=url, status_code=response.status_code)
                return True, None
            elif response.status_code == 404:
                logger.warning("url_not_found", url=url)
                return False, f"URL not found (404). Please check the URL is correct."
            else:
                logger.warning("url_unexpected_status", url=url, status_code=response.status_code)
                return False, f"URL returned unexpected status code: {response.status_code}"
                
    except httpx.ConnectTimeout:
        logger.error("url_connect_timeout", url=url)
        return False, f"Connection timeout. The server at {url} did not respond in time."
    
    except httpx.ConnectError as e:
        logger.error("url_connect_error", url=url, error=str(e))
        return False, f"Connection failed. Could not connect to {url}. Check the URL and network connectivity."
    
    except httpx.TimeoutException:
        logger.error("url_timeout", url=url)
        return False, f"Request timeout. The server at {url} took too long to respond."
    
    except httpx.HTTPStatusError as e:
        logger.error("url_http_error", url=url, status_code=e.response.status_code)
        return False, f"HTTP error {e.response.status_code}: {e.response.reason_phrase}"
    
    except Exception as e:
        logger.error("url_validation_failed", url=url, error=str(e))
        error_msg = str(e)
        
        # Provide more specific error messages for common issues
        if "Name or service not known" in error_msg or "getaddrinfo failed" in error_msg:
            return False, f"DNS resolution failed. The domain name could not be found. Check the URL spelling."
        elif "SSL" in error_msg or "certificate" in error_msg.lower():
            return False, f"SSL/TLS error. The server's security certificate may be invalid."
        else:
            return False, f"Failed to validate URL: {error_msg}"


async def validate_zendesk_url(subdomain: str) -> Tuple[bool, Optional[str]]:
    """Validate Zendesk URL by checking accessibility.
    
    Args:
        subdomain: Zendesk subdomain (e.g., 'mycompany' for mycompany.zendesk.com)
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not subdomain or not subdomain.strip():
        return False, "Zendesk subdomain cannot be empty"
    
    # Remove any protocol or domain suffix if provided
    subdomain = subdomain.replace("https://", "").replace("http://", "")
    subdomain = subdomain.split(".zendesk.com")[0]
    
    url = f"https://{subdomain}.zendesk.com"
    return await validate_url_accessible(url)


async def validate_freshdesk_url(domain: str) -> Tuple[bool, Optional[str]]:
    """Validate Freshdesk URL by checking accessibility.
    
    Args:
        domain: Freshdesk domain (e.g., 'mycompany' for mycompany.freshdesk.com)
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not domain or not domain.strip():
        return False, "Freshdesk domain cannot be empty"
    
    # Remove any protocol or domain suffix if provided
    domain = domain.replace("https://", "").replace("http://", "")
    domain = domain.split(".freshdesk.com")[0]
    
    url = f"https://{domain}.freshdesk.com"
    return await validate_url_accessible(url)


async def validate_custom_support_url(url: str) -> Tuple[bool, Optional[str]]:
    """Validate custom support platform URL by checking accessibility.
    
    Args:
        url: Full URL to custom support platform
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    return await validate_url_accessible(url)
