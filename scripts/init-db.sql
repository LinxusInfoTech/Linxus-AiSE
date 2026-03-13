-- scripts/init-db.sql
-- Database initialization script for AiSE
-- This script is automatically run when PostgreSQL container starts

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search

-- Create credentials table (managed by CredentialStorage)
CREATE TABLE IF NOT EXISTS credentials (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) UNIQUE NOT NULL,
    encrypted_value TEXT NOT NULL,
    credential_type VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    accessed_at TIMESTAMP,
    access_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_credentials_key ON credentials(key);

-- Create credential audit log table
CREATE TABLE IF NOT EXISTS credential_audit_log (
    id SERIAL PRIMARY KEY,
    credential_key VARCHAR(255) NOT NULL,
    operation VARCHAR(50) NOT NULL,
    component VARCHAR(100),
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    success BOOLEAN NOT NULL,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON credential_audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_key ON credential_audit_log(credential_key);

-- Create conversation memory table (for ticket threads)
CREATE TABLE IF NOT EXISTS conversation_memory (
    id SERIAL PRIMARY KEY,
    ticket_id VARCHAR(255) NOT NULL,
    message_id VARCHAR(255) NOT NULL UNIQUE,
    author VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    is_customer BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_conversation_ticket_id ON conversation_memory(ticket_id);
CREATE INDEX IF NOT EXISTS idx_conversation_created_at ON conversation_memory(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversation_message_id ON conversation_memory(message_id);

-- Create documentation metadata table (for knowledge persistence)
CREATE TABLE IF NOT EXISTS documentation_metadata (
    id SERIAL PRIMARY KEY,
    source_name VARCHAR(255) NOT NULL,
    source_url TEXT NOT NULL,
    crawl_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    chunk_count INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER,
    status VARCHAR(50) NOT NULL DEFAULT 'completed',
    error_message TEXT,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_doc_source_name ON documentation_metadata(source_name);
CREATE INDEX IF NOT EXISTS idx_doc_crawl_timestamp ON documentation_metadata(crawl_timestamp DESC);

-- Create configuration table (for Config_UI persistence)
CREATE TABLE IF NOT EXISTS configuration (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) UNIQUE NOT NULL,
    value TEXT,
    value_type VARCHAR(50) NOT NULL DEFAULT 'string',
    description TEXT,
    is_sensitive BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_config_key ON configuration(key);

-- Create audit log table (for security events)
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    user_id VARCHAR(255),
    component VARCHAR(100),
    action VARCHAR(255) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    details JSONB,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_user_id ON audit_log(user_id);

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO aise;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO aise;

-- Insert initial configuration (optional defaults)
INSERT INTO configuration (key, value, value_type, description, is_sensitive)
VALUES 
    ('AISE_MODE', 'approval', 'string', 'Operational mode: interactive, approval, or autonomous', FALSE),
    ('LOG_LEVEL', 'INFO', 'string', 'Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL', FALSE),
    ('MAX_CONCURRENT_TOOLS', '5', 'integer', 'Maximum number of concurrent tool executions', FALSE),
    ('TOOL_EXECUTION_TIMEOUT', '30', 'integer', 'Tool execution timeout in seconds', FALSE)
ON CONFLICT (key) DO NOTHING;

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at
CREATE TRIGGER update_credentials_updated_at BEFORE UPDATE ON credentials
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_configuration_updated_at BEFORE UPDATE ON configuration
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Log initialization
DO $$
BEGIN
    RAISE NOTICE 'AiSE database schema initialized successfully';
END $$;
