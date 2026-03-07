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

-- Recommendations history table
CREATE TABLE IF NOT EXISTS recommendations_history (
    id SERIAL PRIMARY KEY,
    request_id UUID UNIQUE,
    job_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255),
    workspace_id VARCHAR(255),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    recommendation JSONB NOT NULL,
    explanation TEXT,
    pattern_analysis TEXT,
    risk_assessment JSONB,
    token_usage_analysis JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_cost_logs_job_id ON cost_usage_logs(job_id);
CREATE INDEX IF NOT EXISTS idx_cost_logs_timestamp ON cost_usage_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_cost_logs_date ON cost_usage_logs(DATE(timestamp));
CREATE INDEX IF NOT EXISTS idx_cost_logs_model ON cost_usage_logs(model_name);
CREATE INDEX IF NOT EXISTS idx_cost_logs_chain ON cost_usage_logs(chain_name);

CREATE INDEX IF NOT EXISTS idx_recommendations_job_id ON recommendations_history(job_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_timestamp ON recommendations_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_recommendations_request_id ON recommendations_history(request_id);

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

