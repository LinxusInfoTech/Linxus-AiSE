# tests/integration/test_config_ui_url_validation.py
"""Integration tests for Config UI URL validation."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from aise.config_ui.app import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_get_url_templates(client):
    """Test getting URL templates endpoint."""
    response = client.get("/api/url-templates")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "templates" in data
    assert "examples" in data
    assert "zendesk" in data["templates"]
    assert "freshdesk" in data["templates"]
    assert "custom" in data["templates"]


@pytest.mark.asyncio
async def test_config_update_with_zendesk_url_validation():
    """Test config update with Zendesk URL validation."""
    from aise.config_ui.app import _validate_config_value
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_instance.get = AsyncMock(return_value=mock_response)
        
        error = await _validate_config_value("ZENDESK_URL", "https://mycompany.zendesk.com")
        
        assert error is None


@pytest.mark.asyncio
async def test_config_update_with_invalid_zendesk_url():
    """Test config update with invalid Zendesk URL."""
    from aise.config_ui.app import _validate_config_value
    import httpx
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        mock_instance.get = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
        
        error = await _validate_config_value("ZENDESK_URL", "https://invalid.zendesk.com")
        
        assert error is not None
        assert "connection failed" in error.lower()


@pytest.mark.asyncio
async def test_config_update_with_freshdesk_url_validation():
    """Test config update with Freshdesk URL validation."""
    from aise.config_ui.app import _validate_config_value
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_instance.get = AsyncMock(return_value=mock_response)
        
        error = await _validate_config_value("FRESHDESK_URL", "https://mycompany.freshdesk.com")
        
        assert error is None


@pytest.mark.asyncio
async def test_config_update_with_custom_support_url_validation():
    """Test config update with custom support URL validation."""
    from aise.config_ui.app import _validate_config_value
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_instance.get = AsyncMock(return_value=mock_response)
        
        error = await _validate_config_value("CUSTOM_SUPPORT_URL", "https://support.mycompany.com")
        
        assert error is None


@pytest.mark.asyncio
async def test_config_update_with_404_url():
    """Test config update with URL that returns 404."""
    from aise.config_ui.app import _validate_config_value
    
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_instance.get = AsyncMock(return_value=mock_response)
        
        error = await _validate_config_value("CUSTOM_SUPPORT_URL", "https://example.com/notfound")
        
        assert error is not None
        assert "404" in error


@pytest.mark.asyncio
async def test_config_update_with_empty_url():
    """Test config update with empty URL (should skip validation)."""
    from aise.config_ui.app import _validate_config_value
    
    # Empty URLs should not trigger validation
    error = await _validate_config_value("ZENDESK_URL", "")
    
    assert error is None
