/**
 * Production server for Databricks Apps (Node runtime).
 * Serves Angular static files and proxies /api to the FastAPI Databricks App.
 *
 * Uses Node built-in http/https only (no http-proxy-middleware) for CommonJS
 * compatibility on Databricks Apps Node 22.
 *
 * Env:
 *   DATABRICKS_APP_PORT — injected by Databricks Apps (preferred)
 *   PORT                — fallback for local smoke tests
 *   API_PROXY_TARGET    — base URL of the API app (no trailing slash)
 */
const express = require('express');
const path = require('path');
const http = require('http');
const https = require('https');
const { URL } = require('url');

const PORT = Number(process.env.DATBRICKS_APP_PORT || process.env.PORT || 8000);
const DIST = path.join(__dirname, 'dist', 'cluster-advisor-ui');
const API_TARGET = (process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000').replace(/\/$/, '');

const app = express();

app.use('/api', (req, res) => {
  let target;
  try {
    target = new URL(API_TARGET);
  } catch (err) {
    res.status(500).json({ detail: 'Invalid API_PROXY_TARGET', error: String(err.message) });
    return;
  }

  const lib = target.protocol === 'https:' ? https : http;
  const pathWithQuery = req.originalUrl || req.url;

  const headers = { ...req.headers, host: target.host };
  delete headers.connection;

  const proxyReq = lib.request(
    {
      hostname: target.hostname,
      port: target.port || (target.protocol === 'https:' ? 443 : 80),
      path: pathWithQuery,
      method: req.method,
      headers,
    },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
      proxyRes.pipe(res);
    }
  );

  proxyReq.on('error', (err) => {
    console.error('API proxy error:', err.message);
    if (!res.headersSent) {
      res.status(502).json({ detail: 'API unavailable', error: err.message });
    }
  });

  req.pipe(proxyReq);
});

app.use(express.static(DIST, { index: false }));

app.get('*', (_req, res) => {
  res.sendFile(path.join(DIST, 'index.html'));
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Insights Hub UI on 0.0.0.0:${PORT}; /api -> ${API_TARGET}`);
});
