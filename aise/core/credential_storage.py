# aise/core/credential_storage.py
"""PostgreSQL storage backend for encrypted credentials.

This module provides persistent storage for encrypted credentials in PostgreSQL.
All credentials are encrypted using the CredentialVault before storage, and
all access is audit logged.

Example usage:
    >>> from aise.core.credential_storage import CredentialStorage
    >>> from aise.core.credential_vault import CredentialVault
    >>> from aise.core.config import get_config
    >>> 
    >>> config = get_config()
    >>> vault = CredentialVault(config)
    >>> storage = CredentialStorage(config, vault)
    >>> 
    >>> # Store a credential
    >>> await storage.store("zendesk_api_key", "my-secret-key", "api_key")
    >>> 
    >>> # Retrieve a credential (returns decrypted value)
    >>> api_key = await storage.retrieve("zendesk_api_key")
"""

import asyncpg
from typing import Optional, List, Dict, Any
from datetime import datetime
import structlog

from aise.core.exceptions import CredentialVaultError, ConfigurationError

logger = structlog.get_logger(__name__)


class CredentialStorage:
    """PostgreSQL storage backend for encrypted credentials.
    
    This class manages persistent storage of encrypted credentials in PostgreSQL.
    All credentials are encrypted before storage using the CredentialVault, and
    all access is audit logged for security compliance.
    
    Database Schema:
        credentials table:
            - id: SERIAL PRIMARY KEY
            - key: VARCHAR(255) UNIQUE NOT NULL (credential identifier)
            - encrypted_value: TEXT NOT NULL (encrypted credential)
            - credential_type: VARCHAR(50) (api_key, password, token, ssh_key)
            - created_at: TIMESTAMP NOT NULL
            - updated_at: TIMESTAMP NOT NULL
            - accessed_at: TIMESTAMP (last access time)
            - access_count: INTEGER DEFAULT 0
        
        credential_audit_log table:
            - id: SERIAL PRIMARY KEY
            - credential_key: VARCHAR(255) NOT NULL
            - operation: VARCHAR(50) NOT NULL (store, retrieve, delete, rotate)
            - component: VARCHAR(100) (requesting component)
            - timestamp: TIMESTAMP NOT NULL
            - success: BOOLEAN NOT NULL
            - error_message: TEXT
    
    Attributes:
        _config: Configuration instance
        _vault: CredentialVault instance for encryption/decryption
        _pool: asyncpg connection pool
    
    Example:
        >>> storage = CredentialStorage(config, vault)
        >>> await storage.initialize()
        >>> await storage.store("aws_access_key", "AKIA...", "api_key")
        >>> key = await storage.retrieve("aws_access_key")
    """
    
    def __init__(self, config, vault):
        """Initialize credential storage.
        
        Args:
            config: Configuration instance with database settings
            vault: CredentialVault instance for encryption/decryption
        """
        self._config = config
        self._vault = vault
        self._pool: Optional[asyncpg.Pool] = None
    
    async def initialize(self):
        """Initialize database connection pool and create schema.
        
        Creates the credentials and credential_audit_log tables if they don't exist.
        Establishes connection pool with retry logic.
        
        Raises:
            ConfigurationError: If database connection fails
        """
        if not hasattr(self._config, 'DATABASE_URL'):
            # Try POSTGRES_URL as fallback
            if not hasattr(self._config, 'POSTGRES_URL') or not self._config.POSTGRES_URL:
                raise ConfigurationError(
                    "DATABASE_URL or POSTGRES_URL not configured",
                    field="DATABASE_URL"
                )
            database_url = self._config.POSTGRES_URL
        else:
            database_url = self._config.DATABASE_URL or self._config.POSTGRES_URL
        
        try:
            # Create connection pool
            self._pool = await asyncpg.create_pool(
                database_url,
                min_size=5,
                max_size=20,
                command_timeout=60
            )
            
            logger.info(
                "credential_storage_pool_created",
                min_size=5,
                max_size=20
            )
            
            # Create schema
            await self._create_schema()
            
            logger.info("credential_storage_initialized")
            
        except Exception as e:
            logger.error(
                "credential_storage_initialization_failed",
                error=str(e)
            )
            raise ConfigurationError(
                f"Failed to initialize credential storage: {str(e)}",
                field="DATABASE_URL"
            )
    
    async def _create_schema(self):
        """Create database schema for credential storage.
        
        Creates credentials and credential_audit_log tables if they don't exist.
        """
        async with self._pool.acquire() as conn:
            # Create credentials table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS credentials (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(255) UNIQUE NOT NULL,
                    encrypted_value TEXT NOT NULL,
                    credential_type VARCHAR(50),
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    accessed_at TIMESTAMP,
                    access_count INTEGER DEFAULT 0
                )
            """)
            
            # Create index on key for fast lookups
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_credentials_key 
                ON credentials(key)
            """)
            
            # Create audit log table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS credential_audit_log (
                    id SERIAL PRIMARY KEY,
                    credential_key VARCHAR(255) NOT NULL,
                    operation VARCHAR(50) NOT NULL,
                    component VARCHAR(100),
                    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
                    success BOOLEAN NOT NULL,
                    error_message TEXT
                )
            """)
            
            # Create index on timestamp for audit queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp 
                ON credential_audit_log(timestamp DESC)
            """)
            
            logger.info("credential_storage_schema_created")

    
    async def store(
        self,
        key: str,
        plaintext_value: str,
        credential_type: str = "api_key",
        component: str = "system"
    ) -> bool:
        """Store an encrypted credential in PostgreSQL.
        
        The credential is encrypted using the CredentialVault before storage.
        If a credential with the same key exists, it will be updated.
        
        Args:
            key: Unique identifier for the credential (e.g., "zendesk_api_key")
            plaintext_value: The credential value to encrypt and store
            credential_type: Type of credential (api_key, password, token, ssh_key)
            component: Component requesting the storage (for audit logging)
        
        Returns:
            True if storage successful
        
        Raises:
            CredentialVaultError: If encryption or storage fails
            ValueError: If key or value is empty
        
        Example:
            >>> await storage.store("aws_access_key", "AKIA...", "api_key")
        """
        if not key or not plaintext_value:
            raise ValueError("Credential key and value cannot be empty")
        
        if not self._pool:
            raise CredentialVaultError(
                "Credential storage not initialized",
                operation="store"
            )
        
        try:
            # Encrypt the credential
            encrypted_value = self._vault.encrypt(plaintext_value)
            
            # Store in database (upsert)
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO credentials (key, encrypted_value, credential_type, created_at, updated_at)
                    VALUES ($1, $2, $3, NOW(), NOW())
                    ON CONFLICT (key) 
                    DO UPDATE SET 
                        encrypted_value = EXCLUDED.encrypted_value,
                        credential_type = EXCLUDED.credential_type,
                        updated_at = NOW()
                """, key, encrypted_value, credential_type)
            
            # Audit log
            await self._audit_log(key, "store", component, success=True)
            
            logger.info(
                "credential_stored",
                key=key,
                credential_type=credential_type,
                component=component
            )
            
            return True
            
        except Exception as e:
            # Audit log failure
            await self._audit_log(
                key, "store", component, 
                success=False, 
                error_message=str(e)
            )
            
            logger.error(
                "credential_store_failed",
                key=key,
                error=str(e)
            )
            
            raise CredentialVaultError(
                f"Failed to store credential '{key}': {str(e)}",
                operation="store"
            )
    
    async def retrieve(
        self,
        key: str,
        component: str = "system"
    ) -> Optional[str]:
        """Retrieve and decrypt a credential from PostgreSQL.
        
        The encrypted credential is retrieved from the database and decrypted
        using the CredentialVault. Access is audit logged.
        
        Args:
            key: Unique identifier for the credential
            component: Component requesting the retrieval (for audit logging)
        
        Returns:
            Decrypted credential value, or None if not found
        
        Raises:
            CredentialVaultError: If decryption fails
        
        Example:
            >>> api_key = await storage.retrieve("zendesk_api_key")
        
        Security Note:
            The decrypted credential is only in memory and should be used
            immediately. Never log or persist decrypted credentials.
        """
        if not key:
            raise ValueError("Credential key cannot be empty")
        
        if not self._pool:
            raise CredentialVaultError(
                "Credential storage not initialized",
                operation="retrieve"
            )
        
        try:
            # Retrieve from database
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT encrypted_value, credential_type
                    FROM credentials
                    WHERE key = $1
                """, key)
                
                if not row:
                    logger.warning(
                        "credential_not_found",
                        key=key,
                        component=component
                    )
                    return None
                
                # Update access tracking
                await conn.execute("""
                    UPDATE credentials
                    SET accessed_at = NOW(),
                        access_count = access_count + 1
                    WHERE key = $1
                """, key)
            
            # Decrypt the credential
            encrypted_value = row['encrypted_value']
            plaintext_value = self._vault.decrypt(encrypted_value)
            
            # Audit log
            await self._audit_log(key, "retrieve", component, success=True)
            
            logger.info(
                "credential_retrieved",
                key=key,
                credential_type=row['credential_type'],
                component=component
            )
            
            return plaintext_value
            
        except Exception as e:
            # Audit log failure
            await self._audit_log(
                key, "retrieve", component,
                success=False,
                error_message=str(e)
            )
            
            logger.error(
                "credential_retrieve_failed",
                key=key,
                error=str(e)
            )
            
            raise CredentialVaultError(
                f"Failed to retrieve credential '{key}': {str(e)}",
                operation="retrieve"
            )
    
    async def delete(
        self,
        key: str,
        component: str = "system"
    ) -> bool:
        """Delete a credential from PostgreSQL.
        
        Args:
            key: Unique identifier for the credential to delete
            component: Component requesting the deletion (for audit logging)
        
        Returns:
            True if deletion successful, False if credential not found
        
        Example:
            >>> await storage.delete("old_api_key")
        """
        if not key:
            raise ValueError("Credential key cannot be empty")
        
        if not self._pool:
            raise CredentialVaultError(
                "Credential storage not initialized",
                operation="delete"
            )
        
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute("""
                    DELETE FROM credentials
                    WHERE key = $1
                """, key)
                
                # Check if any rows were deleted
                deleted = result.split()[-1] != '0'
            
            # Audit log
            await self._audit_log(key, "delete", component, success=True)
            
            if deleted:
                logger.info(
                    "credential_deleted",
                    key=key,
                    component=component
                )
            else:
                logger.warning(
                    "credential_delete_not_found",
                    key=key,
                    component=component
                )
            
            return deleted
            
        except Exception as e:
            # Audit log failure
            await self._audit_log(
                key, "delete", component,
                success=False,
                error_message=str(e)
            )
            
            logger.error(
                "credential_delete_failed",
                key=key,
                error=str(e)
            )
            
            raise CredentialVaultError(
                f"Failed to delete credential '{key}': {str(e)}",
                operation="delete"
            )
    
    async def list_keys(self) -> List[Dict[str, Any]]:
        """List all stored credential keys with metadata.
        
        Returns credential keys with metadata but NOT the actual credential values.
        Useful for displaying available credentials in Config_UI.
        
        Returns:
            List of dictionaries with credential metadata:
                - key: Credential identifier
                - credential_type: Type of credential
                - created_at: When credential was first stored
                - updated_at: When credential was last updated
                - accessed_at: When credential was last accessed
                - access_count: Number of times accessed
        
        Example:
            >>> keys = await storage.list_keys()
            >>> for cred in keys:
            ...     print(f"{cred['key']}: {cred['credential_type']}")
        """
        if not self._pool:
            raise CredentialVaultError(
                "Credential storage not initialized",
                operation="list_keys"
            )
        
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT key, credential_type, created_at, updated_at, 
                           accessed_at, access_count
                    FROM credentials
                    ORDER BY key
                """)
            
            credentials = [dict(row) for row in rows]
            
            logger.info(
                "credentials_listed",
                count=len(credentials)
            )
            
            return credentials
            
        except Exception as e:
            logger.error(
                "credential_list_failed",
                error=str(e)
            )
            
            raise CredentialVaultError(
                f"Failed to list credentials: {str(e)}",
                operation="list_keys"
            )
    
    async def rotate_key(
        self,
        key: str,
        new_plaintext_value: str,
        component: str = "system"
    ) -> bool:
        """Rotate a credential by updating it with a new value.
        
        This is a convenience method that combines retrieve (for audit) and store.
        
        Args:
            key: Unique identifier for the credential to rotate
            new_plaintext_value: New credential value
            component: Component requesting the rotation (for audit logging)
        
        Returns:
            True if rotation successful
        
        Example:
            >>> await storage.rotate_key("api_key", "new-secret-value")
        """
        if not key or not new_plaintext_value:
            raise ValueError("Credential key and new value cannot be empty")
        
        try:
            # Get existing credential type
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT credential_type
                    FROM credentials
                    WHERE key = $1
                """, key)
                
                credential_type = row['credential_type'] if row else "api_key"
            
            # Store new value (this will update existing)
            await self.store(key, new_plaintext_value, credential_type, component)
            
            # Audit log rotation
            await self._audit_log(key, "rotate", component, success=True)
            
            logger.info(
                "credential_rotated",
                key=key,
                component=component
            )
            
            return True
            
        except Exception as e:
            # Audit log failure
            await self._audit_log(
                key, "rotate", component,
                success=False,
                error_message=str(e)
            )
            
            logger.error(
                "credential_rotate_failed",
                key=key,
                error=str(e)
            )
            
            raise CredentialVaultError(
                f"Failed to rotate credential '{key}': {str(e)}",
                operation="rotate"
            )
    
    async def _audit_log(
        self,
        credential_key: str,
        operation: str,
        component: str,
        success: bool,
        error_message: Optional[str] = None
    ):
        """Log credential access to audit log.
        
        Args:
            credential_key: Credential identifier
            operation: Operation performed (store, retrieve, delete, rotate)
            component: Component performing the operation
            success: Whether operation succeeded
            error_message: Error message if operation failed
        """
        if not self._pool:
            return
        
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO credential_audit_log 
                        (credential_key, operation, component, timestamp, success, error_message)
                    VALUES ($1, $2, $3, NOW(), $4, $5)
                """, credential_key, operation, component, success, error_message)
        except Exception as e:
            # Don't raise exception for audit log failures
            logger.error(
                "audit_log_failed",
                credential_key=credential_key,
                operation=operation,
                error=str(e)
            )
    
    async def get_audit_log(
        self,
        credential_key: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Retrieve audit log entries.
        
        Args:
            credential_key: Optional filter by credential key
            limit: Maximum number of entries to return (default: 100)
        
        Returns:
            List of audit log entries
        
        Example:
            >>> logs = await storage.get_audit_log("zendesk_api_key", limit=50)
        """
        if not self._pool:
            raise CredentialVaultError(
                "Credential storage not initialized",
                operation="get_audit_log"
            )
        
        try:
            async with self._pool.acquire() as conn:
                if credential_key:
                    rows = await conn.fetch("""
                        SELECT credential_key, operation, component, timestamp, 
                               success, error_message
                        FROM credential_audit_log
                        WHERE credential_key = $1
                        ORDER BY timestamp DESC
                        LIMIT $2
                    """, credential_key, limit)
                else:
                    rows = await conn.fetch("""
                        SELECT credential_key, operation, component, timestamp,
                               success, error_message
                        FROM credential_audit_log
                        ORDER BY timestamp DESC
                        LIMIT $1
                    """, limit)
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(
                "audit_log_retrieve_failed",
                error=str(e)
            )
            
            raise CredentialVaultError(
                f"Failed to retrieve audit log: {str(e)}",
                operation="get_audit_log"
            )
    
    async def close(self):
        """Close database connection pool.
        
        Should be called during application shutdown.
        """
        if self._pool:
            await self._pool.close()
            logger.info("credential_storage_pool_closed")
