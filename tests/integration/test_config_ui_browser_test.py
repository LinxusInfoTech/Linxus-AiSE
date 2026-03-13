# tests/integration/test_config_ui_browser_test.py
"""Integration tests for Config UI browser URL testing functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from fastapi.testclient import TestClient


@pytest.fixture
def mock_config_browser_enabled():
    """Mock config with browser fallback enabled."""
    config = Mock()
    config.USE_BROWSER_FALLBACK = True
    config.BROWSER_HEADLESS = True
    return config


@pytest.fixture
def mock_config_browser_disabled():
    """Mock config with browser fallback disabled."""
    config = Mock()
    config.USE_BROWSER_FALLBACK = False
    config.BROWSER_HEADLESS = True
    return config


class TestBrowserURLTesting:
    """Tests for browser URL testing endpoint."""
    
    def test_browser_url_test_success(self, mock_config_browser_enabled):
        """Test successful browser navigation."""
        from aise.config_ui.app import app
        
        # Mock Playwright
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status = 200
        
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(return_value=mock_response)
        mock_page.title = AsyncMock(return_value="Test Page")
        mock_page.set_default_timeout = MagicMock()
        
        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()
        
        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)
        
        mock_playwright = MagicMock()
        mock_playwright.chromium = mock_chromium
        
        with patch("aise.config_ui.app.load_config", return_value=mock_config_browser_enabled):
            with patch("playwright.async_api.async_playwright") as mock_pw:
                mock_pw.return_value.__aenter__.return_value = mock_playwright
                
                client = TestClient(app)
                response = client.post(
                    "/api/test-browser-url",
                    json={
                        "url": "https://example.zendesk.com",
                        "platform": "zendesk"
                    }
                )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Successfully navigated" in data["message"]
        assert data["details"]["url"] == "https://example.zendesk.com"
        assert data["details"]["platform"] == "zendesk"
        assert data["details"]["status_code"] == 200
        assert data["details"]["page_title"] == "Test Page"
        assert data["details"]["browser_fallback_enabled"] is True
    
    def test_browser_url_test_navigation_failed(self, mock_config_browser_enabled):
        """Test browser navigation with failed response."""
        from aise.config_ui.app import app
        
        # Mock Playwright with failed response
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status = 404
        
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(return_value=mock_response)
        mock_page.set_default_timeout = MagicMock()
        
        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()
        
        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)
        
        mock_playwright = MagicMock()
        mock_playwright.chromium = mock_chromium
        
        with patch("aise.config_ui.app.load_config", return_value=mock_config_browser_enabled):
            with patch("playwright.async_api.async_playwright") as mock_pw:
                mock_pw.return_value.__aenter__.return_value = mock_playwright
                
                client = TestClient(app)
                response = client.post(
                    "/api/test-browser-url",
                    json={
                        "url": "https://example.zendesk.com/notfound",
                        "platform": "zendesk"
                    }
                )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Navigation failed" in data["message"]
        assert data["details"]["status_code"] == 404
    
    def test_browser_url_test_browser_disabled(self, mock_config_browser_disabled):
        """Test browser URL test when browser fallback is disabled."""
        from aise.config_ui.app import app
        
        with patch("aise.config_ui.app.load_config", return_value=mock_config_browser_disabled):
            client = TestClient(app)
            response = client.post(
                "/api/test-browser-url",
                json={
                    "url": "https://example.zendesk.com",
                    "platform": "zendesk"
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Browser fallback is disabled" in data["message"]
        assert data["details"]["browser_fallback_enabled"] is False
    
    def test_browser_url_test_missing_url(self, mock_config_browser_enabled):
        """Test browser URL test with missing URL."""
        from aise.config_ui.app import app
        
        with patch("aise.config_ui.app.load_config", return_value=mock_config_browser_enabled):
            client = TestClient(app)
            response = client.post(
                "/api/test-browser-url",
                json={"platform": "zendesk"}
            )
        
        assert response.status_code == 400
        assert "URL is required" in response.json()["detail"]
    
    def test_browser_url_test_dns_error(self, mock_config_browser_enabled):
        """Test browser URL test with DNS resolution error."""
        from aise.config_ui.app import app
        
        # Mock Playwright with DNS error
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(
            side_effect=Exception("net::ERR_NAME_NOT_RESOLVED at https://invalid.example.com")
        )
        mock_page.set_default_timeout = MagicMock()
        
        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()
        
        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)
        
        mock_playwright = MagicMock()
        mock_playwright.chromium = mock_chromium
        
        with patch("aise.config_ui.app.load_config", return_value=mock_config_browser_enabled):
            with patch("playwright.async_api.async_playwright") as mock_pw:
                mock_pw.return_value.__aenter__.return_value = mock_playwright
                
                client = TestClient(app)
                response = client.post(
                    "/api/test-browser-url",
                    json={
                        "url": "https://invalid.example.com",
                        "platform": "custom"
                    }
                )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "DNS resolution failed" in data["message"]
    
    def test_browser_url_test_connection_refused(self, mock_config_browser_enabled):
        """Test browser URL test with connection refused error."""
        from aise.config_ui.app import app
        
        # Mock Playwright with connection refused error
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(
            side_effect=Exception("net::ERR_CONNECTION_REFUSED at https://localhost:9999")
        )
        mock_page.set_default_timeout = MagicMock()
        
        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()
        
        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)
        
        mock_playwright = MagicMock()
        mock_playwright.chromium = mock_chromium
        
        with patch("aise.config_ui.app.load_config", return_value=mock_config_browser_enabled):
            with patch("playwright.async_api.async_playwright") as mock_pw:
                mock_pw.return_value.__aenter__.return_value = mock_playwright
                
                client = TestClient(app)
                response = client.post(
                    "/api/test-browser-url",
                    json={
                        "url": "https://localhost:9999",
                        "platform": "custom"
                    }
                )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Connection refused" in data["message"]
    
    def test_browser_url_test_timeout(self, mock_config_browser_enabled):
        """Test browser URL test with timeout error."""
        from aise.config_ui.app import app
        
        # Mock Playwright with timeout error
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(
            side_effect=Exception("Timeout 10000ms exceeded")
        )
        mock_page.set_default_timeout = MagicMock()
        
        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()
        
        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)
        
        mock_playwright = MagicMock()
        mock_playwright.chromium = mock_chromium
        
        with patch("aise.config_ui.app.load_config", return_value=mock_config_browser_enabled):
            with patch("playwright.async_api.async_playwright") as mock_pw:
                mock_pw.return_value.__aenter__.return_value = mock_playwright
                
                client = TestClient(app)
                response = client.post(
                    "/api/test-browser-url",
                    json={
                        "url": "https://slow.example.com",
                        "platform": "custom"
                    }
                )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Navigation timeout" in data["message"]
    
    def test_browser_url_test_playwright_not_installed(self, mock_config_browser_enabled):
        """Test browser URL test when Playwright is not installed."""
        from aise.config_ui.app import app
        
        with patch("aise.config_ui.app.load_config", return_value=mock_config_browser_enabled):
            # Mock the import to raise ImportError
            import sys
            with patch.dict(sys.modules, {'playwright': None, 'playwright.async_api': None}):
                client = TestClient(app)
                response = client.post(
                    "/api/test-browser-url",
                    json={
                        "url": "https://example.zendesk.com",
                        "platform": "zendesk"
                    }
                )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "Playwright is not installed" in data["message"]
        assert "playwright_not_installed" in data["details"]["error"]
    
    def test_browser_url_test_default_platform(self, mock_config_browser_enabled):
        """Test browser URL test with default platform."""
        from aise.config_ui.app import app
        
        # Mock Playwright
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status = 200
        
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(return_value=mock_response)
        mock_page.title = AsyncMock(return_value="Custom Platform")
        mock_page.set_default_timeout = MagicMock()
        
        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()
        
        mock_chromium = MagicMock()
        mock_chromium.launch = AsyncMock(return_value=mock_browser)
        
        mock_playwright = MagicMock()
        mock_playwright.chromium = mock_chromium
        
        with patch("aise.config_ui.app.load_config", return_value=mock_config_browser_enabled):
            with patch("playwright.async_api.async_playwright") as mock_pw:
                mock_pw.return_value.__aenter__.return_value = mock_playwright
                
                client = TestClient(app)
                response = client.post(
                    "/api/test-browser-url",
                    json={"url": "https://support.example.com"}
                )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["details"]["platform"] == "custom"  # Default platform
