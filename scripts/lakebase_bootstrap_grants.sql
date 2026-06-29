-- Lakebase bootstrap: OAuth role + DDL/DML grants for Databricks Apps
--
-- Run once in Lakebase SQL Editor as a database owner (your user identity),
-- BEFORE the app can run init_database() / CREATE TABLE on startup.
--
-- IMPORTANT (private-only workspaces):
--   SQL Editor requires "Inbound Private Link for performance-intensive
--   services" (Service-Direct, port 5432). If you see:
--     "Service Direct private link not being configured"
--   see docs/LAKEBASE_POSTGRES_AND_DATABRICKS_APPS.md — Bootstrap database grants.
--
-- Alternative without SQL Editor: App → Resources → Lakebase → permission
-- "Can connect and create", then redeploy the app.
--
-- Replace placeholders:
--   <DATABRICKS_CLIENT_ID>  App service principal client ID (UUID).
--                           Same value as PGUSER / DATABRICKS_CLIENT_ID on the app.
--
-- Find it: Databricks → Apps → your app → Environment / Identity, or
--          Settings → Identity and access → Service principals → your app SP.

CREATE EXTENSION IF NOT EXISTS databricks_auth;

-- Idempotent: no-op if the OAuth role already exists.
SELECT databricks_create_role('<DATABRICKS_CLIENT_ID>', 'SERVICE_PRINCIPAL');

GRANT CONNECT ON DATABASE databricks_postgres TO "<DATABRICKS_CLIENT_ID>";
GRANT USAGE, CREATE ON SCHEMA public TO "<DATABRICKS_CLIENT_ID>";

-- After the app creates tables (first successful deploy), DML on existing objects:
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "<DATABRICKS_CLIENT_ID>";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO "<DATABRICKS_CLIENT_ID>";

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "<DATABRICKS_CLIENT_ID>";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO "<DATABRICKS_CLIENT_ID>";

-- Optional: verify grants (run as owner; replace role name)
-- SELECT has_schema_privilege('<DATABRICKS_CLIENT_ID>', 'public', 'CREATE') AS can_create_in_public;
