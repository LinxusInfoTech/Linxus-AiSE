#!/usr/bin/env python3
"""
Validation script to demonstrate Config class functionality.
This script shows the key features without requiring full dependency installation.
"""

import os
import sys

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 80)
print("AiSE Configuration Validation")
print("=" * 80)
print()

# Check if dependencies are available
try:
    from pydantic import __version__ as pydantic_version
    from pydantic_settings import __version__ as pydantic_settings_version
    import structlog
    
    print("✓ Dependencies available:")
    print(f"  - pydantic: {pydantic_version}")
    print(f"  - pydantic-settings: {pydantic_settings_version}")
    print(f"  - structlog: {structlog.__version__}")
    print()
    
    # Try to import the Config class
    from aise.core.config import Config, load_config, get_config
    
    print("✓ Config module imported successfully")
    print()
    
    # Set up minimal required environment variables
    os.environ["POSTGRES_URL"] = "postgresql://aise:password@localhost:5432/aise"
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test1234567890abcdef"
    os.environ["LOG_LEVEL"] = "INFO"
    
    print("Testing configuration loading...")
    print()
    
    # Load configuration
    config = load_config()
    
    print("✓ Configuration loaded successfully")
    print()
    
    # Display configuration
    print("Configuration Summary:")
    print("-" * 80)
    print(f"  LLM Provider: {config.LLM_PROVIDER}")
    print(f"  Operational Mode: {config.AISE_MODE}")
    print(f"  PostgreSQL URL: {config.POSTGRES_URL}")
    print(f"  Redis URL: {config.REDIS_URL}")
    print(f"  ChromaDB: {config.CHROMA_HOST}:{config.CHROMA_PORT}")
    print(f"  Log Level: {config.LOG_LEVEL}")
    print()
    
    # Test sensitive value masking
    print("Testing sensitive value masking:")
    print("-" * 80)
    masked_key = Config.mask_sensitive_value("sk-ant-test1234567890abcdef")
    print(f"  Original: sk-ant-test1234567890abcdef")
    print(f"  Masked: {masked_key}")
    print()
    
    # Test configuration sources
    print("Configuration Sources:")
    print("-" * 80)
    sources = config.get_config_sources()
    for key in ["POSTGRES_URL", "REDIS_URL", "ANTHROPIC_API_KEY", "LLM_PROVIDER", "CHROMA_HOST"]:
        print(f"  {key}: {sources[key]}")
    print()
    
    # Test system credential detection
    print("System Credential Detection:")
    print("-" * 80)
    system_creds = config.detect_system_credentials()
    if system_creds:
        for cred_type, details in system_creds.items():
            print(f"  {cred_type.upper()}: Detected")
            if "sources" in details:
                for source in details["sources"]:
                    print(f"    - {source}")
    else:
        print("  No system credentials detected")
    print()
    
    # Test to_dict with masking
    print("Configuration Dictionary (masked):")
    print("-" * 80)
    config_dict = config.to_dict(mask_sensitive=True)
    sensitive_fields = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "POSTGRES_URL"]
    for field in sensitive_fields:
        if config_dict.get(field):
            print(f"  {field}: {config_dict[field]}")
    print()
    
    # Test get_config
    retrieved_config = get_config()
    assert retrieved_config is config, "get_config should return the same instance"
    print("✓ Global configuration instance working correctly")
    print()
    
    print("=" * 80)
    print("✓ All validation checks passed!")
    print("=" * 80)
    
except ImportError as e:
    print(f"✗ Missing dependency: {e}")
    print()
    print("To install dependencies, run:")
    print("  poetry install")
    print("  or")
    print("  pip install pydantic pydantic-settings structlog")
    sys.exit(1)
except Exception as e:
    print(f"✗ Validation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
