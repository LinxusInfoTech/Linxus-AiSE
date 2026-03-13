# aise/core/exceptions.py
"""Custom exception hierarchy for AiSE.

This module defines all custom exceptions used throughout the AiSE system.
All exceptions inherit from AiSEException for easy catching and handling.
"""


class AiSEException(Exception):
    """Base exception for all AiSE-specific errors.
    
    All custom exceptions in the AiSE system inherit from this base class,
    allowing for easy catching of all AiSE-related errors.
    
    Attributes:
        message: Human-readable error message
        context: Optional dictionary containing additional error context
    """
    
    def __init__(self, message: str, context: dict = None):
        self.message = message
        self.context = context or {}
        super().__init__(message)
    
    def __str__(self):
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"{self.message} ({context_str})"
        return self.message


# Tool Execution Exceptions

class ToolExecutionError(AiSEException):
    """Base exception for tool execution failures.
    
    Raised when a CLI tool execution fails for any reason.
    Use more specific subclasses when the failure type is known.
    
    Attributes:
        command: The command that failed
        exit_code: The exit code returned by the command (if available)
        stdout: Standard output from the command
        stderr: Standard error from the command
    """
    
    def __init__(self, message: str, command: str = None, exit_code: int = None, 
                 stdout: str = None, stderr: str = None):
        context = {}
        if command:
            context['command'] = command
        if exit_code is not None:
            context['exit_code'] = exit_code
        if stdout:
            context['stdout'] = stdout[:200]  # Truncate for logging
        if stderr:
            context['stderr'] = stderr[:200]  # Truncate for logging
        super().__init__(message, context)
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class ForbiddenCommandError(ToolExecutionError):
    """Raised when a command is not in the allowlist.
    
    This exception is raised when the Tool_Executor attempts to execute
    a command that is not permitted by the CommandAllowlist. This is a
    security feature to prevent unauthorized or dangerous operations.
    
    Use this when:
    - A command is not in the allowlist at all
    - A command's subcommand is not permitted
    - A command contains suspicious patterns
    
    Example:
        >>> allowlist.validate_or_raise("rm -rf /")
        ForbiddenCommandError: Command not allowed: rm -rf /
    """
    
    def __init__(self, command: str, reason: str = None):
        message = f"Command not allowed: {command}"
        if reason:
            message += f" - {reason}"
        super().__init__(message, command=command)
        self.reason = reason


class ToolExecutionTimeout(ToolExecutionError):
    """Raised when a tool execution exceeds the timeout limit.
    
    This exception is raised when a CLI command runs longer than the
    configured timeout period. The process is killed before raising
    this exception.
    
    Use this when:
    - A command exceeds the configured timeout (default 30 seconds)
    - A command appears to be hanging or stuck
    
    Example:
        >>> await executor.run("sleep 60", timeout=5)
        ToolExecutionTimeout: Command timed out after 5s: sleep 60
    """
    
    def __init__(self, command: str, timeout: int):
        message = f"Command timed out after {timeout}s: {command}"
        super().__init__(message, command=command)
        self.timeout = timeout


# LLM Provider Exceptions

class ProviderError(AiSEException):
    """Base exception for LLM provider failures.
    
    Raised when an LLM provider encounters an error during completion.
    This could be due to API errors, network issues, rate limiting, etc.
    
    Attributes:
        provider: Name of the provider that failed (e.g., "anthropic", "openai")
        status_code: HTTP status code if applicable
        retry_after: Seconds to wait before retrying (for rate limits)
    """
    
    def __init__(self, message: str, provider: str = None, status_code: int = None,
                 retry_after: int = None):
        context = {}
        if provider:
            context['provider'] = provider
        if status_code:
            context['status_code'] = status_code
        if retry_after:
            context['retry_after'] = retry_after
        super().__init__(message, context)
        self.provider = provider
        self.status_code = status_code
        self.retry_after = retry_after


class ProviderUnavailableError(ProviderError):
    """Raised when an LLM provider is temporarily unavailable.
    
    This exception indicates that a provider cannot be reached or is
    experiencing temporary issues. The system should attempt failover
    to a secondary provider.
    
    Use this when:
    - Network connection to provider fails
    - Provider returns 503 Service Unavailable
    - Provider is rate-limiting requests
    - Provider API is down for maintenance
    
    Example:
        >>> await anthropic_provider.complete(messages)
        ProviderUnavailableError: Provider anthropic unavailable: Connection timeout
    """
    
    def __init__(self, provider: str, reason: str = None, retry_after: int = None):
        message = f"Provider {provider} unavailable"
        if reason:
            message += f": {reason}"
        super().__init__(message, provider=provider, retry_after=retry_after)
        self.reason = reason


class AuthenticationError(ProviderError):
    """Raised when LLM provider authentication fails.
    
    This exception is raised when API key validation fails or when
    the provider rejects authentication credentials.
    
    Use this when:
    - API key is missing or invalid
    - Provider returns 401 Unauthorized
    - Provider returns 403 Forbidden
    - API key has expired or been revoked
    
    Example:
        >>> await anthropic_provider.complete(messages)
        AuthenticationError: Invalid API key for provider anthropic
    """
    
    def __init__(self, provider: str, reason: str = None):
        message = f"Authentication failed for provider {provider}"
        if reason:
            message += f": {reason}"
        super().__init__(message, provider=provider)
        self.reason = reason


class AllProvidersFailedError(ProviderError):
    """Raised when all configured LLM providers have failed.
    
    This exception is raised after attempting failover to all configured
    providers and all of them failed. This is a critical error that
    prevents the system from generating responses.
    
    Use this when:
    - Primary provider fails and no secondary providers are configured
    - All configured providers fail in sequence
    - System cannot generate LLM responses
    
    Example:
        >>> await router.complete_with_failover(messages)
        AllProvidersFailedError: No LLM providers available
    """
    
    def __init__(self, message: str = "No LLM providers available", 
                 failed_providers: list = None):
        super().__init__(message)
        self.failed_providers = failed_providers or []


# Ticket System Exceptions

class TicketAPIError(AiSEException):
    """Base exception for ticket system API failures.
    
    Raised when a ticket provider API call fails. This could be due to
    authentication issues, network errors, or API-specific errors.
    
    Attributes:
        provider: Name of the ticket provider (e.g., "zendesk", "freshdesk")
        status_code: HTTP status code if applicable
        ticket_id: ID of the ticket being operated on (if applicable)
    """
    
    def __init__(self, message: str, provider: str = None, status_code: int = None,
                 ticket_id: str = None):
        context = {}
        if provider:
            context['provider'] = provider
        if status_code:
            context['status_code'] = status_code
        if ticket_id:
            context['ticket_id'] = ticket_id
        super().__init__(message, context)
        self.provider = provider
        self.status_code = status_code
        self.ticket_id = ticket_id


class TicketNotFoundError(TicketAPIError):
    """Raised when a ticket ID does not exist in the ticket system.
    
    This exception indicates that the requested ticket cannot be found.
    This could be because the ID is invalid, the ticket was deleted,
    or there's a permission issue.
    
    Use this when:
    - Ticket ID does not exist in the system
    - API returns 404 Not Found for a ticket
    - User lacks permission to view the ticket
    
    Example:
        >>> await zendesk.get("invalid-id")
        TicketNotFoundError: Ticket not found: invalid-id
    """
    
    def __init__(self, ticket_id: str, provider: str = None):
        message = f"Ticket not found: {ticket_id}"
        super().__init__(message, provider=provider, ticket_id=ticket_id)


# Knowledge Engine Exceptions

class VectorStoreError(AiSEException):
    """Raised when vector store operations fail.
    
    This exception is raised when ChromaDB or the vector store encounters
    an error during upsert, search, or other operations.
    
    Use this when:
    - ChromaDB connection fails
    - Vector store is unavailable
    - Embedding dimension mismatch
    - Search query fails
    
    Note: When the vector store is unavailable, the system should continue
    without knowledge context and log a warning (Requirement 18.3).
    
    Example:
        >>> await vector_store.search(query)
        VectorStoreError: ChromaDB connection failed: Connection refused
    """
    
    def __init__(self, message: str, operation: str = None):
        context = {}
        if operation:
            context['operation'] = operation
        super().__init__(message, context)
        self.operation = operation


class KnowledgeEngineError(AiSEException):
    """Raised when knowledge engine operations fail.
    
    This exception is raised when the knowledge engine encounters errors
    during crawling, chunking, embedding, or retrieval operations.
    
    Use this when:
    - Knowledge manager initialization fails
    - Documentation crawling fails
    - Embedding generation fails
    - Knowledge retrieval fails
    - Metadata store operations fail
    
    Attributes:
        operation: The operation that failed (e.g., "initialization", "crawl", "embed")
    """
    
    def __init__(self, message: str, operation: str = None):
        context = {}
        if operation:
            context['operation'] = operation
        super().__init__(message, context)
        self.operation = operation


# Browser Automation Exceptions

class BrowserError(AiSEException):
    """Raised when browser automation operations fail.
    
    This exception is raised when Playwright browser operations encounter
    errors. This could be due to element not found, timeout, navigation
    failures, etc.
    
    Use this when:
    - Browser fails to launch
    - Page navigation fails
    - Element not found on page
    - Browser action times out
    - Screenshot capture fails
    
    Note: When browser automation fails, the system should fall back to
    API if available (Requirement 18.8).
    
    Attributes:
        action: The browser action that failed (e.g., "click", "navigate")
        url: The URL being operated on (if applicable)
        selector: The CSS selector being used (if applicable)
    """
    
    def __init__(self, message: str, action: str = None, url: str = None,
                 selector: str = None):
        context = {}
        if action:
            context['action'] = action
        if url:
            context['url'] = url
        if selector:
            context['selector'] = selector
        super().__init__(message, context)
        self.action = action
        self.url = url
        self.selector = selector


# Configuration Exceptions

class ConfigurationError(AiSEException):
    """Raised when configuration is invalid or missing.
    
    This exception is raised during system startup or configuration
    validation when required settings are missing or invalid.
    
    Use this when:
    - Required configuration values are missing
    - Configuration values fail validation
    - API keys are invalid
    - Database connection strings are malformed
    - Configuration file cannot be loaded
    
    The system should fail to start with a clear error message when
    this exception is raised (Requirement 17.3).
    
    Example:
        >>> Config()
        ConfigurationError: At least one LLM provider API key must be set
    """
    
    def __init__(self, message: str, field: str = None, value: str = None):
        context = {}
        if field:
            context['field'] = field
        if value:
            context['value'] = value
        super().__init__(message, context)
        self.field = field
        self.value = value


# Credential Vault Exceptions

class CredentialVaultError(AiSEException):
    """Raised when credential vault operations fail.
    
    This exception is raised when encryption, decryption, or credential
    storage operations fail in the Credential_Vault.
    
    Use this when:
    - Encryption key is missing or invalid
    - Decryption fails (corrupted data or wrong key)
    - Credential storage fails
    - Key rotation fails
    
    The system should fail to start if the encryption key is missing
    or invalid (Requirement 2.10).
    
    Example:
        >>> vault.decrypt(encrypted_credential)
        CredentialVaultError: Decryption failed: Invalid encryption key
    """
    
    def __init__(self, message: str, operation: str = None):
        context = {}
        if operation:
            context['operation'] = operation
        super().__init__(message, context)
        self.operation = operation


# Database Exceptions

class DatabaseError(AiSEException):
    """Raised when database operations fail.
    
    This exception is raised when PostgreSQL or Redis operations encounter
    errors during queries, inserts, updates, or deletes.
    
    Use this when:
    - Database connection fails
    - Query execution fails
    - Transaction fails
    - Data integrity constraint violated
    
    Attributes:
        operation: The database operation that failed (e.g., "insert", "query")
    """
    
    def __init__(self, message: str, operation: str = None):
        context = {}
        if operation:
            context['operation'] = operation
        super().__init__(message, context)
        self.operation = operation


# General Validation Exceptions

class ValidationError(AiSEException):
    """Raised when data validation fails.
    
    This exception is raised when input data, API responses, or internal
    data structures fail validation checks.
    
    Use this when:
    - Ticket data is malformed (Requirement 18.7)
    - API response doesn't match expected schema
    - User input fails validation
    - Data type conversion fails
    
    Example:
        >>> validate_ticket(malformed_data)
        ValidationError: Invalid ticket data: missing required field 'subject'
    """
    
    def __init__(self, message: str, field: str = None, value: str = None):
        context = {}
        if field:
            context['field'] = field
        if value:
            context['value'] = str(value)[:100]  # Truncate for logging
        super().__init__(message, context)
        self.field = field
        self.value = value
