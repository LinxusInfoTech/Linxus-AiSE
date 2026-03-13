# tests/unit/test_exceptions.py
"""Unit tests for custom exception hierarchy."""

import pytest
from aise.core.exceptions import (
    AiSEException,
    ToolExecutionError,
    ForbiddenCommandError,
    ToolExecutionTimeout,
    ProviderError,
    ProviderUnavailableError,
    AllProvidersFailedError,
    TicketAPIError,
    TicketNotFoundError,
    VectorStoreError,
    BrowserError,
    ConfigurationError,
    CredentialVaultError,
    ValidationError,
)


class TestAiSEException:
    """Tests for base AiSEException class."""
    
    def test_basic_exception(self):
        """Test basic exception creation with message only."""
        exc = AiSEException("Test error")
        assert str(exc) == "Test error"
        assert exc.message == "Test error"
        assert exc.context == {}
    
    def test_exception_with_context(self):
        """Test exception with context dictionary."""
        exc = AiSEException("Test error", context={"key": "value", "count": 42})
        assert "Test error" in str(exc)
        assert "key=value" in str(exc)
        assert "count=42" in str(exc)
        assert exc.context == {"key": "value", "count": 42}
    
    def test_exception_inheritance(self):
        """Test that AiSEException inherits from Exception."""
        exc = AiSEException("Test error")
        assert isinstance(exc, Exception)
    
    def test_catch_all_aise_exceptions(self):
        """Test that all custom exceptions can be caught as AiSEException."""
        exceptions = [
            ForbiddenCommandError("test"),
            ToolExecutionTimeout("test", 30),
            ProviderUnavailableError("anthropic"),
            TicketNotFoundError("123"),
            VectorStoreError("test"),
            BrowserError("test"),
            ConfigurationError("test"),
            CredentialVaultError("test"),
            ValidationError("test"),
        ]
        
        for exc in exceptions:
            assert isinstance(exc, AiSEException)


class TestToolExecutionExceptions:
    """Tests for tool execution related exceptions."""
    
    def test_tool_execution_error_basic(self):
        """Test basic ToolExecutionError."""
        exc = ToolExecutionError("Command failed")
        assert str(exc) == "Command failed"
        assert exc.command is None
        assert exc.exit_code is None
    
    def test_tool_execution_error_with_details(self):
        """Test ToolExecutionError with full details."""
        exc = ToolExecutionError(
            "Command failed",
            command="aws ec2 describe-instances",
            exit_code=1,
            stdout="some output",
            stderr="error message"
        )
        assert "Command failed" in str(exc)
        assert "aws ec2 describe-instances" in str(exc)
        assert exc.command == "aws ec2 describe-instances"
        assert exc.exit_code == 1
        assert exc.stdout == "some output"
        assert exc.stderr == "error message"
    
    def test_tool_execution_error_truncates_output(self):
        """Test that stdout/stderr are truncated in context."""
        long_output = "x" * 500
        exc = ToolExecutionError(
            "Command failed",
            command="test",
            stdout=long_output,
            stderr=long_output
        )
        # Full output stored in attributes
        assert len(exc.stdout) == 500
        assert len(exc.stderr) == 500
        # But truncated in context for logging
        assert len(exc.context['stdout']) == 200
        assert len(exc.context['stderr']) == 200
    
    def test_forbidden_command_error(self):
        """Test ForbiddenCommandError."""
        exc = ForbiddenCommandError("rm -rf /")
        assert "Command not allowed" in str(exc)
        assert "rm -rf /" in str(exc)
        assert exc.command == "rm -rf /"
        assert exc.reason is None
    
    def test_forbidden_command_error_with_reason(self):
        """Test ForbiddenCommandError with reason."""
        exc = ForbiddenCommandError("rm -rf /", reason="Dangerous command")
        assert "Command not allowed" in str(exc)
        assert "rm -rf /" in str(exc)
        assert "Dangerous command" in str(exc)
        assert exc.reason == "Dangerous command"
    
    def test_forbidden_command_inherits_tool_execution_error(self):
        """Test that ForbiddenCommandError inherits from ToolExecutionError."""
        exc = ForbiddenCommandError("test")
        assert isinstance(exc, ToolExecutionError)
        assert isinstance(exc, AiSEException)
    
    def test_tool_execution_timeout(self):
        """Test ToolExecutionTimeout."""
        exc = ToolExecutionTimeout("sleep 60", timeout=30)
        assert "timed out" in str(exc).lower()
        assert "30s" in str(exc)
        assert "sleep 60" in str(exc)
        assert exc.command == "sleep 60"
        assert exc.timeout == 30
    
    def test_tool_execution_timeout_inherits_tool_execution_error(self):
        """Test that ToolExecutionTimeout inherits from ToolExecutionError."""
        exc = ToolExecutionTimeout("test", 30)
        assert isinstance(exc, ToolExecutionError)
        assert isinstance(exc, AiSEException)


class TestProviderExceptions:
    """Tests for LLM provider related exceptions."""
    
    def test_provider_error_basic(self):
        """Test basic ProviderError."""
        exc = ProviderError("API call failed")
        assert str(exc) == "API call failed"
        assert exc.provider is None
        assert exc.status_code is None
        assert exc.retry_after is None
    
    def test_provider_error_with_details(self):
        """Test ProviderError with full details."""
        exc = ProviderError(
            "API call failed",
            provider="anthropic",
            status_code=429,
            retry_after=60
        )
        assert "API call failed" in str(exc)
        assert "anthropic" in str(exc)
        assert exc.provider == "anthropic"
        assert exc.status_code == 429
        assert exc.retry_after == 60
    
    def test_provider_unavailable_error(self):
        """Test ProviderUnavailableError."""
        exc = ProviderUnavailableError("anthropic")
        assert "Provider anthropic unavailable" in str(exc)
        assert exc.provider == "anthropic"
        assert exc.reason is None
    
    def test_provider_unavailable_error_with_reason(self):
        """Test ProviderUnavailableError with reason."""
        exc = ProviderUnavailableError(
            "anthropic",
            reason="Connection timeout",
            retry_after=120
        )
        assert "Provider anthropic unavailable" in str(exc)
        assert "Connection timeout" in str(exc)
        assert exc.reason == "Connection timeout"
        assert exc.retry_after == 120
    
    def test_provider_unavailable_inherits_provider_error(self):
        """Test that ProviderUnavailableError inherits from ProviderError."""
        exc = ProviderUnavailableError("anthropic")
        assert isinstance(exc, ProviderError)
        assert isinstance(exc, AiSEException)
    
    def test_all_providers_failed_error(self):
        """Test AllProvidersFailedError."""
        exc = AllProvidersFailedError()
        assert "No LLM providers available" in str(exc)
        assert exc.failed_providers == []
    
    def test_all_providers_failed_error_with_list(self):
        """Test AllProvidersFailedError with failed providers list."""
        exc = AllProvidersFailedError(
            "All providers failed",
            failed_providers=["anthropic", "openai", "deepseek"]
        )
        assert "All providers failed" in str(exc)
        assert exc.failed_providers == ["anthropic", "openai", "deepseek"]
    
    def test_all_providers_failed_inherits_provider_error(self):
        """Test that AllProvidersFailedError inherits from ProviderError."""
        exc = AllProvidersFailedError()
        assert isinstance(exc, ProviderError)
        assert isinstance(exc, AiSEException)


class TestTicketExceptions:
    """Tests for ticket system related exceptions."""
    
    def test_ticket_api_error_basic(self):
        """Test basic TicketAPIError."""
        exc = TicketAPIError("API call failed")
        assert str(exc) == "API call failed"
        assert exc.provider is None
        assert exc.status_code is None
        assert exc.ticket_id is None
    
    def test_ticket_api_error_with_details(self):
        """Test TicketAPIError with full details."""
        exc = TicketAPIError(
            "API call failed",
            provider="zendesk",
            status_code=500,
            ticket_id="12345"
        )
        assert "API call failed" in str(exc)
        assert "zendesk" in str(exc)
        assert exc.provider == "zendesk"
        assert exc.status_code == 500
        assert exc.ticket_id == "12345"
    
    def test_ticket_not_found_error(self):
        """Test TicketNotFoundError."""
        exc = TicketNotFoundError("12345")
        assert "Ticket not found" in str(exc)
        assert "12345" in str(exc)
        assert exc.ticket_id == "12345"
        assert exc.provider is None
    
    def test_ticket_not_found_error_with_provider(self):
        """Test TicketNotFoundError with provider."""
        exc = TicketNotFoundError("12345", provider="zendesk")
        assert "Ticket not found" in str(exc)
        assert "12345" in str(exc)
        assert exc.ticket_id == "12345"
        assert exc.provider == "zendesk"
    
    def test_ticket_not_found_inherits_ticket_api_error(self):
        """Test that TicketNotFoundError inherits from TicketAPIError."""
        exc = TicketNotFoundError("12345")
        assert isinstance(exc, TicketAPIError)
        assert isinstance(exc, AiSEException)


class TestKnowledgeEngineExceptions:
    """Tests for knowledge engine related exceptions."""
    
    def test_vector_store_error_basic(self):
        """Test basic VectorStoreError."""
        exc = VectorStoreError("ChromaDB connection failed")
        assert "ChromaDB connection failed" in str(exc)
        assert exc.operation is None
    
    def test_vector_store_error_with_operation(self):
        """Test VectorStoreError with operation."""
        exc = VectorStoreError("Search failed", operation="search")
        assert "Search failed" in str(exc)
        assert "search" in str(exc)
        assert exc.operation == "search"
    
    def test_vector_store_error_inherits_aise_exception(self):
        """Test that VectorStoreError inherits from AiSEException."""
        exc = VectorStoreError("test")
        assert isinstance(exc, AiSEException)


class TestBrowserExceptions:
    """Tests for browser automation related exceptions."""
    
    def test_browser_error_basic(self):
        """Test basic BrowserError."""
        exc = BrowserError("Browser action failed")
        assert "Browser action failed" in str(exc)
        assert exc.action is None
        assert exc.url is None
        assert exc.selector is None
    
    def test_browser_error_with_details(self):
        """Test BrowserError with full details."""
        exc = BrowserError(
            "Click failed",
            action="click",
            url="https://example.com",
            selector="#submit-button"
        )
        assert "Click failed" in str(exc)
        assert "click" in str(exc)
        assert exc.action == "click"
        assert exc.url == "https://example.com"
        assert exc.selector == "#submit-button"
    
    def test_browser_error_inherits_aise_exception(self):
        """Test that BrowserError inherits from AiSEException."""
        exc = BrowserError("test")
        assert isinstance(exc, AiSEException)


class TestConfigurationExceptions:
    """Tests for configuration related exceptions."""
    
    def test_configuration_error_basic(self):
        """Test basic ConfigurationError."""
        exc = ConfigurationError("Invalid configuration")
        assert "Invalid configuration" in str(exc)
        assert exc.field is None
        assert exc.value is None
    
    def test_configuration_error_with_field(self):
        """Test ConfigurationError with field."""
        exc = ConfigurationError(
            "Missing required field",
            field="ANTHROPIC_API_KEY"
        )
        assert "Missing required field" in str(exc)
        assert "ANTHROPIC_API_KEY" in str(exc)
        assert exc.field == "ANTHROPIC_API_KEY"
    
    def test_configuration_error_with_field_and_value(self):
        """Test ConfigurationError with field and value."""
        exc = ConfigurationError(
            "Invalid value",
            field="LLM_PROVIDER",
            value="invalid_provider"
        )
        assert "Invalid value" in str(exc)
        assert "LLM_PROVIDER" in str(exc)
        assert exc.field == "LLM_PROVIDER"
        assert exc.value == "invalid_provider"
    
    def test_configuration_error_inherits_aise_exception(self):
        """Test that ConfigurationError inherits from AiSEException."""
        exc = ConfigurationError("test")
        assert isinstance(exc, AiSEException)


class TestCredentialVaultExceptions:
    """Tests for credential vault related exceptions."""
    
    def test_credential_vault_error_basic(self):
        """Test basic CredentialVaultError."""
        exc = CredentialVaultError("Encryption failed")
        assert "Encryption failed" in str(exc)
        assert exc.operation is None
    
    def test_credential_vault_error_with_operation(self):
        """Test CredentialVaultError with operation."""
        exc = CredentialVaultError("Decryption failed", operation="decrypt")
        assert "Decryption failed" in str(exc)
        assert "decrypt" in str(exc)
        assert exc.operation == "decrypt"
    
    def test_credential_vault_error_inherits_aise_exception(self):
        """Test that CredentialVaultError inherits from AiSEException."""
        exc = CredentialVaultError("test")
        assert isinstance(exc, AiSEException)


class TestValidationExceptions:
    """Tests for validation related exceptions."""
    
    def test_validation_error_basic(self):
        """Test basic ValidationError."""
        exc = ValidationError("Validation failed")
        assert "Validation failed" in str(exc)
        assert exc.field is None
        assert exc.value is None
    
    def test_validation_error_with_field(self):
        """Test ValidationError with field."""
        exc = ValidationError("Missing required field", field="subject")
        assert "Missing required field" in str(exc)
        assert "subject" in str(exc)
        assert exc.field == "subject"
    
    def test_validation_error_with_field_and_value(self):
        """Test ValidationError with field and value."""
        exc = ValidationError(
            "Invalid email format",
            field="customer_email",
            value="not-an-email"
        )
        assert "Invalid email format" in str(exc)
        assert "customer_email" in str(exc)
        assert exc.field == "customer_email"
        assert exc.value == "not-an-email"
    
    def test_validation_error_truncates_long_values(self):
        """Test that ValidationError truncates long values."""
        long_value = "x" * 200
        exc = ValidationError("Invalid value", field="test", value=long_value)
        # Full value stored in attribute
        assert len(exc.value) == 200
        # But truncated in context for logging
        assert len(exc.context['value']) == 100
    
    def test_validation_error_inherits_aise_exception(self):
        """Test that ValidationError inherits from AiSEException."""
        exc = ValidationError("test")
        assert isinstance(exc, AiSEException)


class TestExceptionUsagePatterns:
    """Tests for common exception usage patterns."""
    
    def test_catching_specific_exception(self):
        """Test catching a specific exception type."""
        with pytest.raises(ForbiddenCommandError) as exc_info:
            raise ForbiddenCommandError("rm -rf /")
        
        assert "Command not allowed" in str(exc_info.value)
        assert exc_info.value.command == "rm -rf /"
    
    def test_catching_base_exception(self):
        """Test catching all AiSE exceptions with base class."""
        with pytest.raises(AiSEException):
            raise ProviderUnavailableError("anthropic")
    
    def test_exception_context_for_logging(self):
        """Test that exception context is suitable for structured logging."""
        exc = ToolExecutionError(
            "Command failed",
            command="aws ec2 describe-instances",
            exit_code=1,
            stderr="Access denied"
        )
        
        # Context should be a dict suitable for logging
        assert isinstance(exc.context, dict)
        assert exc.context['command'] == "aws ec2 describe-instances"
        assert exc.context['exit_code'] == 1
        assert 'stderr' in exc.context
    
    def test_exception_chaining(self):
        """Test exception chaining with raise from."""
        original_error = ValueError("Original error")
        
        with pytest.raises(ConfigurationError) as exc_info:
            try:
                raise original_error
            except ValueError as e:
                raise ConfigurationError("Config validation failed") from e
        
        assert exc_info.value.__cause__ is original_error
    
    def test_multiple_exception_types_in_try_except(self):
        """Test handling multiple exception types."""
        def risky_operation(error_type):
            if error_type == "provider":
                raise ProviderUnavailableError("anthropic")
            elif error_type == "tool":
                raise ForbiddenCommandError("rm -rf /")
            elif error_type == "ticket":
                raise TicketNotFoundError("12345")
        
        # Test catching specific types
        with pytest.raises(ProviderUnavailableError):
            risky_operation("provider")
        
        with pytest.raises(ForbiddenCommandError):
            risky_operation("tool")
        
        # Test catching all with base class
        for error_type in ["provider", "tool", "ticket"]:
            with pytest.raises(AiSEException):
                risky_operation(error_type)
