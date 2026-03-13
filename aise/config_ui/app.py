# aise/config_ui/app.py
"""FastAPI application for configuration UI.

This module provides a web-based configuration interface for AiSE,
allowing non-technical users to configure the system without editing
.env files or using CLI commands.

Example usage:
    $ uvicorn aise.config_ui.app:app --host 0.0.0.0 --port 8080
    
    Then visit http://localhost:8080/config in your browser.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import structlog
from pathlib import Path

from aise.core.config import get_config as load_config, Config
from aise.core.exceptions import ConfigurationError, ProviderError
from aise.config_ui.validators import (
    validate_llm_provider,
    validate_postgres_url,
    validate_redis_url,
    validate_zendesk_credentials,
    validate_freshdesk_credentials,
    validate_zendesk_url,
    validate_freshdesk_url,
    validate_custom_support_url,
    get_url_templates
)
from aise.config_ui.persistence import ConfigPersistence

logger = structlog.get_logger(__name__)

# Global persistence instance
_persistence: Optional[ConfigPersistence] = None

# Create FastAPI app
app = FastAPI(
    title="AiSE Configuration UI",
    description="Web-based configuration interface for AI Support Engineer System",
    version="0.1.0"
)


class ConfigUpdate(BaseModel):
    """Configuration update request model."""
    key: str = Field(..., description="Configuration key to update")
    value: str = Field(..., description="New value for the configuration key")


class ConfigResponse(BaseModel):
    """Configuration response model."""
    sections: Dict[str, Dict[str, Any]] = Field(..., description="Configuration organized by section")
    masked: bool = Field(True, description="Whether sensitive values are masked")


@app.get("/")
async def root():
    """Root endpoint - redirect to config UI."""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>AiSE Configuration</title>
        <meta http-equiv="refresh" content="0; url=/config">
    </head>
    <body>
        <p>Redirecting to <a href="/config">configuration page</a>...</p>
    </body>
    </html>
    """)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "aise-config-ui"}


@app.get("/config", response_class=HTMLResponse)
async def config_page():
    """Serve the configuration UI page."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AiSE Configuration</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }
            .header h1 { font-size: 2.5em; margin-bottom: 10px; }
            .header p { opacity: 0.9; font-size: 1.1em; }
            .content { padding: 30px; }
            .section {
                margin-bottom: 30px;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                overflow: hidden;
            }
            .section-header {
                background: #f5f5f5;
                padding: 15px 20px;
                font-weight: 600;
                font-size: 1.2em;
                color: #333;
                border-bottom: 2px solid #667eea;
            }
            .section-content { padding: 20px; }
            .config-item {
                display: grid;
                grid-template-columns: 200px 1fr 100px;
                gap: 15px;
                align-items: center;
                padding: 15px;
                border-bottom: 1px solid #f0f0f0;
            }
            .config-item:last-child { border-bottom: none; }
            .config-label {
                font-weight: 500;
                color: #555;
            }
            .config-value {
                font-family: 'Courier New', monospace;
                padding: 8px 12px;
                background: #f9f9f9;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 0.9em;
            }
            .config-value.masked { color: #999; }
            .btn {
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 0.9em;
                transition: all 0.3s;
            }
            .btn-primary {
                background: #667eea;
                color: white;
            }
            .btn-primary:hover { background: #5568d3; }
            .btn-secondary {
                background: #e0e0e0;
                color: #333;
            }
            .btn-secondary:hover { background: #d0d0d0; }
            .btn-reveal {
                background: #ffc107;
                color: #333;
                padding: 10px 20px;
                margin: 20px 0;
                font-weight: 600;
            }
            .btn-reveal:hover { background: #ffb300; }
            .status {
                padding: 15px;
                margin: 20px 0;
                border-radius: 6px;
                display: none;
            }
            .status.success {
                background: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }
            .status.error {
                background: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }
            .loading {
                text-align: center;
                padding: 40px;
                color: #666;
            }
            .spinner {
                border: 3px solid #f3f3f3;
                border-top: 3px solid #667eea;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 0 auto 20px;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>⚙️ AiSE Configuration</h1>
                <p>Configure your AI Support Engineer System</p>
            </div>
            <div class="content">
                <div id="status" class="status"></div>
                <div style="text-align: center; margin: 20px 0;">
                    <button id="reveal-btn" class="btn btn-reveal" onclick="toggleReveal()">
                        🔒 Show Sensitive Values
                    </button>
                </div>
                <div id="loading" class="loading">
                    <div class="spinner"></div>
                    <p>Loading configuration...</p>
                </div>
                <div id="config-sections" style="display: none;"></div>
            </div>
        </div>

        <script>
            let configData = {};
            let isRevealed = false;

            async function loadConfig() {
                try {
                    const response = await fetch(`/api/config?reveal=${isRevealed}`);
                    const data = await response.json();
                    configData = data;
                    renderConfig(data);
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('config-sections').style.display = 'block';
                } catch (error) {
                    showStatus('Failed to load configuration: ' + error.message, 'error');
                    document.getElementById('loading').style.display = 'none';
                }
            }

            function toggleReveal() {
                isRevealed = !isRevealed;
                const btn = document.getElementById('reveal-btn');
                if (isRevealed) {
                    btn.textContent = '🔓 Hide Sensitive Values';
                    btn.style.background = '#ff5722';
                    btn.style.color = 'white';
                } else {
                    btn.textContent = '🔒 Show Sensitive Values';
                    btn.style.background = '#ffc107';
                    btn.style.color = '#333';
                }
                loadConfig();
            }

            function renderConfig(data) {
                const container = document.getElementById('config-sections');
                container.innerHTML = '';

                for (const [sectionName, sectionData] of Object.entries(data.sections)) {
                    const section = document.createElement('div');
                    section.className = 'section';
                    
                    const header = document.createElement('div');
                    header.className = 'section-header';
                    header.textContent = sectionName;
                    section.appendChild(header);

                    const content = document.createElement('div');
                    content.className = 'section-content';

                    for (const [key, value] of Object.entries(sectionData)) {
                        const item = document.createElement('div');
                        item.className = 'config-item';

                        const label = document.createElement('div');
                        label.className = 'config-label';
                        label.textContent = key;

                        const valueDiv = document.createElement('div');
                        valueDiv.className = 'config-value';
                        if (data.masked && isSensitive(key)) {
                            valueDiv.classList.add('masked');
                            valueDiv.textContent = maskValue(value);
                        } else {
                            valueDiv.textContent = value || '(not set)';
                        }

                        const actions = document.createElement('div');
                        const editBtn = document.createElement('button');
                        editBtn.className = 'btn btn-primary';
                        editBtn.textContent = 'Edit';
                        editBtn.onclick = () => editConfig(key, value);
                        actions.appendChild(editBtn);

                        item.appendChild(label);
                        item.appendChild(valueDiv);
                        item.appendChild(actions);
                        content.appendChild(item);
                    }

                    section.appendChild(content);
                    container.appendChild(section);
                }
            }

            function isSensitive(key) {
                const sensitiveKeys = ['API_KEY', 'PASSWORD', 'SECRET', 'TOKEN', 'CREDENTIAL'];
                return sensitiveKeys.some(k => key.toUpperCase().includes(k));
            }

            function maskValue(value) {
                if (!value || value.length < 8) return '••••••••';
                return value.substring(0, 4) + '••••' + value.substring(value.length - 4);
            }

            function editConfig(key, currentValue) {
                const newValue = prompt(`Enter new value for ${key}:`, currentValue || '');
                if (newValue !== null) {
                    updateConfig(key, newValue);
                }
            }

            async function updateConfig(key, value) {
                try {
                    const response = await fetch('/api/config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ key, value })
                    });
                    
                    if (response.ok) {
                        showStatus(`Successfully updated ${key}`, 'success');
                        loadConfig();
                    } else {
                        const error = await response.json();
                        showStatus(`Failed to update ${key}: ${error.detail}`, 'error');
                    }
                } catch (error) {
                    showStatus('Update failed: ' + error.message, 'error');
                }
            }

            function showStatus(message, type) {
                const status = document.getElementById('status');
                status.textContent = message;
                status.className = `status ${type}`;
                status.style.display = 'block';
                setTimeout(() => {
                    status.style.display = 'none';
                }, 5000);
            }

            // Load config on page load
            loadConfig();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/api/url-templates")
async def get_url_template_list():
    """Get URL templates for common support platforms.
    
    Returns:
        Dictionary of platform names to URL templates
    """
    try:
        templates = get_url_templates()
        
        logger.info("url_templates_retrieved")
        
        return {
            "templates": templates,
            "examples": {
                "zendesk": "https://mycompany.zendesk.com",
                "freshdesk": "https://mycompany.freshdesk.com",
                "custom": "https://support.mycompany.com"
            }
        }
        
    except Exception as e:
        logger.error("url_templates_retrieval_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve URL templates: {str(e)}")


@app.get("/api/config", response_model=ConfigResponse)
async def get_config(reveal: bool = False):
    """Get current configuration organized by section.
    
    Args:
        reveal: If True, show unmasked sensitive values
    
    Returns:
        Configuration organized by section with optional masking
    """
    try:
        config = load_config()
        
        # Organize configuration by section
        sections = {
            "LLM Providers": {
                "LLM_PROVIDER": config.LLM_PROVIDER,
                "ANTHROPIC_API_KEY": config.ANTHROPIC_API_KEY or "",
                "OPENAI_API_KEY": config.OPENAI_API_KEY or "",
                "DEEPSEEK_API_KEY": config.DEEPSEEK_API_KEY or "",
                "OLLAMA_BASE_URL": config.OLLAMA_BASE_URL,
            },
            "Database": {
                "POSTGRES_URL": config.POSTGRES_URL,
                "REDIS_URL": config.REDIS_URL,
                "CHROMA_HOST": config.CHROMA_HOST,
                "CHROMA_PORT": str(config.CHROMA_PORT),
            },
            "Knowledge Engine": {
                "CHROMA_PERSIST_PATH": config.CHROMA_PERSIST_PATH,
                "KNOWLEDGE_CRAWL_MAX_DEPTH": str(config.KNOWLEDGE_CRAWL_MAX_DEPTH),
                "KNOWLEDGE_CHUNK_SIZE": str(config.KNOWLEDGE_CHUNK_SIZE),
                "KNOWLEDGE_MIN_REINIT_HOURS": str(config.KNOWLEDGE_MIN_REINIT_HOURS),
                "EMBEDDING_MODEL": config.EMBEDDING_MODEL,
            },
            "Ticket Systems": {
                "ZENDESK_SUBDOMAIN": config.ZENDESK_SUBDOMAIN or "",
                "ZENDESK_EMAIL": config.ZENDESK_EMAIL or "",
                "ZENDESK_API_TOKEN": config.ZENDESK_API_TOKEN or "",
                "ZENDESK_URL": config.ZENDESK_URL or "",
                "FRESHDESK_DOMAIN": config.FRESHDESK_DOMAIN or "",
                "FRESHDESK_API_KEY": config.FRESHDESK_API_KEY or "",
                "FRESHDESK_URL": config.FRESHDESK_URL or "",
                "CUSTOM_SUPPORT_URL": config.CUSTOM_SUPPORT_URL or "",
            },
            "Operational Mode": {
                "AISE_MODE": config.AISE_MODE,
            }
        }
        
        # Mask sensitive values if not revealing
        if not reveal:
            sections = _mask_sensitive_values(sections)
        
        logger.info("config_retrieved", reveal=reveal)
        
        return ConfigResponse(sections=sections, masked=not reveal)
        
    except Exception as e:
        logger.error("config_retrieval_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve configuration: {str(e)}")


@app.post("/api/test-browser-url")
async def test_browser_url(request: dict):
    """Test browser navigation to a configured URL.
    
    This endpoint tests whether the browser can successfully navigate to a URL
    for browser automation purposes. It's different from URL validation - this
    specifically tests browser compatibility and navigation.
    
    Args:
        request: Dictionary with 'url' and 'platform' keys
            - url: The URL to test
            - platform: Platform type ('zendesk', 'freshdesk', 'custom')
    
    Returns:
        Dictionary with test results including success status and details
    """
    try:
        url = request.get("url")
        platform = request.get("platform", "custom")
        
        if not url:
            raise HTTPException(status_code=400, detail="URL is required")
        
        # Check if browser fallback is enabled
        config = load_config()
        if not config.USE_BROWSER_FALLBACK:
            return {
                "success": False,
                "message": "Browser fallback is disabled. Enable USE_BROWSER_FALLBACK to use browser automation.",
                "details": {
                    "url": url,
                    "platform": platform,
                    "browser_fallback_enabled": False
                }
            }
        
        logger.info("browser_url_test_requested", url=url, platform=platform)
        
        # Test browser navigation
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                # Launch browser in headless mode
                browser = await p.chromium.launch(
                    headless=config.BROWSER_HEADLESS
                )
                
                try:
                    # Create a new page
                    page = await browser.new_page()
                    
                    # Set a reasonable timeout
                    page.set_default_timeout(10000)  # 10 seconds
                    
                    # Attempt to navigate to the URL
                    response = await page.goto(url, wait_until="domcontentloaded")
                    
                    # Check response status
                    if response and response.ok:
                        logger.info(
                            "browser_url_test_success",
                            url=url,
                            status=response.status
                        )
                        
                        # Get page title for additional context
                        title = await page.title()
                        
                        await browser.close()
                        
                        return {
                            "success": True,
                            "message": f"Successfully navigated to {url}",
                            "details": {
                                "url": url,
                                "platform": platform,
                                "status_code": response.status,
                                "page_title": title,
                                "browser_fallback_enabled": True
                            }
                        }
                    else:
                        status_code = response.status if response else "unknown"
                        logger.warning(
                            "browser_url_test_failed",
                            url=url,
                            status=status_code
                        )
                        
                        await browser.close()
                        
                        return {
                            "success": False,
                            "message": f"Navigation failed with status {status_code}",
                            "details": {
                                "url": url,
                                "platform": platform,
                                "status_code": status_code,
                                "browser_fallback_enabled": True
                            }
                        }
                        
                except Exception as nav_error:
                    await browser.close()
                    raise nav_error
                    
        except ImportError:
            logger.error("playwright_not_installed")
            return {
                "success": False,
                "message": "Playwright is not installed. Install it with: pip install playwright && playwright install chromium",
                "details": {
                    "url": url,
                    "platform": platform,
                    "error": "playwright_not_installed"
                }
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error("browser_url_test_error", url=url, error=error_msg)
            
            # Provide more specific error messages
            if "net::ERR_NAME_NOT_RESOLVED" in error_msg:
                message = "DNS resolution failed. The domain name could not be found."
            elif "net::ERR_CONNECTION_REFUSED" in error_msg:
                message = "Connection refused. The server is not accepting connections."
            elif "net::ERR_CONNECTION_TIMED_OUT" in error_msg:
                message = "Connection timed out. The server did not respond in time."
            elif "Timeout" in error_msg:
                message = "Navigation timeout. The page took too long to load."
            else:
                message = f"Browser navigation failed: {error_msg}"
            
            return {
                "success": False,
                "message": message,
                "details": {
                    "url": url,
                    "platform": platform,
                    "error": error_msg,
                    "browser_fallback_enabled": True
                }
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("browser_url_test_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to test browser URL: {str(e)}"
        )


@app.post("/api/config")
async def update_config(update: ConfigUpdate):
    """Update a configuration value.
    
    Args:
        update: Configuration update request
    
    Returns:
        Success message
    """
    try:
        logger.info(
            "config_update_requested",
            key=update.key,
            value_length=len(update.value)
        )
        
        # Validate the key exists
        config = load_config()
        if not hasattr(config, update.key):
            raise HTTPException(
                status_code=400,
                detail=f"Unknown configuration key: {update.key}"
            )
        
        # Validate the value based on key type
        validation_error = await _validate_config_value(update.key, update.value)
        if validation_error:
            raise HTTPException(
                status_code=400,
                detail=validation_error
            )
        
        # Persist to database
        global _persistence
        if not _persistence:
            # Initialize persistence if not already done
            from aise.core.credential_storage import CredentialStorage
            from aise.core.credential_vault import CredentialVault
            
            vault = CredentialVault(config)
            credential_storage = CredentialStorage(config, vault)
            await credential_storage.initialize()
            
            _persistence = ConfigPersistence(config, credential_storage)
            await _persistence.initialize()
        
        # Update configuration
        await _persistence.update_config(update.key, update.value, component="config_ui")
        
        logger.info("config_update_success", key=update.key)
        
        return {
            "message": f"Configuration updated: {update.key}",
            "success": True,
            "applied_without_restart": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("config_update_failed", key=update.key, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update configuration: {str(e)}")


async def _validate_config_value(key: str, value: str) -> Optional[str]:
    """Validate a configuration value before saving.
    
    Args:
        key: Configuration key
        value: Value to validate
    
    Returns:
        Error message if validation fails, None if valid
    """
    try:
        # LLM Provider API Keys
        if key == "ANTHROPIC_API_KEY":
            is_valid, error = await validate_llm_provider("anthropic", value)
            return error if not is_valid else None
        
        elif key == "OPENAI_API_KEY":
            is_valid, error = await validate_llm_provider("openai", value)
            return error if not is_valid else None
        
        elif key == "DEEPSEEK_API_KEY":
            is_valid, error = await validate_llm_provider("deepseek", value)
            return error if not is_valid else None
        
        # Database URLs
        elif key == "POSTGRES_URL" or key == "DATABASE_URL":
            is_valid, error = await validate_postgres_url(value)
            return error if not is_valid else None
        
        elif key == "REDIS_URL":
            is_valid, error = await validate_redis_url(value)
            return error if not is_valid else None
        
        # Zendesk credentials - need all three values
        elif key in ["ZENDESK_SUBDOMAIN", "ZENDESK_EMAIL", "ZENDESK_API_TOKEN"]:
            # Get current config to check if we have all required values
            config = load_config()
            subdomain = value if key == "ZENDESK_SUBDOMAIN" else config.ZENDESK_SUBDOMAIN
            email = value if key == "ZENDESK_EMAIL" else config.ZENDESK_EMAIL
            api_token = value if key == "ZENDESK_API_TOKEN" else config.ZENDESK_API_TOKEN
            
            if subdomain and email and api_token:
                is_valid, error = await validate_zendesk_credentials(subdomain, email, api_token)
                return error if not is_valid else None
        
        # Freshdesk credentials
        elif key in ["FRESHDESK_DOMAIN", "FRESHDESK_API_KEY"]:
            config = load_config()
            domain = value if key == "FRESHDESK_DOMAIN" else config.FRESHDESK_DOMAIN
            api_key = value if key == "FRESHDESK_API_KEY" else config.FRESHDESK_API_KEY
            
            if domain and api_key:
                is_valid, error = await validate_freshdesk_credentials(domain, api_key)
                return error if not is_valid else None
        
        # URL validation for browser targets
        elif key == "ZENDESK_URL":
            if value:  # Only validate if value is provided
                is_valid, error = await validate_zendesk_url(value)
                return error if not is_valid else None
        
        elif key == "FRESHDESK_URL":
            if value:  # Only validate if value is provided
                is_valid, error = await validate_freshdesk_url(value)
                return error if not is_valid else None
        
        elif key == "CUSTOM_SUPPORT_URL":
            if value:  # Only validate if value is provided
                is_valid, error = await validate_custom_support_url(value)
                return error if not is_valid else None
        
        # No specific validation needed for other keys
        return None
        
    except Exception as e:
        logger.error("config_validation_error", key=key, error=str(e))
        return f"Validation error: {str(e)}"


def _mask_sensitive_values(sections: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """Mask sensitive configuration values.
    
    Args:
        sections: Configuration sections
    
    Returns:
        Sections with masked sensitive values
    """
    sensitive_keys = ["API_KEY", "PASSWORD", "SECRET", "TOKEN", "CREDENTIAL", "KEY"]
    
    masked_sections = {}
    for section_name, section_data in sections.items():
        masked_section = {}
        for key, value in section_data.items():
            # Check if key contains sensitive keywords
            is_sensitive = any(sensitive in key.upper() for sensitive in sensitive_keys)
            
            if is_sensitive and value:
                # Mask: show first 4 and last 4 characters
                if len(value) > 8:
                    masked_section[key] = f"{value[:4]}••••{value[-4:]}"
                else:
                    masked_section[key] = "••••••••"
            else:
                masked_section[key] = value
        
        masked_sections[section_name] = masked_section
    
    return masked_sections
