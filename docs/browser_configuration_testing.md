# Browser Configuration Testing

## Overview

The browser configuration testing feature allows administrators to verify that configured support platform URLs are accessible for browser automation before saving them. This is particularly useful when setting up browser fallback functionality for ticket system integrations.

## Purpose

This feature addresses Requirement 5.8: "WHEN a user tests browser configuration THEN THE System SHALL attempt to navigate to the URL and report success or failure."

Unlike URL validation (which checks HTTP accessibility), browser configuration testing specifically verifies that:
1. The URL can be loaded in a browser automation context (Playwright)
2. The page renders successfully
3. The browser can interact with the page

## API Endpoint

### POST /api/test-browser-url

Tests whether a browser can successfully navigate to a configured URL.

**Request Body:**
```json
{
  "url": "https://example.zendesk.com",
  "platform": "zendesk"
}
```

**Parameters:**
- `url` (required): The URL to test
- `platform` (optional): Platform type - one of `zendesk`, `freshdesk`, or `custom`. Defaults to `custom`.

**Response (Success):**
```json
{
  "success": true,
  "message": "Successfully navigated to https://example.zendesk.com",
  "details": {
    "url": "https://example.zendesk.com",
    "platform": "zendesk",
    "status_code": 200,
    "page_title": "Zendesk Support",
    "browser_fallback_enabled": true
  }
}
```

**Response (Failure):**
```json
{
  "success": false,
  "message": "DNS resolution failed. The domain name could not be found.",
  "details": {
    "url": "https://invalid.example.com",
    "platform": "custom",
    "error": "net::ERR_NAME_NOT_RESOLVED at https://invalid.example.com",
    "browser_fallback_enabled": true
  }
}
```

**Response (Browser Fallback Disabled):**
```json
{
  "success": false,
  "message": "Browser fallback is disabled. Enable USE_BROWSER_FALLBACK to use browser automation.",
  "details": {
    "url": "https://example.zendesk.com",
    "platform": "zendesk",
    "browser_fallback_enabled": false
  }
}
```

## Configuration Requirements

### USE_BROWSER_FALLBACK

The browser configuration test endpoint only functions when `USE_BROWSER_FALLBACK=true` in the system configuration. This aligns with Requirement 5.10: "WHEN browser fallback is disabled THEN THE System SHALL not require browser target URL configuration."

To enable browser fallback:

```bash
# In .env file
USE_BROWSER_FALLBACK=true
BROWSER_HEADLESS=true  # Optional, defaults to true
```

### Playwright Installation

Browser testing requires Playwright to be installed:

```bash
pip install playwright
playwright install chromium
```

If Playwright is not installed, the endpoint will return:
```json
{
  "success": false,
  "message": "Playwright is not installed. Install it with: pip install playwright && playwright install chromium",
  "details": {
    "url": "https://example.zendesk.com",
    "platform": "zendesk",
    "error": "playwright_not_installed"
  }
}
```

## Error Handling

The endpoint provides specific error messages for common issues:

### DNS Resolution Failure
```
"DNS resolution failed. The domain name could not be found."
```
Occurs when the domain name cannot be resolved.

### Connection Refused
```
"Connection refused. The server is not accepting connections."
```
Occurs when the server actively refuses the connection.

### Connection Timeout
```
"Connection timed out. The server did not respond in time."
```
Occurs when the server doesn't respond within the timeout period.

### Navigation Timeout
```
"Navigation timeout. The page took too long to load."
```
Occurs when the page takes longer than 10 seconds to load.

### HTTP Error
```
"Navigation failed with status 404"
```
Occurs when the server returns a non-2xx status code.

## Usage Example

### Using curl

```bash
# Test Zendesk URL
curl -X POST http://localhost:8080/api/test-browser-url \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://mycompany.zendesk.com",
    "platform": "zendesk"
  }'

# Test Freshdesk URL
curl -X POST http://localhost:8080/api/test-browser-url \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://mycompany.freshdesk.com",
    "platform": "freshdesk"
  }'

# Test custom support URL
curl -X POST http://localhost:8080/api/test-browser-url \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://support.mycompany.com",
    "platform": "custom"
  }'
```

### Using Python

```python
import requests

response = requests.post(
    "http://localhost:8080/api/test-browser-url",
    json={
        "url": "https://mycompany.zendesk.com",
        "platform": "zendesk"
    }
)

result = response.json()
if result["success"]:
    print(f"✓ Browser can navigate to {result['details']['url']}")
    print(f"  Page title: {result['details']['page_title']}")
    print(f"  Status code: {result['details']['status_code']}")
else:
    print(f"✗ Browser navigation failed: {result['message']}")
```

## Implementation Details

### Browser Configuration

The test uses the following browser settings:
- **Browser**: Chromium (via Playwright)
- **Headless mode**: Controlled by `BROWSER_HEADLESS` config (default: true)
- **Timeout**: 10 seconds for page load
- **Wait strategy**: `domcontentloaded` - waits for DOM to be fully loaded

### Security Considerations

1. **Timeout Protection**: All browser operations have a 10-second timeout to prevent hanging
2. **Resource Cleanup**: Browser instances are properly closed after each test
3. **Error Isolation**: Exceptions are caught and converted to user-friendly messages
4. **No Credentials**: The test only navigates to the URL; it doesn't attempt authentication

### Performance

- Each test launches a new browser instance
- Browser instances are closed immediately after testing
- Tests typically complete in 2-5 seconds for accessible URLs
- Failed tests (DNS errors, timeouts) may take up to 10 seconds

## Differences from URL Validation

| Feature | URL Validation | Browser Configuration Test |
|---------|---------------|---------------------------|
| Method | HTTP GET request | Browser navigation |
| Purpose | Check HTTP accessibility | Verify browser compatibility |
| Requirements | None | Playwright + USE_BROWSER_FALLBACK |
| Speed | Fast (< 1 second) | Slower (2-10 seconds) |
| JavaScript | Not executed | Fully executed |
| Use Case | Basic connectivity | Browser automation readiness |

## Troubleshooting

### Test Always Fails with "Browser fallback is disabled"

**Solution**: Enable browser fallback in configuration:
```bash
USE_BROWSER_FALLBACK=true
```

### Test Fails with "Playwright is not installed"

**Solution**: Install Playwright:
```bash
pip install playwright
playwright install chromium
```

### Test Times Out on Valid URLs

**Possible causes**:
1. Slow network connection
2. Page has heavy JavaScript that takes time to load
3. Page requires authentication and redirects

**Solution**: This is expected behavior. The test verifies the URL is accessible, but some pages may take longer than the 10-second timeout.

### Test Succeeds but Browser Automation Still Fails

**Possible causes**:
1. Page structure changed after testing
2. Authentication required for actual operations
3. Rate limiting or bot detection

**Solution**: The test only verifies basic navigation. Actual browser automation may require additional configuration (credentials, selectors, etc.).

## Related Documentation

- [URL Validation](./url_validation.md) - HTTP-based URL validation
- [Configuration](./configuration.md) - System configuration options
- [Browser Automation](./architecture.md#browser-automation-layer) - Full browser automation architecture

## Requirements Satisfied

This feature satisfies the following requirements:

- **5.4**: Browser_Agent uses configured target URL
- **5.8**: System attempts to navigate to URL and reports success/failure
- **5.10**: Browser target URL configuration only required when USE_BROWSER_FALLBACK=true
