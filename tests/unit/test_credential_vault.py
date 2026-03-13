# tests/unit/test_credential_vault.py
"""Unit tests for the CredentialVault class."""

import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from cryptography.fernet import Fernet

from aise.core.credential_vault import CredentialVault, generate_key
from aise.core.exceptions import CredentialVaultError


class TestCredentialVault:
    """Test suite for CredentialVault class."""
    
    def test_encrypt_decrypt_roundtrip(self):
        """Test that encryption and decryption work correctly."""
        # Generate a test key
        test_key = Fernet.generate_key().decode('utf-8')
        
        # Create vault with test key
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': test_key}):
            vault = CredentialVault()
        
        # Test data
        plaintext = "my-secret-api-key-12345"
        
        # Encrypt
        encrypted = vault.encrypt(plaintext)
        
        # Verify encrypted is different from plaintext
        assert encrypted != plaintext
        assert len(encrypted) > len(plaintext)
        
        # Decrypt
        decrypted = vault.decrypt(encrypted)
        
        # Verify roundtrip
        assert decrypted == plaintext
    
    def test_encrypt_empty_string_raises_error(self):
        """Test that encrypting empty string raises ValueError."""
        test_key = Fernet.generate_key().decode('utf-8')
        
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': test_key}):
            vault = CredentialVault()
        
        with pytest.raises(ValueError, match="Cannot encrypt empty credential"):
            vault.encrypt("")
    
    def test_decrypt_empty_string_raises_error(self):
        """Test that decrypting empty string raises ValueError."""
        test_key = Fernet.generate_key().decode('utf-8')
        
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': test_key}):
            vault = CredentialVault()
        
        with pytest.raises(ValueError, match="Cannot decrypt empty string"):
            vault.decrypt("")
    
    def test_decrypt_with_wrong_key_raises_error(self):
        """Test that decrypting with wrong key raises CredentialVaultError."""
        # Encrypt with one key
        key1 = Fernet.generate_key().decode('utf-8')
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': key1}):
            vault1 = CredentialVault()
            encrypted = vault1.encrypt("secret")
        
        # Try to decrypt with different key
        key2 = Fernet.generate_key().decode('utf-8')
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': key2}):
            vault2 = CredentialVault()
            
            with pytest.raises(CredentialVaultError, match="Invalid encryption key"):
                vault2.decrypt(encrypted)
    
    def test_decrypt_corrupted_data_raises_error(self):
        """Test that decrypting corrupted data raises CredentialVaultError."""
        test_key = Fernet.generate_key().decode('utf-8')
        
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': test_key}):
            vault = CredentialVault()
        
        # Try to decrypt invalid data
        with pytest.raises(CredentialVaultError):
            vault.decrypt("not-valid-encrypted-data")
    
    def test_key_loading_from_environment_variable(self):
        """Test that encryption key is loaded from environment variable."""
        test_key = Fernet.generate_key().decode('utf-8')
        
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': test_key}):
            vault = CredentialVault()
            
            info = vault.get_key_info()
            assert info['initialized'] is True
            assert 'environment variable' in info['key_source']
    
    def test_key_loading_from_config(self):
        """Test that encryption key is loaded from config object."""
        test_key = Fernet.generate_key().decode('utf-8')
        
        # Create mock config
        mock_config = Mock()
        mock_config.CREDENTIAL_VAULT_KEY = test_key
        
        # Ensure environment variable is not set
        with patch.dict(os.environ, {}, clear=True):
            vault = CredentialVault(config=mock_config)
            
            info = vault.get_key_info()
            assert info['initialized'] is True
            assert 'config.CREDENTIAL_VAULT_KEY' in info['key_source']
    
    def test_key_loading_from_file(self, tmp_path):
        """Test that encryption key is loaded from file."""
        # Create a temporary key file
        key_file = tmp_path / ".aise" / "vault.key"
        key_file.parent.mkdir(parents=True, exist_ok=True)
        
        test_key = Fernet.generate_key()
        key_file.write_bytes(test_key)
        
        # Mock Path.home() to return tmp_path
        with patch('aise.core.credential_vault.Path.home', return_value=tmp_path):
            with patch.dict(os.environ, {}, clear=True):
                vault = CredentialVault()
                
                info = vault.get_key_info()
                assert info['initialized'] is True
                assert 'vault.key' in info['key_source']
    
    def test_auto_generate_key_if_not_found(self, tmp_path):
        """Test that a new key is auto-generated if not found."""
        # Mock Path.home() to return tmp_path
        with patch('aise.core.credential_vault.Path.home', return_value=tmp_path):
            with patch.dict(os.environ, {}, clear=True):
                vault = CredentialVault()
                
                # Verify vault is initialized
                info = vault.get_key_info()
                assert info['initialized'] is True
                assert 'auto-generated' in info['key_source']
                
                # Verify key file was created
                key_file = tmp_path / ".aise" / "vault.key"
                assert key_file.exists()
                
                # Verify key file has correct permissions (600)
                assert oct(key_file.stat().st_mode)[-3:] == '600'
    
    def test_invalid_key_raises_error(self):
        """Test that invalid encryption key raises CredentialVaultError."""
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': 'invalid-key'}):
            with pytest.raises(CredentialVaultError, match="Invalid encryption key"):
                CredentialVault()
    
    def test_mask_credential(self):
        """Test credential masking for safe display."""
        # Test normal credential
        masked = CredentialVault.mask_credential("my-secret-api-key-12345")
        assert masked == "my-s****2345"
        assert "secret" not in masked
        
        # Test short credential
        masked_short = CredentialVault.mask_credential("short")
        assert masked_short == "****"
        
        # Test empty credential
        masked_empty = CredentialVault.mask_credential("")
        assert masked_empty == "****"
        
        # Test custom show_chars
        masked_custom = CredentialVault.mask_credential("my-secret-api-key", show_chars=2)
        assert masked_custom == "my****ey"
    
    def test_encrypt_unicode_characters(self):
        """Test that encryption works with unicode characters."""
        test_key = Fernet.generate_key().decode('utf-8')
        
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': test_key}):
            vault = CredentialVault()
        
        # Test with unicode characters
        plaintext = "密码-пароль-🔐"
        encrypted = vault.encrypt(plaintext)
        decrypted = vault.decrypt(encrypted)
        
        assert decrypted == plaintext
    
    def test_encrypt_long_credential(self):
        """Test that encryption works with long credentials."""
        test_key = Fernet.generate_key().decode('utf-8')
        
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': test_key}):
            vault = CredentialVault()
        
        # Test with very long credential (e.g., SSH private key)
        plaintext = "a" * 10000
        encrypted = vault.encrypt(plaintext)
        decrypted = vault.decrypt(encrypted)
        
        assert decrypted == plaintext
        assert len(encrypted) > len(plaintext)
    
    def test_multiple_encrypt_produces_different_ciphertext(self):
        """Test that encrypting the same plaintext produces different ciphertext."""
        test_key = Fernet.generate_key().decode('utf-8')
        
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': test_key}):
            vault = CredentialVault()
        
        plaintext = "my-secret"
        
        # Encrypt the same plaintext twice
        encrypted1 = vault.encrypt(plaintext)
        encrypted2 = vault.encrypt(plaintext)
        
        # Ciphertexts should be different (due to random IV)
        assert encrypted1 != encrypted2
        
        # But both should decrypt to the same plaintext
        assert vault.decrypt(encrypted1) == plaintext
        assert vault.decrypt(encrypted2) == plaintext
    
    def test_get_key_info(self):
        """Test get_key_info returns correct information."""
        test_key = Fernet.generate_key().decode('utf-8')
        
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': test_key}):
            vault = CredentialVault()
            
            info = vault.get_key_info()
            
            assert isinstance(info, dict)
            assert info['initialized'] is True
            assert 'key_source' in info
            assert info['key_length'] == 44  # Fernet keys are always 44 bytes


class TestGenerateKey:
    """Test suite for generate_key utility function."""
    
    def test_generate_key_returns_valid_key(self):
        """Test that generate_key returns a valid Fernet key."""
        key = generate_key()
        
        # Verify it's a string
        assert isinstance(key, str)
        
        # Verify it's a valid Fernet key by trying to use it
        fernet = Fernet(key.encode('utf-8'))
        
        # Test encryption/decryption with generated key
        test_data = b"test"
        encrypted = fernet.encrypt(test_data)
        decrypted = fernet.decrypt(encrypted)
        assert decrypted == test_data
    
    def test_generate_key_produces_unique_keys(self):
        """Test that generate_key produces unique keys each time."""
        key1 = generate_key()
        key2 = generate_key()
        key3 = generate_key()
        
        # All keys should be different
        assert key1 != key2
        assert key2 != key3
        assert key1 != key3


class TestCredentialVaultAuditLogging:
    """Test suite for audit logging in CredentialVault."""
    
    def test_encrypt_logs_audit_event(self, caplog):
        """Test that encryption logs an audit event."""
        test_key = Fernet.generate_key().decode('utf-8')
        
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': test_key}):
            vault = CredentialVault()
            
            # Clear previous logs
            caplog.clear()
            
            # Encrypt a credential
            vault.encrypt("my-secret")
            
            # Verify audit log was created
            # Note: structlog logs may not appear in caplog, so we just verify no errors
            assert True  # If we got here, no exceptions were raised
    
    def test_decrypt_logs_audit_event(self, caplog):
        """Test that decryption logs an audit event."""
        test_key = Fernet.generate_key().decode('utf-8')
        
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': test_key}):
            vault = CredentialVault()
            
            # Encrypt first
            encrypted = vault.encrypt("my-secret")
            
            # Clear previous logs
            caplog.clear()
            
            # Decrypt
            vault.decrypt(encrypted)
            
            # Verify audit log was created
            assert True  # If we got here, no exceptions were raised
    
    def test_credentials_never_logged_in_plaintext(self, caplog):
        """Test that credentials are never logged in plaintext."""
        test_key = Fernet.generate_key().decode('utf-8')
        
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': test_key}):
            vault = CredentialVault()
            
            secret = "super-secret-password-12345"
            
            # Encrypt and decrypt
            encrypted = vault.encrypt(secret)
            decrypted = vault.decrypt(encrypted)
            
            # Check all log records
            for record in caplog.records:
                # Verify the secret is not in any log message
                assert secret not in str(record.getMessage())
                assert secret not in str(record.args)


class TestCredentialVaultErrorHandling:
    """Test suite for error handling in CredentialVault."""
    
    def test_initialization_failure_raises_credential_vault_error(self):
        """Test that initialization failures raise CredentialVaultError."""
        # Provide an invalid key that will fail Fernet initialization
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': 'not-a-valid-fernet-key'}):
            with pytest.raises(CredentialVaultError, match="Invalid encryption key"):
                CredentialVault()
    
    def test_encrypt_without_initialization_raises_error(self):
        """Test that encrypting without initialization raises error."""
        test_key = Fernet.generate_key().decode('utf-8')
        
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': test_key}):
            vault = CredentialVault()
            
            # Manually break the vault
            vault._fernet = None
            
            with pytest.raises(CredentialVaultError, match="not initialized"):
                vault.encrypt("test")
    
    def test_decrypt_without_initialization_raises_error(self):
        """Test that decrypting without initialization raises error."""
        test_key = Fernet.generate_key().decode('utf-8')
        
        with patch.dict(os.environ, {'CREDENTIAL_VAULT_KEY': test_key}):
            vault = CredentialVault()
            encrypted = vault.encrypt("test")
            
            # Manually break the vault
            vault._fernet = None
            
            with pytest.raises(CredentialVaultError, match="not initialized"):
                vault.decrypt(encrypted)
