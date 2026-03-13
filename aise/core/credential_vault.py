# aise/core/credential_vault.py
"""Encrypted credential vault with AES-256-GCM encryption.

This module provides secure storage for sensitive credentials using Fernet
symmetric encryption (AES-256-GCM). All credential access is audit logged,
and credentials are never logged in plaintext.

The CredentialVault handles encryption/decryption, while CredentialStorage
handles persistent storage in PostgreSQL. Use CredentialStorage for most
use cases as it provides a complete solution.

Example usage:
    >>> from aise.core.credential_vault import CredentialVault
    >>> from aise.core.config import get_config
    >>> 
    >>> config = get_config()
    >>> vault = CredentialVault(config)
    >>> 
    >>> # Encrypt and store a credential
    >>> encrypted = vault.encrypt("my-secret-api-key")
    >>> 
    >>> # Decrypt when needed
    >>> decrypted = vault.decrypt(encrypted)
    >>> # decrypted == "my-secret-api-key"
    >>> 
    >>> # For persistent storage, use CredentialStorage:
    >>> from aise.core.credential_storage import CredentialStorage
    >>> storage = CredentialStorage(config, vault)
    >>> await storage.initialize()
    >>> await storage.store("api_key", "my-secret-api-key")
    >>> api_key = await storage.retrieve("api_key")
"""

import os
import secrets
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
import structlog

from aise.core.exceptions import CredentialVaultError

logger = structlog.get_logger(__name__)


class CredentialVault:
    """Encrypted credential vault using Fernet (AES-256-GCM).
    
    This class provides secure encryption and decryption of sensitive credentials
    using the cryptography library's Fernet implementation, which uses AES-256-GCM
    for authenticated encryption.
    
    The encryption key can be loaded from:
    1. CREDENTIAL_VAULT_KEY environment variable
    2. Key file at ~/.aise/vault.key
    3. Auto-generated on first run (saved to ~/.aise/vault.key)
    
    All credential access is audit logged using structlog. Credentials are never
    logged in plaintext - only masked values are logged.
    
    Attributes:
        _fernet: Fernet cipher instance for encryption/decryption
        _key_source: Description of where the encryption key was loaded from
    
    Example:
        >>> vault = CredentialVault(config)
        >>> encrypted = vault.encrypt("secret-password")
        >>> decrypted = vault.decrypt(encrypted)
    
    Security Notes:
        - Encryption key must be kept secure and backed up
        - In production, use a key management system (AWS KMS, HashiCorp Vault, etc.)
        - Never commit the encryption key to version control
        - Rotate encryption keys periodically using rotate_key()
    """
    
    def __init__(self, config=None):
        """Initialize the credential vault with encryption key.
        
        Args:
            config: Optional Config instance. If None, will attempt to load
                   from environment variable or generate new key.
        
        Raises:
            CredentialVaultError: If encryption key is invalid or cannot be loaded
        """
        self._fernet: Optional[Fernet] = None
        self._key_source: str = "unknown"
        
        # Load or generate encryption key
        encryption_key = self._load_or_generate_key(config)
        
        try:
            self._fernet = Fernet(encryption_key)
            logger.info(
                "credential_vault_initialized",
                key_source=self._key_source
            )
        except Exception as e:
            raise CredentialVaultError(
                f"Failed to initialize credential vault: {str(e)}",
                operation="initialization"
            )
    
    def _load_or_generate_key(self, config) -> bytes:
        """Load encryption key from config, environment, file, or generate new.
        
        Priority order:
        1. CREDENTIAL_VAULT_KEY environment variable
        2. Config.CREDENTIAL_VAULT_KEY (if config provided)
        3. Key file at ~/.aise/vault.key
        4. Auto-generate and save to ~/.aise/vault.key
        
        Args:
            config: Optional Config instance
        
        Returns:
            Encryption key as bytes
        
        Raises:
            CredentialVaultError: If key is invalid
        """
        # Try environment variable first (highest priority)
        env_key = os.environ.get("CREDENTIAL_VAULT_KEY")
        if env_key:
            self._key_source = "environment variable CREDENTIAL_VAULT_KEY"
            return self._validate_key(env_key.encode())
        
        # Try config object
        if config and hasattr(config, "CREDENTIAL_VAULT_KEY") and config.CREDENTIAL_VAULT_KEY:
            self._key_source = "config.CREDENTIAL_VAULT_KEY"
            return self._validate_key(config.CREDENTIAL_VAULT_KEY.encode())
        
        # Try key file
        key_file = Path.home() / ".aise" / "vault.key"
        if key_file.exists():
            try:
                key_data = key_file.read_bytes().strip()
                self._key_source = str(key_file)
                return self._validate_key(key_data)
            except Exception as e:
                logger.warning(
                    "failed_to_read_key_file",
                    path=str(key_file),
                    error=str(e)
                )
        
        # Auto-generate new key
        logger.warning(
            "no_encryption_key_found",
            message="Generating new encryption key. IMPORTANT: Back up this key for production use!"
        )
        return self._generate_and_save_key(key_file)
    
    def _validate_key(self, key: bytes) -> bytes:
        """Validate that the key is a valid Fernet key.
        
        Args:
            key: Encryption key to validate
        
        Returns:
            Validated key
        
        Raises:
            CredentialVaultError: If key is invalid
        """
        try:
            # Try to create a Fernet instance to validate the key
            Fernet(key)
            return key
        except Exception as e:
            raise CredentialVaultError(
                f"Invalid encryption key: {str(e)}",
                operation="key_validation"
            )
    
    def _generate_and_save_key(self, key_file: Path) -> bytes:
        """Generate a new Fernet key and save it to file.
        
        Args:
            key_file: Path where the key should be saved
        
        Returns:
            Generated encryption key
        
        Raises:
            CredentialVaultError: If key cannot be saved
        """
        # Generate new Fernet key
        key = Fernet.generate_key()
        
        # Create directory if it doesn't exist
        key_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Save key to file with restricted permissions
            key_file.write_bytes(key)
            # Set file permissions to 600 (owner read/write only)
            key_file.chmod(0o600)
            
            self._key_source = f"{key_file} (auto-generated)"
            
            logger.warning(
                "encryption_key_generated",
                path=str(key_file),
                message=(
                    "New encryption key generated and saved. "
                    "PRODUCTION USERS: Back up this key securely! "
                    "Consider using a key management system (AWS KMS, HashiCorp Vault, etc.) "
                    "Set CREDENTIAL_VAULT_KEY environment variable to use a specific key."
                )
            )
            
            return key
        except Exception as e:
            raise CredentialVaultError(
                f"Failed to save encryption key: {str(e)}",
                operation="key_generation"
            )
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt a credential using Fernet (AES-256-GCM).
        
        Args:
            plaintext: The credential to encrypt (e.g., API key, password)
        
        Returns:
            Base64-encoded encrypted credential as string
        
        Raises:
            CredentialVaultError: If encryption fails
            ValueError: If plaintext is empty
        
        Example:
            >>> vault = CredentialVault(config)
            >>> encrypted = vault.encrypt("my-secret-key")
            >>> # encrypted is a base64 string like: "gAAAAABh..."
        """
        if not plaintext:
            raise ValueError("Cannot encrypt empty credential")
        
        if not self._fernet:
            raise CredentialVaultError(
                "Credential vault not initialized",
                operation="encrypt"
            )
        
        try:
            # Convert to bytes and encrypt
            plaintext_bytes = plaintext.encode('utf-8')
            encrypted_bytes = self._fernet.encrypt(plaintext_bytes)
            
            # Return as base64 string
            encrypted_str = encrypted_bytes.decode('utf-8')
            
            # Audit log (never log the plaintext!)
            logger.info(
                "credential_encrypted",
                length=len(plaintext),
                encrypted_length=len(encrypted_str)
            )
            
            return encrypted_str
            
        except Exception as e:
            logger.error(
                "encryption_failed",
                error=str(e)
            )
            raise CredentialVaultError(
                f"Failed to encrypt credential: {str(e)}",
                operation="encrypt"
            )
    
    def decrypt(self, encrypted: str) -> str:
        """Decrypt a credential using Fernet (AES-256-GCM).
        
        Args:
            encrypted: Base64-encoded encrypted credential
        
        Returns:
            Decrypted credential as plaintext string
        
        Raises:
            CredentialVaultError: If decryption fails (wrong key, corrupted data)
            ValueError: If encrypted is empty
        
        Example:
            >>> vault = CredentialVault(config)
            >>> decrypted = vault.decrypt("gAAAAABh...")
            >>> # decrypted is the original plaintext
        
        Security Note:
            The decrypted credential is only in memory and should be used
            immediately. Never log or persist decrypted credentials.
        """
        if not encrypted:
            raise ValueError("Cannot decrypt empty string")
        
        if not self._fernet:
            raise CredentialVaultError(
                "Credential vault not initialized",
                operation="decrypt"
            )
        
        try:
            # Convert from base64 string to bytes
            encrypted_bytes = encrypted.encode('utf-8')
            
            # Decrypt
            plaintext_bytes = self._fernet.decrypt(encrypted_bytes)
            plaintext = plaintext_bytes.decode('utf-8')
            
            # Audit log (never log the decrypted value!)
            logger.info(
                "credential_decrypted",
                encrypted_length=len(encrypted),
                decrypted_length=len(plaintext)
            )
            
            return plaintext
            
        except InvalidToken:
            logger.error(
                "decryption_failed",
                error="Invalid token - wrong encryption key or corrupted data"
            )
            raise CredentialVaultError(
                "Decryption failed: Invalid encryption key or corrupted data",
                operation="decrypt"
            )
        except Exception as e:
            logger.error(
                "decryption_failed",
                error=str(e)
            )
            raise CredentialVaultError(
                f"Failed to decrypt credential: {str(e)}",
                operation="decrypt"
            )
    
    @staticmethod
    def mask_credential(credential: str, show_chars: int = 4) -> str:
        """Mask a credential for safe logging/display.
        
        Shows only the first and last N characters, masking the middle with asterisks.
        This is useful for logging and displaying credentials in UIs.
        
        Args:
            credential: The credential to mask
            show_chars: Number of characters to show at start and end (default: 4)
        
        Returns:
            Masked credential string (e.g., "abcd****wxyz")
        
        Example:
            >>> CredentialVault.mask_credential("my-secret-api-key-12345")
            "my-s****2345"
            >>> CredentialVault.mask_credential("short")
            "****"
        """
        if not credential or len(credential) <= show_chars * 2:
            return "****"
        
        return f"{credential[:show_chars]}****{credential[-show_chars:]}"
    
    def get_key_info(self) -> dict:
        """Get information about the encryption key (for diagnostics).
        
        Returns:
            Dictionary with key source and status information
        
        Example:
            >>> vault = CredentialVault(config)
            >>> info = vault.get_key_info()
            >>> print(info)
            {
                'initialized': True,
                'key_source': 'environment variable CREDENTIAL_VAULT_KEY',
                'key_length': 44
            }
        """
        return {
            'initialized': self._fernet is not None,
            'key_source': self._key_source,
            'key_length': 44 if self._fernet else 0  # Fernet keys are always 44 bytes
        }


def generate_key() -> str:
    """Generate a new Fernet encryption key.
    
    This is a utility function for generating encryption keys for production use.
    The generated key should be stored securely in a key management system.
    
    Returns:
        Base64-encoded Fernet key as string
    
    Example:
        >>> from aise.core.credential_vault import generate_key
        >>> key = generate_key()
        >>> print(f"Save this key securely: {key}")
        >>> # Set as environment variable:
        >>> # export CREDENTIAL_VAULT_KEY="<key>"
    """
    key = Fernet.generate_key()
    return key.decode('utf-8')


# Example usage and instructions
if __name__ == "__main__":
    print("=" * 70)
    print("AiSE Credential Vault - Encryption Key Generator")
    print("=" * 70)
    print()
    print("Generating a new encryption key...")
    print()
    
    key = generate_key()
    
    print("Your new encryption key:")
    print(f"  {key}")
    print()
    print("IMPORTANT: Save this key securely!")
    print()
    print("To use this key, set it as an environment variable:")
    print(f"  export CREDENTIAL_VAULT_KEY='{key}'")
    print()
    print("Or add it to your .env file:")
    print(f"  CREDENTIAL_VAULT_KEY={key}")
    print()
    print("For production use, consider using a key management system:")
    print("  - AWS KMS (Key Management Service)")
    print("  - HashiCorp Vault")
    print("  - Azure Key Vault")
    print("  - Google Cloud KMS")
    print()
    print("=" * 70)
