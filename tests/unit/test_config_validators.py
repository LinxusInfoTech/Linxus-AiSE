# tests/unit/test_config_validators.py
"""Unit tests for configuration validators."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from aise.config_ui.validators import (
    validate_anthropic_key,
    validate_openai_key,
    validate_deepseek_key,
    validate_llm_provider,
    validate_postgres_url,
    validate_redis_url,
    validate_zendesk_credentials,
    validate_freshdesk_credentials
)


@pytest.mark.asyncio
async def test_validate_anthropic_key_valid():
    """Test Anthropic API key validation with valid key."""
    with patch('anthropic.AsyncAnthropic') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value = mock_instance
        mock_instance.messages.create = AsyncMock(return_value=MagicMock())
        
        is_valid, error = await validate_anthropic_key("sk-ant-valid-key")
        
        assert is_valid is True
        assert error is None
        mock_instance.messages.create.assert_called_once()


@pytest.mark.asyncio
async def test_validate_anthropic_key_invalid():
    """Test Anthropic API key validation with invalid key."""
    with patch('anthropic.AsyncAnthropic') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value = mock_instance
        mock_instance.messages.create = AsyncMock(
            side_effect=Exception("Invalid API key")
        )
        
        is_valid, error = await validate_anthropic_key("sk-ant-invalid-key")
        
        assert is_valid is False
        assert error is not None


@pytest.mark.asyncio
async def test_validate_openai_key_valid():
    """Test OpenAI API key validation with valid key."""
    with patch('openai.AsyncOpenAI') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value = mock_instance
        mock_instance.chat.completions.create = AsyncMock(return_value=MagicMock())
        
        is_valid, error = await validate_openai_key("sk-valid-key")
        
        assert is_valid is True
        assert error is None


@pytest.mark.asyncio
async def test_validate_openai_key_invalid():
    """Test OpenAI API key validation with invalid key."""
    with patch('openai.AsyncOpenAI') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value = mock_instance
        mock_instance.chat.completions.create = AsyncMock(
            side_effect=Exception("Invalid API key")
        )
        
        is_valid, error = await validate_openai_key("sk-invalid-key")
        
        assert is_valid is False
        assert error is not None


@pytest.mark.asyncio
async def test_validate_deepseek_key_valid():
    """Test DeepSeek API key validation with valid key."""
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_instance.post = AsyncMock(return_value=mock_response)
        
        is_valid, error = await validate_deepseek_key("sk-valid-key")
        
        assert is_valid is True
        assert error is None


@pytest.mark.asyncio
async def test_validate_deepseek_key_invalid():
    """Test DeepSeek API key validation with invalid key."""
    with patch('httpx.AsyncClient') as mock_client:
        import httpx
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_instance.post = AsyncMock(return_value=mock_response)
        
        is_valid, error = await validate_deepseek_key("sk-invalid-key")
        
        assert is_valid is False
        assert "Invalid DeepSeek API key" in error


@pytest.mark.asyncio
async def test_validate_llm_provider_empty_key():
    """Test LLM provider validation with empty key."""
    is_valid, error = await validate_llm_provider("anthropic", "")
    
    assert is_valid is False
    assert "cannot be empty" in error


@pytest.mark.asyncio
async def test_validate_llm_provider_unknown():
    """Test LLM provider validation with unknown provider."""
    is_valid, error = await validate_llm_provider("unknown", "key")
    
    assert is_valid is False
    assert "Unknown provider" in error


@pytest.mark.asyncio
async def test_validate_llm_provider_ollama():
    """Test LLM provider validation for Ollama (no key needed)."""
    is_valid, error = await validate_llm_provider("ollama", "http://localhost:11434")
    
    assert is_valid is True
    assert error is None


@pytest.mark.asyncio
async def test_validate_postgres_url_valid():
    """Test PostgreSQL URL validation with valid connection."""
    with patch('asyncpg.connect') as mock_connect:
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value="PostgreSQL 14.0")
        mock_conn.close = AsyncMock()
        mock_connect.return_value = mock_conn
        
        is_valid, error = await validate_postgres_url("postgresql://user:pass@localhost/db")
        
        assert is_valid is True
        assert error is None
        mock_connect.assert_called_once()


@pytest.mark.asyncio
async def test_validate_postgres_url_invalid_format():
    """Test PostgreSQL URL validation with invalid format."""
    is_valid, error = await validate_postgres_url("mysql://user:pass@localhost/db")
    
    assert is_valid is False
    assert "must start with postgresql://" in error


@pytest.mark.asyncio
async def test_validate_postgres_url_auth_failed():
    """Test PostgreSQL URL validation with authentication failure."""
    with patch('asyncpg.connect') as mock_connect:
        import asyncpg
        mock_connect.side_effect = asyncpg.InvalidPasswordError("Authentication failed")
        
        is_valid, error = await validate_postgres_url("postgresql://user:wrong@localhost/db")
        
        assert is_valid is False
        assert "authentication failed" in error.lower()


@pytest.mark.asyncio
async def test_validate_redis_url_valid():
    """Test Redis URL validation with valid connection."""
    with patch('redis.asyncio.from_url') as mock_from_url:
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_client.close = AsyncMock()
        mock_from_url.return_value = mock_client
        
        is_valid, error = await validate_redis_url("redis://localhost:6379")
        
        assert is_valid is True
        assert error is None


@pytest.mark.asyncio
async def test_validate_redis_url_invalid_format():
    """Test Redis URL validation with invalid format."""
    is_valid, error = await validate_redis_url("http://localhost:6379")
    
    assert is_valid is False
    assert "must start with redis://" in error


@pytest.mark.asyncio
async def test_validate_zendesk_credentials_valid():
    """Test Zendesk credentials validation with valid credentials."""
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_instance.get = AsyncMock(return_value=mock_response)
        
        is_valid, error = await validate_zendesk_credentials(
            "mycompany", "admin@example.com", "valid-token"
        )
        
        assert is_valid is True
        assert error is None


@pytest.mark.asyncio
async def test_validate_zendesk_credentials_invalid():
    """Test Zendesk credentials validation with invalid credentials."""
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_instance.get = AsyncMock(return_value=mock_response)
        
        is_valid, error = await validate_zendesk_credentials(
            "mycompany", "admin@example.com", "invalid-token"
        )
        
        assert is_valid is False
        assert "authentication failed" in error.lower()


@pytest.mark.asyncio
async def test_validate_zendesk_credentials_missing():
    """Test Zendesk credentials validation with missing values."""
    is_valid, error = await validate_zendesk_credentials("", "", "")
    
    assert is_valid is False
    assert "required" in error.lower()


@pytest.mark.asyncio
async def test_validate_freshdesk_credentials_valid():
    """Test Freshdesk credentials validation with valid credentials."""
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_instance.get = AsyncMock(return_value=mock_response)
        
        is_valid, error = await validate_freshdesk_credentials("mycompany", "valid-key")
        
        assert is_valid is True
        assert error is None


@pytest.mark.asyncio
async def test_validate_freshdesk_credentials_invalid():
    """Test Freshdesk credentials validation with invalid credentials."""
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_instance.get = AsyncMock(return_value=mock_response)
        
        is_valid, error = await validate_freshdesk_credentials("mycompany", "invalid-key")
        
        assert is_valid is False
        assert "authentication failed" in error.lower()


@pytest.mark.asyncio
async def test_validate_url_accessible_valid():
    """Test URL accessibility validation with valid URL."""
    from aise.config_ui.validators import validate_url_accessible
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_instance.get = AsyncMock(return_value=mock_response)
        
        is_valid, error = await validate_url_accessible("https://example.com")
        
        assert is_valid is True
        assert error is None


@pytest.mark.asyncio
async def test_validate_url_accessible_404():
    """Test URL accessibility validation with 404 error."""
    from aise.config_ui.validators import validate_url_accessible
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_instance.get = AsyncMock(return_value=mock_response)
        
        is_valid, error = await validate_url_accessible("https://example.com/notfound")
        
        assert is_valid is False
        assert "404" in error


@pytest.mark.asyncio
async def test_validate_url_accessible_auth_required():
    """Test URL accessibility validation with authentication required (401/403)."""
    from aise.config_ui.validators import validate_url_accessible
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_instance.get = AsyncMock(return_value=mock_response)
        
        is_valid, error = await validate_url_accessible("https://example.com")
        
        # 401 is acceptable - means URL exists but needs auth
        assert is_valid is True
        assert error is None


@pytest.mark.asyncio
async def test_validate_url_accessible_timeout():
    """Test URL accessibility validation with timeout."""
    from aise.config_ui.validators import validate_url_accessible
    import httpx
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        mock_instance.get = AsyncMock(side_effect=httpx.ConnectTimeout("Timeout"))
        
        is_valid, error = await validate_url_accessible("https://example.com")
        
        assert is_valid is False
        assert "timeout" in error.lower()


@pytest.mark.asyncio
async def test_validate_url_accessible_connection_error():
    """Test URL accessibility validation with connection error."""
    from aise.config_ui.validators import validate_url_accessible
    import httpx
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        mock_instance.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
        
        is_valid, error = await validate_url_accessible("https://example.com")
        
        assert is_valid is False
        assert "connection failed" in error.lower()


@pytest.mark.asyncio
async def test_validate_url_accessible_invalid_format():
    """Test URL accessibility validation with invalid URL format."""
    from aise.config_ui.validators import validate_url_accessible
    
    is_valid, error = await validate_url_accessible("not-a-url")
    
    assert is_valid is False
    assert "must start with http" in error.lower()


@pytest.mark.asyncio
async def test_validate_url_accessible_empty():
    """Test URL accessibility validation with empty URL."""
    from aise.config_ui.validators import validate_url_accessible
    
    is_valid, error = await validate_url_accessible("")
    
    assert is_valid is False
    assert "cannot be empty" in error.lower()


@pytest.mark.asyncio
async def test_validate_zendesk_url_valid():
    """Test Zendesk URL validation with valid subdomain."""
    from aise.config_ui.validators import validate_zendesk_url
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_instance.get = AsyncMock(return_value=mock_response)
        
        is_valid, error = await validate_zendesk_url("mycompany")
        
        assert is_valid is True
        assert error is None


@pytest.mark.asyncio
async def test_validate_zendesk_url_with_full_url():
    """Test Zendesk URL validation with full URL provided."""
    from aise.config_ui.validators import validate_zendesk_url
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_instance.get = AsyncMock(return_value=mock_response)
        
        is_valid, error = await validate_zendesk_url("https://mycompany.zendesk.com")
        
        assert is_valid is True
        assert error is None


@pytest.mark.asyncio
async def test_validate_zendesk_url_empty():
    """Test Zendesk URL validation with empty subdomain."""
    from aise.config_ui.validators import validate_zendesk_url
    
    is_valid, error = await validate_zendesk_url("")
    
    assert is_valid is False
    assert "cannot be empty" in error.lower()


@pytest.mark.asyncio
async def test_validate_freshdesk_url_valid():
    """Test Freshdesk URL validation with valid domain."""
    from aise.config_ui.validators import validate_freshdesk_url
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_instance.get = AsyncMock(return_value=mock_response)
        
        is_valid, error = await validate_freshdesk_url("mycompany")
        
        assert is_valid is True
        assert error is None


@pytest.mark.asyncio
async def test_validate_freshdesk_url_with_full_url():
    """Test Freshdesk URL validation with full URL provided."""
    from aise.config_ui.validators import validate_freshdesk_url
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_instance.get = AsyncMock(return_value=mock_response)
        
        is_valid, error = await validate_freshdesk_url("https://mycompany.freshdesk.com")
        
        assert is_valid is True
        assert error is None


@pytest.mark.asyncio
async def test_validate_custom_support_url_valid():
    """Test custom support URL validation with valid URL."""
    from aise.config_ui.validators import validate_custom_support_url
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_instance.get = AsyncMock(return_value=mock_response)
        
        is_valid, error = await validate_custom_support_url("https://support.mycompany.com")
        
        assert is_valid is True
        assert error is None


@pytest.mark.asyncio
async def test_get_url_templates():
    """Test getting URL templates."""
    from aise.config_ui.validators import get_url_templates
    
    templates = get_url_templates()
    
    assert "zendesk" in templates
    assert "freshdesk" in templates
    assert "custom" in templates
    assert "{subdomain}" in templates["zendesk"]
    assert "{domain}" in templates["freshdesk"]
