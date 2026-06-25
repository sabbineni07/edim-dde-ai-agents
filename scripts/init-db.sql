-- Initialize database schema for EDIM DDE AI Agents

-- Cost and usage tracking tables
CREATE TABLE IF NOT EXISTS cost_usage_logs (
    id SERIAL PRIMARY KEY,
    request_id UUID,
    job_id VARCHAR(255),
    user_id VARCHAR(255),
    workspace_id VARCHAR(255),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    model_name VARCHAR(50) NOT NULL,
    chain_name VARCHAR(50) NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL,
    cost_usd DECIMAL(10, 6) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Daily cost summary table (for performance)
CREATE TABLE IF NOT EXISTS daily_cost_summary (
    date DATE PRIMARY KEY,
    total_requests INTEGER DEFAULT 0,
    total_tokens BIGINT DEFAULT 0,
    total_cost_usd DECIMAL(10, 2) DEFAULT 0,
    avg_cost_per_request DECIMAL(10, 6) DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Request logs table (one row per API request, success or failure; generic across endpoints)
CREATE TABLE IF NOT EXISTS request_logs (
    id SERIAL PRIMARY KEY,
    request_id UUID UNIQUE,
    endpoint VARCHAR(255) NOT NULL,
    request_params JSONB NOT NULL DEFAULT '{}',
    job_id VARCHAR(255),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) NOT NULL,
    duration_ms INTEGER,
    error_code VARCHAR(100),
    error_message TEXT,
    user_id VARCHAR(255),
    workspace_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_request_logs_endpoint ON request_logs(endpoint);
CREATE INDEX IF NOT EXISTS idx_request_logs_job_id ON request_logs(job_id);
CREATE INDEX IF NOT EXISTS idx_request_logs_timestamp ON request_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_request_logs_status ON request_logs(status);
CREATE INDEX IF NOT EXISTS idx_request_logs_request_id ON request_logs(request_id);

-- Recommendations history table (request_log_request_id references request_logs.request_id)
CREATE TABLE IF NOT EXISTS recommendations_history (
    id SERIAL PRIMARY KEY,
    request_id UUID UNIQUE,
    request_log_request_id UUID REFERENCES request_logs(request_id),
    job_id VARCHAR(255) NOT NULL,
    job_run_id VARCHAR(255),
    user_id VARCHAR(255),
    workspace_id VARCHAR(255),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    recommendation JSONB NOT NULL,
    explanation TEXT,
    pattern_analysis TEXT,
    risk_assessment JSONB,
    token_usage_analysis JSONB,
    comparison JSONB,
    reason_codes JSONB,
    lifecycle_status VARCHAR(64) DEFAULT 'RECOMMENDED',
    lifecycle_updated_at TIMESTAMP,
    lifecycle_updated_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Recommendation lifecycle audit (Phase 5.4)
CREATE TABLE IF NOT EXISTS recommendation_lifecycle_events (
    id SERIAL PRIMARY KEY,
    request_id UUID NOT NULL REFERENCES recommendations_history(request_id),
    from_status VARCHAR(64),
    to_status VARCHAR(64) NOT NULL,
    changed_by VARCHAR(255) NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_lifecycle_events_request_id ON recommendation_lifecycle_events(request_id);
CREATE INDEX IF NOT EXISTS idx_lifecycle_events_changed_at ON recommendation_lifecycle_events(changed_at);

-- Workspace connections & agents (Phase 10)
CREATE TABLE IF NOT EXISTS workspace_connections (
    id UUID PRIMARY KEY,
    workspace_id VARCHAR(255) NOT NULL,
    workspace_name VARCHAR(512),
    connection_type VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_workspace_connections_workspace_id ON workspace_connections(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_connections_type ON workspace_connections(connection_type);

CREATE TABLE IF NOT EXISTS workspace_agents (
    id UUID PRIMARY KEY,
    workspace_id VARCHAR(255) NOT NULL,
    workspace_name VARCHAR(512),
    agent_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    bindings JSONB NOT NULL DEFAULT '{}',
    agent_settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_workspace_agents_workspace_id ON workspace_agents(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_agents_agent_id ON workspace_agents(agent_id);

CREATE TABLE IF NOT EXISTS platform_environments (
    id VARCHAR(64) PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    display_name VARCHAR(255) NOT NULL,
    description TEXT,
    environment_tier VARCHAR(32) NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    catalog_name VARCHAR(255),
    schema_name VARCHAR(255),
    table_name VARCHAR(255),
    databricks_server_hostname VARCHAR(512),
    databricks_http_path VARCHAR(512),
    default_metrics_connection_id UUID,
    default_llm_connection_id UUID,
    sort_order INTEGER NOT NULL DEFAULT 0,
    icon VARCHAR(64) NOT NULL DEFAULT 'cloud',
    is_enabled INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_platform_environments_tier ON platform_environments(environment_tier);
CREATE INDEX IF NOT EXISTS idx_platform_environments_source ON platform_environments(source_type);

CREATE TABLE IF NOT EXISTS environment_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment_id VARCHAR(64) NOT NULL REFERENCES platform_environments(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    connection_type VARCHAR(64) NOT NULL,
    purpose VARCHAR(32) NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_environment_connections_env ON environment_connections(environment_id);
CREATE INDEX IF NOT EXISTS idx_environment_connections_purpose ON environment_connections(environment_id, purpose);

CREATE UNIQUE INDEX IF NOT EXISTS idx_environment_connections_default
    ON environment_connections(environment_id, purpose)
    WHERE is_default = TRUE;

CREATE TABLE IF NOT EXISTS environment_datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment_id VARCHAR(64) NOT NULL REFERENCES platform_environments(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    source_type VARCHAR(32) NOT NULL,
    table_fqn VARCHAR(512),
    local_path VARCHAR(1024),
    schema_profile VARCHAR(64) NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_environment_datasets_env ON environment_datasets(environment_id);
CREATE INDEX IF NOT EXISTS idx_environment_datasets_profile ON environment_datasets(schema_profile);

CREATE UNIQUE INDEX IF NOT EXISTS idx_environment_datasets_default
    ON environment_datasets(environment_id)
    WHERE is_default = TRUE;

ALTER TABLE platform_environments
    DROP CONSTRAINT IF EXISTS platform_environments_default_metrics_connection_id_fkey;
ALTER TABLE platform_environments
    ADD CONSTRAINT platform_environments_default_metrics_connection_id_fkey
    FOREIGN KEY (default_metrics_connection_id) REFERENCES environment_connections(id) ON DELETE SET NULL;

ALTER TABLE platform_environments
    DROP CONSTRAINT IF EXISTS platform_environments_default_llm_connection_id_fkey;
ALTER TABLE platform_environments
    ADD CONSTRAINT platform_environments_default_llm_connection_id_fkey
    FOREIGN KEY (default_llm_connection_id) REFERENCES environment_connections(id) ON DELETE SET NULL;

ALTER TABLE platform_environments
    DROP CONSTRAINT IF EXISTS platform_environments_default_dataset_id_fkey;
ALTER TABLE platform_environments
    ADD COLUMN IF NOT EXISTS default_dataset_id UUID;
ALTER TABLE platform_environments
    ADD CONSTRAINT platform_environments_default_dataset_id_fkey
    FOREIGN KEY (default_dataset_id) REFERENCES environment_datasets(id) ON DELETE SET NULL;

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_cost_logs_job_id ON cost_usage_logs(job_id);
CREATE INDEX IF NOT EXISTS idx_cost_logs_timestamp ON cost_usage_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_cost_logs_date ON cost_usage_logs(DATE(timestamp));
CREATE INDEX IF NOT EXISTS idx_cost_logs_model ON cost_usage_logs(model_name);
CREATE INDEX IF NOT EXISTS idx_cost_logs_chain ON cost_usage_logs(chain_name);

CREATE INDEX IF NOT EXISTS idx_recommendations_job_id ON recommendations_history(job_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_job_run_id ON recommendations_history(job_run_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_lifecycle_status ON recommendations_history(lifecycle_status);
CREATE INDEX IF NOT EXISTS idx_recommendations_timestamp ON recommendations_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_recommendations_request_id ON recommendations_history(request_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_request_log_request_id ON recommendations_history(request_log_request_id);

-- Function to update daily summary
CREATE OR REPLACE FUNCTION update_daily_cost_summary()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO daily_cost_summary (date, total_requests, total_tokens, total_cost_usd, avg_cost_per_request)
    VALUES (
        DATE(NEW.timestamp),
        1,
        NEW.total_tokens,
        NEW.cost_usd,
        NEW.cost_usd
    )
    ON CONFLICT (date) DO UPDATE
    SET
        total_requests = daily_cost_summary.total_requests + 1,
        total_tokens = daily_cost_summary.total_tokens + NEW.total_tokens,
        total_cost_usd = daily_cost_summary.total_cost_usd + NEW.cost_usd,
        avg_cost_per_request = (daily_cost_summary.total_cost_usd + NEW.cost_usd) / (daily_cost_summary.total_requests + 1),
        updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update daily summary
DROP TRIGGER IF EXISTS trigger_update_daily_summary ON cost_usage_logs;
CREATE TRIGGER trigger_update_daily_summary
    AFTER INSERT ON cost_usage_logs
    FOR EACH ROW
    EXECUTE FUNCTION update_daily_cost_summary();

