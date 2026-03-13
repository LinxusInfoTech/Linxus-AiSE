# examples/credential_storage_example.py
"""Example usage of CredentialStorage for secure credential management.

This example demonstrates how to:
1. Initialize the credential storage with PostgreSQL backend
2. Store encrypted credentials
3. Retrieve and use credentials
4. List stored credentials
5. Rotate credentials
6. View audit logs
7. Clean up resources

Prerequisites:
- PostgreSQL database running (via docker-compose up postgres)
- DATABASE_URL configured in .env
- CREDENTIAL_VAULT_KEY configured in .env (or auto-generated)
"""

import asyncio
from aise.core.config import get_config
from aise.core.credential_vault import CredentialVault
from aise.core.credential_storage import CredentialStorage


async def main():
    """Demonstrate credential storage usage."""
    
    print("=" * 70)
    print("AiSE Credential Storage Example")
    print("=" * 70)
    print()
    
    # 1. Load configuration
    print("1. Loading configuration...")
    config = get_config()
    print(f"   Database URL: {config.DATABASE_URL[:30]}...")
    print()
    
    # 2. Initialize credential vault (handles encryption/decryption)
    print("2. Initializing credential vault...")
    vault = CredentialVault(config)
    key_info = vault.get_key_info()
    print(f"   Encryption key source: {key_info['key_source']}")
    print()
    
    # 3. Initialize credential storage (handles PostgreSQL persistence)
    print("3. Initializing credential storage...")
    storage = CredentialStorage(config, vault)
    await storage.initialize()
    print("   ✓ Database schema created")
    print("   ✓ Connection pool established")
    print()
    
    # 4. Store some example credentials
    print("4. Storing example credentials...")
    
    credentials = [
        ("zendesk_api_key", "zd_secret_key_12345", "api_key"),
        ("aws_access_key", "AKIAIOSFODNN7EXAMPLE", "api_key"),
        ("database_password", "super_secret_db_pass", "password"),
        ("github_token", "ghp_example_token_12345", "token"),
    ]
    
    for key, value, cred_type in credentials:
        await storage.store(key, value, cred_type, component="example_script")
        masked = CredentialVault.mask_credential(value)
        print(f"   ✓ Stored {key}: {masked}")
    print()
    
    # 5. List all stored credentials (metadata only, not values)
    print("5. Listing stored credentials...")
    keys = await storage.list_keys()
    print(f"   Found {len(keys)} credentials:")
    for cred in keys:
        print(f"   - {cred['key']}")
        print(f"     Type: {cred['credential_type']}")
        print(f"     Created: {cred['created_at']}")
        print(f"     Access count: {cred['access_count']}")
    print()
    
    # 6. Retrieve and use a credential
    print("6. Retrieving a credential...")
    zendesk_key = await storage.retrieve("zendesk_api_key", component="example_script")
    print(f"   Retrieved Zendesk API key: {CredentialVault.mask_credential(zendesk_key)}")
    print(f"   (In real usage, you would use this key to authenticate with Zendesk)")
    print()
    
    # 7. Rotate a credential
    print("7. Rotating a credential...")
    new_value = "zd_new_secret_key_67890"
    await storage.rotate_key("zendesk_api_key", new_value, component="example_script")
    print(f"   ✓ Rotated zendesk_api_key to: {CredentialVault.mask_credential(new_value)}")
    print()
    
    # 8. View audit log
    print("8. Viewing audit log...")
    audit_logs = await storage.get_audit_log(credential_key="zendesk_api_key", limit=10)
    print(f"   Found {len(audit_logs)} audit entries for zendesk_api_key:")
    for log in audit_logs:
        status = "✓" if log['success'] else "✗"
        print(f"   {status} {log['operation']} by {log['component']} at {log['timestamp']}")
    print()
    
    # 9. Delete a credential
    print("9. Deleting a credential...")
    deleted = await storage.delete("github_token", component="example_script")
    if deleted:
        print("   ✓ Deleted github_token")
    else:
        print("   ✗ github_token not found")
    print()
    
    # 10. Verify deletion
    print("10. Verifying deletion...")
    keys_after = await storage.list_keys()
    print(f"    Now have {len(keys_after)} credentials (was {len(keys)})")
    print()
    
    # 11. Clean up
    print("11. Cleaning up...")
    await storage.close()
    print("    ✓ Connection pool closed")
    print()
    
    print("=" * 70)
    print("Example completed successfully!")
    print("=" * 70)
    print()
    print("Key takeaways:")
    print("- All credentials are encrypted at rest using AES-256-GCM")
    print("- All access is audit logged for security compliance")
    print("- Credentials are only decrypted in memory when needed")
    print("- Masked values are shown in logs and UI for safety")
    print("- Encryption key can be rotated without data loss")
    print()


if __name__ == "__main__":
    asyncio.run(main())
