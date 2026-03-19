# aise/config_ui/persistence.py
"""Configuration persistence for Config UI.

This module handles persisting configuration changes to the database
and applying them to the running system without requiring a restart.

Example usage:
    >>> from aise.config_ui.persistence import ConfigPersistence
    >>> 
    >>> persistence = ConfigPersistence(config, credential_storage)
    >>> await persistence.initialize()
    >>> 
    >>> # Update configuration
    >>> await persistence.update_config("ANTHROPIC_API_KEY", "sk-ant-...")
"""

from typing import Optional, Dict, Any
import structlog
import asyncpg
import os

from aise.core.exceptions import ConfigurationError

logger = structlog.get_logger(__name__)


class ConfigPersistence:
    """Handles configuration persistence to database and runtime updates.
    
    This class manages storing configuration changes to PostgreSQL and
    applying them to the running system without requiring a restart.
    
    Database Schema:
        config_settings table:
            - id: SERIAL PRIMARY KEY
            - key: VARCHAR(255) UNIQUE NOT NULL
            - value: TEXT NOT NULL
            - is_sensitive: BOOLEAN DEFAULT FALSE
            - created_at: TIMESTAMP NOT NULL
            - updated_at: TIMESTAMP NOT NULL
    
    Attributes:
        _config: Configuration instance
        _credential_storage: CredentialStorage instance for sensitive values
        _pool: asyncpg connection pool
    """
    
    # Configuration keys that should be stored as encrypted credentials
    SENSITIVE_KEYS = {
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "ZENDESK_API_TOKEN",
        "FRESHDESK_API_KEY",
        "EMAIL_IMAP_PASSWORD",
        "EMAIL_SMTP_PASSWORD",
        "SLACK_BOT_TOKEN",
        "SLACK_SIGNING_SECRET",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "CREDENTIAL_VAULT_KEY",
        "WEBHOOK_SECRET",
        "LANGSMITH_API_KEY",
    }
    
    def __init__(self, config, credential_storage=None):
        """Initialize configuration persistence.
        
        Args:
            config: Configuration instance
            credential_storage: Optional CredentialStorage instance for sensitive values
        """
        self._config = config
        self._credential_storage = credential_storage
        self._pool: Optional[asyncpg.Pool] = None
    
    async def initialize(self):
        """Initialize database connection pool and create schema.
        
        Raises:
            ConfigurationError: If database connection fails
        """
        database_url = self._config.POSTGRES_URL
        
        try:
            # Create connection pool
            self._pool = await asyncpg.create_pool(
                database_url,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            
            logger.info("config_persistence_pool_created")
            
            # Create schema
            await self._create_schema()
            
            logger.info("config_persistence_initialized")
            
        except Exception as e:
            logger.error("config_persistence_initialization_failed", error=str(e))
            raise ConfigurationError(
                f"Failed to initialize config persistence: {str(e)}",
                field="POSTGRES_URL"
            )
    
    async def _create_schema(self):
        """Create database schema for configuration storage."""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS config_settings (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(255) UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    is_sensitive BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_config_key 
                ON config_settings(key)
            """)
            
            logger.info("config_persistence_schema_created")
    
    async def update_config(
        self,
        key: str,
        value: str,
        component: str = "config_ui"
    ) -> bool:
        """Update a configuration value and apply it to the running system.
        
        Sensitive values are stored in the credential vault, while non-sensitive
        values are stored in the config_settings table. The change is also
        applied to the running Config instance.
        
        Args:
            key: Configuration key to update
            value: New value for the configuration key
            component: Component requesting the update (for audit logging)
        
        Returns:
            True if update successful
        
        Raises:
            ConfigurationError: If update fails
            ValueError: If key is invalid
        """
        if not key or not value:
            raise ValueError("Configuration key and value cannot be empty")
        
        # Validate that the key exists in Config model
        if not hasattr(self._config, key):
            raise ValueError(f"Unknown configuration key: {key}")
        
        try:
            is_sensitive = key in self.SENSITIVE_KEYS
            
            if is_sensitive and self._credential_storage:
                # Store sensitive value in credential vault
                await self._credential_storage.store(
                    key=key,
                    plaintext_value=value,
                    credential_type="api_key" if "KEY" in key else "password",
                    component=component
                )
                
                logger.info(
                    "sensitive_config_stored",
                    key=key,
                    component=component
                )
            else:
                # Store non-sensitive value in config_settings table
                async with self._pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO config_settings (key, value, is_sensitive, created_at, updated_at)
                        VALUES ($1, $2, $3, NOW(), NOW())
                        ON CONFLICT (key)
                        DO UPDATE SET
                            value = EXCLUDED.value,
                            updated_at = NOW()
                    """, key, value, is_sensitive)
                
                logger.info(
                    "config_stored",
                    key=key,
                    component=component
                )
            
            # Apply to running config instance
            await self._apply_to_runtime(key, value)

            # Audit log the config change
            import asyncio
            from aise.core.audit import log_security_event
            asyncio.ensure_future(log_security_event(
                event_type="config_change",
                action=f"set {key}",
                component=component,
                success=True,
                resource_type="configuration",
                resource_id=key,
                details={"is_sensitive": is_sensitive},
            ))

            return True
            
        except Exception as e:
            logger.error(
                "config_update_failed",
                key=key,
                error=str(e)
            )
            raise ConfigurationError(
                f"Failed to update configuration '{key}': {str(e)}",
                field=key
            )
    
    async def _apply_to_runtime(self, key: str, value: str):
        """Apply configuration change to the running Config instance.
        
        This allows configuration changes to take effect without restarting
        the application.
        
        Args:
            key: Configuration key
            value: New value
        """
        try:
            # Get the field type from the Config model
            field_info = self._config.model_fields.get(key)
            
            if not field_info:
                logger.warning("config_field_not_found", key=key)
                return
            
            # Convert value to appropriate type
            field_type = field_info.annotation
            
            # Handle Optional types
            if hasattr(field_type, '__origin__') and field_type.__origin__ is type(None):
                # It's Optional[T], extract T
                field_type = field_type.__args__[0]
            
            # Convert string value to appropriate type
            if field_type == bool:
                converted_value = value.lower() in ('true', '1', 'yes', 'on')
            elif field_type == int:
                converted_value = int(value)
            else:
                converted_value = value
            
            # Update the config instance
            setattr(self._config, key, converted_value)
            
            # Also update environment variable for child processes
            os.environ[key] = value
            
            logger.info(
                "config_applied_to_runtime",
                key=key
            )
            
        except Exception as e:
            logger.error(
                "config_runtime_apply_failed",
                key=key,
                error=str(e)
            )
            # Don't raise - persistence succeeded even if runtime update failed
    
    async def get_config(self, key: str) -> Optional[str]:
        """Retrieve a configuration value from storage.
        
        Args:
            key: Configuration key to retrieve
        
        Returns:
            Configuration value, or None if not found
        """
        try:
            is_sensitive = key in self.SENSITIVE_KEYS
            
            if is_sensitive and self._credential_storage:
                # Retrieve from credential vault
                value = await self._credential_storage.retrieve(key)
                return value
            else:
                # Retrieve from config_settings table
                async with self._pool.acquire() as conn:
                    row = await conn.fetchrow("""
                        SELECT value
                        FROM config_settings
                        WHERE key = $1
                    """, key)
                    
                    if row:
                        return row['value']
                    
                    # Fall back to current config value
                    return str(getattr(self._config, key, None))
            
        except Exception as e:
            logger.error("config_retrieve_failed", key=key, error=str(e))
            return None
    
    async def load_all_config(self) -> Dict[str, Any]:
        """Load all configuration from storage.
        
        Returns:
            Dictionary of all configuration key-value pairs
        """
        config_dict = {}
        
        try:
            # Load non-sensitive values from config_settings
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT key, value
                    FROM config_settings
                """)
                
                for row in rows:
                    config_dict[row['key']] = row['value']
            
            # Load sensitive values from credential vault
            if self._credential_storage:
                for key in self.SENSITIVE_KEYS:
                    value = await self._credential_storage.retrieve(key)
                    if value:
                        config_dict[key] = value
            
            logger.info("all_config_loaded", count=len(config_dict))
            return config_dict
            
        except Exception as e:
            logger.error("config_load_all_failed", error=str(e))
            return {}
    
    async def delete_config(self, key: str) -> bool:
        """Delete a configuration value from storage.
        
        Args:
            key: Configuration key to delete
        
        Returns:
            True if deletion successful
        """
        try:
            is_sensitive = key in self.SENSITIVE_KEYS
            
            if is_sensitive and self._credential_storage:
                # Delete from credential vault
                await self._credential_storage.delete(key)
            else:
                # Delete from config_settings table
                async with self._pool.acquire() as conn:
                    await conn.execute("""
                        DELETE FROM config_settings
                        WHERE key = $1
                    """, key)
            
            logger.info("config_deleted", key=key)
            return True
            
        except Exception as e:
            logger.error("config_delete_failed", key=key, error=str(e))
            return False
    
    async def close(self):
        """Close database connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("config_persistence_pool_closed")
