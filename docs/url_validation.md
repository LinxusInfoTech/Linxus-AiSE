# URL Validation in Config UI

## Overview

The Config UI now includes URL validation for browser target URLs. This ensures that configured support platform URLs are accessible before saving them to the configuration.

## Features

### 1. URL Accessibility Validation (Requirement 5.5)

When configuring browser target URLs, the system validates that the URLs are accessible via HTTP GET request:

- **ZENDESK_URL**: Validates Zendesk instance URLs
- **FRESHDESK_URL**: Validates Freshdesk instance URLs  
- **CUSTOM_SUPPORT_URL**: Validates custom support platform URLs

The validation accepts:
- 2xx status codes (success)
- 3xx status codes (redirects)
- 401/403 status codes (authentication required - indicates URL exists)

The validation rejects:
- 404 status codes (not found)
- Connection timeouts
- DNS resolution failures
- SSL/TLS errors

### 2. Diagnostic Error Messages (Requirement 5.6)

When URL validation fails, the Config UI displays specific error messages with diagnostic information:

- **404 Not Found**: "URL not found (404). Please check the URL is correct."
- **Connection Timeout**: "Connection timeout. The server at {url} did not respond in time."
- **Connection Failed**: "Connection failed. Could not connect to {url}. Check the URL and network connectivity."
- **DNS Failure**: "DNS resolution failed. The domain name could not be found. Check the URL spelling."
- **SSL Error**: "SSL/TLS error. The server's security certificate may be invalid."

### 3. URL Templates (Requirement 5.9)

The Config UI provides URL templates for common platforms:

```python
{
    "zendesk": "https://{subdomain}.zendesk.com",
    "freshdesk": "https://{domain}.freshdesk.com",
    "custom": "{url}"
}
```

Access templates via the API endpoint:
```bash
GET /api/url-templates
```

Response:
```json
{
    "templates": {
        "zendesk": "https://{subdomain}.zendesk.com",
        "freshdesk": "https://{domain}.freshdesk.com",
        "custom": "{url}"
    },
    "examples": {
        "zendesk": "https://mycompany.zendesk.com",
        "freshdesk": "https://mycompany.freshdesk.com",
        "custom": "https://support.mycompany.com"
    }
}
```

## API Usage

### Validate Zendesk URL

```python
from aise.config_ui.validators import validate_zendesk_url

is_valid, error = await validate_zendesk_url("mycompany")
# or
is_valid, error = await validate_zendesk_url("https://mycompany.zendesk.com")
```

### Validate Freshdesk URL

```python
from aise.config_ui.validators import validate_freshdesk_url

is_valid, error = await validate_freshdesk_url("mycompany")
# or
is_valid, error = await validate_freshdesk_url("https://mycompany.freshdesk.com")
```

### Validate Custom Support URL

```python
from aise.config_ui.validators import validate_custom_support_url

is_valid, error = await validate_custom_support_url("https://support.mycompany.com")
```

### Generic URL Validation

```python
from aise.config_ui.validators import validate_url_accessible

is_valid, error = await validate_url_accessible("https://example.com")
```

## Configuration

### Via Config UI

1. Navigate to http://localhost:8080/config
2. Find the "Ticket Systems" section
3. Enter URL values for:
   - ZENDESK_URL
   - FRESHDESK_URL
   - CUSTOM_SUPPORT_URL
4. Click "Edit" to save
5. The system will validate the URL before saving
6. If validation fails, an error message with diagnostic information will be displayed

### Via Environment Variables

```bash
export ZENDESK_URL="https://mycompany.zendesk.com"
export FRESHDESK_URL="https://mycompany.freshdesk.com"
export CUSTOM_SUPPORT_URL="https://support.mycompany.com"
```

### Via .env File

```env
ZENDESK_URL=https://mycompany.zendesk.com
FRESHDESK_URL=https://mycompany.freshdesk.com
CUSTOM_SUPPORT_URL=https://support.mycompany.com
```

## Error Handling

The URL validation is non-blocking for empty values. If a URL field is left empty, no validation is performed. This allows users to configure only the platforms they use.

Example:
```python
# Empty URL - no validation performed
error = await _validate_config_value("ZENDESK_URL", "")
assert error is None

# Invalid URL - validation performed and fails
error = await _validate_config_value("ZENDESK_URL", "https://invalid.zendesk.com")
assert error is not None
```

## Testing

### Unit Tests

Run unit tests for URL validation:
```bash
poetry run pytest tests/unit/test_config_validators.py -v
```

### Integration Tests

Run integration tests for Config UI URL validation:
```bash
poetry run pytest tests/integration/test_config_ui_url_validation.py -v
```

### All Tests

Run all validator tests:
```bash
poetry run pytest tests/unit/test_config_validators.py tests/integration/test_config_ui_url_validation.py -v
```

## Implementation Details

### Validators Module

The `aise/config_ui/validators.py` module provides:

- `validate_url_accessible(url)`: Generic URL accessibility validation
- `validate_zendesk_url(subdomain)`: Zendesk-specific URL validation
- `validate_freshdesk_url(domain)`: Freshdesk-specific URL validation
- `validate_custom_support_url(url)`: Custom platform URL validation
- `get_url_templates()`: Get URL templates for common platforms

### Config UI Integration

The `aise/config_ui/app.py` module integrates URL validation:

- Added ZENDESK_URL, FRESHDESK_URL, CUSTOM_SUPPORT_URL to config sections
- Added URL validation in `_validate_config_value()` function
- Added `/api/url-templates` endpoint for retrieving URL templates
- Validation is performed before saving configuration changes

### Error Messages

All error messages follow a consistent format:
1. Clear description of the problem
2. Specific diagnostic information (status code, error type)
3. Actionable remediation guidance

Example:
```
"Connection failed. Could not connect to https://example.com. Check the URL and network connectivity."
```

## Future Enhancements

Potential future improvements:
- Browser-based URL testing (navigate to URL and verify page loads)
- URL reachability monitoring (periodic health checks)
- URL history tracking (track URL changes over time)
- Bulk URL validation (validate multiple URLs at once)
