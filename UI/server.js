/**
 * Production server for Databricks Apps (Node runtime).
 * Serves Angular static files and proxies /api to the FastAPI Databricks App.
 *
 * Databricks Apps auth: the API app URL requires a valid Bearer token. The Angular
 * stub login sends Authorization: Bearer stub-token-* which causes 401. This proxy:
 *   1. Forwards x-forwarded-access-token (user OAuth from Databricks gateway)
 *   2. Else uses the UI app's service principal (M2M) when DATABRICKS_* env is set
 *   3. Else forwards client Authorization only if it is not a stub token (local dev)
 *
 * Grant the UI app's DATABRICKS_CLIENT_ID **CAN USE** on the API Databricks App.
 *
 * Env:
 *   DATABRICKS_APP_PORT — injected by Databricks Apps (preferred)
 *   PORT                — fallback for local smoke tests
 *   API_PROXY_TARGET    — base URL of the API app (no trailing slash)
 *   DATABRICKS_HOST, DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET — injected on Apps
 */
const express = require('express');
const path = require('path');
const http = require('http');
const https = require('https');
const { URL } = require('url');

const PORT = Number(process.env.DATBRICKS_APP_PORT || process.env.PORT || 8000);
const DIST = path.join(__dirname, 'dist', 'cluster-advisor-ui');
const API_TARGET = (process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000').replace(/\/$/, '');

/** @type {{ token: string | null, expiresAt: number }} */
const m2mCache = { token: null, expiresAt: 0 };

const app = express();

function headerValue(req, name) {
  const v = req.headers[name.toLowerCase()];
  if (Array.isArray(v)) return v[0];
  return v;
}

function isStubAuth(auth) {
  return !!auth && /^Bearer\s+stub-token-/i.test(String(auth));
}

function fetchM2MToken() {
  const now = Date.now();
  if (m2mCache.token && m2mCache.expiresAt > now + 60_000) {
    return Promise.resolve(m2mCache.token);
  }

  const host = (process.env.DATBRICKS_HOST || '').replace(/\/$/, '');
  const clientId = process.env.DATBRICKS_CLIENT_ID;
  const clientSecret = process.env.DATBRICKS_CLIENT_SECRET;
  if (!host || !clientId || !clientSecret) {
    return Promise.resolve(null);
  }

  const tokenUrl = new URL('/oidc/v1/token', host);
  const body = 'grant_type=client_credentials&scope=all-apis';
  const basic = Buffer.from(`${clientId}:${clientSecret}`).toString('base64');

  return new Promise((resolve, reject) => {
    const reqOpts = {
      hostname: tokenUrl.hostname,
      port: tokenUrl.port || 443,
      path: `${tokenUrl.pathname}${tokenUrl.search}`,
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        Authorization: `Basic ${basic}`,
        'Content-Length': Buffer.byteLength(body),
      },
    };

    const tokenReq = https.request(reqOpts, (tokenRes) => {
      let data = '';
      tokenRes.on('data', (chunk) => {
        data += chunk;
      });
      tokenRes.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (!parsed.access_token) {
            reject(new Error(`M2M token response missing access_token: ${data.slice(0, 200)}`));
            return;
          }
          m2mCache.token = parsed.access_token;
          m2mCache.expiresAt = now + (Number(parsed.expires_in) || 3600) * 1000;
          resolve(parsed.access_token);
        } catch (err) {
          reject(err);
        }
      });
    });

    tokenReq.on('error', reject);
    tokenReq.write(body);
    tokenReq.end();
  });
}

async function buildProxyHeaders(req, targetHost) {
  const headers = { ...req.headers, host: targetHost };
  delete headers.connection;
  delete headers.authorization;

  const userToken = headerValue(req, 'x-forwarded-access-token');
  const clientAuth = headerValue(req, 'authorization');

  if (userToken) {
    headers.authorization = `Bearer ${userToken}`;
  } else if (clientAuth && !isStubAuth(clientAuth)) {
    headers.authorization = clientAuth;
  } else if (process.env.DATABRICKS_CLIENT_ID) {
    const m2m = await fetchM2MToken();
    if (m2m) {
      headers.authorization = `Bearer ${m2m}`;
    }
  }

  return headers;
}

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

  buildProxyHeaders(req, target.host)
    .then((headers) => {
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
    })
    .catch((err) => {
      console.error('Proxy auth error:', err.message);
      if (!res.headersSent) {
        res.status(500).json({ detail: 'Proxy auth failed', error: err.message });
      }
    });
});

app.use(express.static(DIST, { index: false }));

app.get('*', (_req, res) => {
  res.sendFile(path.join(DIST, 'index.html'));
});

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Insights Hub UI on 0.0.0.0:${PORT}; /api -> ${API_TARGET}`);
});
