/**
 * Production server for Databricks Apps (Node runtime).
 * Serves Angular static files and proxies /api to the FastAPI Databricks App.
 *
 * Env:
 *   DATABRICKS_APP_PORT — injected by Databricks Apps (preferred)
 *   PORT                — fallback for local smoke tests
 *   API_PROXY_TARGET    — base URL of the API app (no trailing slash), e.g.
 *                         https://edim-dde-ai-agents-api-xxxx.databricksapps.com
 */
const express = require('express');
const path = require('path');
const { createProxyMiddleware } = require('http-proxy-middleware');

const PORT = Number(process.env.DATBRICKS_APP_PORT || process.env.PORT || 8000);
const DIST = path.join(__dirname, 'dist', 'cluster-advisor-ui');
const API_TARGET = (process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000').replace(/\/$/, '');

const app = express();

app.use(
  '/api',
  createProxyMiddleware({
    target: API_TARGET,
    changeOrigin: true,
    secure: true,
    logLevel: 'warn',
  })
);

app.use(express.static(DIST, { index: false }));

app.get('*', (_req, res) => {
  res.sendFile(path.join(DIST, 'index.html'));
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Insights Hub UI on 0.0.0.0:${PORT}; /api -> ${API_TARGET}`);
});
