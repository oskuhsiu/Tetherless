// SPDX-License-Identifier: AGPL-3.0-only
// Deliberately dependency-free. This perimeter never logs requests or errors.
import http from 'node:http';
import { createHash, randomBytes, timingSafeEqual } from 'node:crypto';
import { gateCSP, gatePage, closedPreviewPage } from './gate-page.mjs';

const COOKIE = '__Host-tetherless-test';
const MAX_BODY = 32 * 1024;
const HOP = new Set(['connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
  'te', 'trailer', 'transfer-encoding', 'upgrade']);
const CALLBACK = /^\/v1\/device-enrollments\/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\/callback$/;

function fail(message) { throw new Error(message); }
export function readConfig(env = process.env, now = Date.now(), sourceCommit) {
  if (!/^[a-f0-9]{40}$/.test(sourceCommit ?? '')) fail('A valid build source commit is required');
  const origin = env.FRONTEND_ORIGIN;
  let url;
  try { url = new URL(origin); } catch { fail('FRONTEND_ORIGIN must be a canonical HTTPS origin'); }
  if (url.protocol !== 'https:' || url.origin !== origin || url.username || url.password ||
      !/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/.test(url.hostname) ||
      url.hostname === 'localhost' || /^\d+(?:\.\d+){3}$/.test(url.hostname)) {
    fail('FRONTEND_ORIGIN must be a canonical HTTPS DNS origin');
  }
  if (env.TETHERLESS_PUBLIC_HOST !== url.host) fail('Public host must exactly match HTTPS origin');
  const portText = env.PORT ?? '10000';
  const port = Number(portText);
  if (!/^\d{4,5}$/.test(portText) || port < 1024 || port > 65535 ||
      [8787, 18012, 18013, 19099].includes(port)) fail('Invalid public PORT');
  const accessMode = env.TETHERLESS_PREVIEW_ACCESS_MODE === undefined ? 'gated' : env.TETHERLESS_PREVIEW_ACCESS_MODE;
  if (!['gated', 'public'].includes(accessMode)) fail('Preview access mode must be gated or public');
  const digest = accessMode === 'gated' ? (env.TETHERLESS_TEST_ACCESS_SHA256 ?? '') : undefined;
  if (accessMode === 'gated' && !/^[a-f0-9]{64}$/.test(digest)) fail('A SHA256 test access digest is required');
  const expiryText = env.TETHERLESS_TEST_EXPIRES_AT ?? '';
  const expires = Date.parse(expiryText);
  if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(expiryText) ||
      !Number.isFinite(expires) || expires <= now || expires > now + 24 * 60 * 60 * 1000) {
    fail('An absolute UTC test expiry within the next 24 hours is required');
  }
  const frontend = env.TETHERLESS_FRONTEND_DIR;
  if (!frontend?.startsWith('/') || /[\x00-\x1f]/.test(frontend)) fail('An absolute frontend directory is required');
  return { origin, host: url.host, port, accessMode, digest: digest === undefined ? undefined : Buffer.from(digest, 'hex'), expires, frontend, sourceCommit };
}
function digest(value) { return createHash('sha256').update(value).digest(); }
function headers() {
  return { 'cache-control': 'no-store', 'x-content-type-options': 'nosniff',
    'referrer-policy': 'no-referrer', 'x-frame-options': 'DENY',
    'strict-transport-security': 'max-age=31536000' };
}
function send(res, status, error, extra = {}) {
  if (res.headersSent || res.destroyed) return;
  res.writeHead(status, { ...headers(), 'content-type': 'application/json', ...extra });
  res.end(JSON.stringify({ error }));
}
function gate(res, config, closed = false) {
  res.writeHead(closed ? 410 : 200, { ...headers(), 'content-type': 'text/html; charset=utf-8',
    'content-security-policy': gateCSP });
  res.end(config.accessMode === 'public' ? closedPreviewPage(config.sourceCommit, config.expires)
    : gatePage(config.sourceCommit, config.expires, closed));
}
function filteredHeaders(input) {
  const excluded = new Set(HOP);
  for (const name of (input.connection ?? '').split(',')) excluded.add(name.trim().toLowerCase());
  return Object.fromEntries(Object.entries(input).filter(([name]) => !excluded.has(name)));
}
function bucket(limit, period, now) {
  let tokens = limit;
  let last = now();
  return () => {
    const current = now();
    tokens = Math.min(limit, tokens + Math.max(0, current - last) * limit / period);
    last = current;
    if (tokens < 1) return false;
    tokens -= 1;
    return true;
  };
}
async function body(req, limit) {
  const declared = req.headers['content-length'];
  if (declared && (!/^\d+$/.test(declared) || Number(declared) > limit)) throw 413;
  const chunks = [];
  let size = 0;
  try {
    for await (const chunk of req) {
      size += chunk.length;
      if (size > limit) throw 413;
      chunks.push(chunk);
    }
    return Buffer.concat(chunks);
  } finally { for (const chunk of chunks) chunk.fill(0); }
}

// upstreamPort/now are explicit test-only dependency injection, never public env settings.
export function createProxy(config, { upstreamPort = 8787, now = Date.now } = {}) {
  const sessions = new Map();
  const agent = new http.Agent({ keepAlive: true, maxSockets: 16, maxFreeSockets: 2 });
  // Liveness has separate transport capacity and no public quota that can be
  // exhausted to deliberately force a platform restart of account sessions.
  const healthAgent = new http.Agent({ keepAlive: true, maxSockets: 4, maxFreeSockets: 2 });
  const permits = {
    all: bucket(240, 60000, now),
    unlock: bucket(6, 60000, now), start: bucket(3, 60000, now),
    mutate: bucket(30, 60000, now), callback: bucket(10, 60000, now),
  };
  let active = 0;
  const server = http.createServer({ maxHeaderSize: 16 * 1024, requestTimeout: 15000,
    headersTimeout: 10000, keepAliveTimeout: 5000, maxRequestsPerSocket: 100 }, (req, res) => {
    void handle(req, res).catch(() => send(res, 400, 'requestRejected'));
  });
  server.maxConnections = 64;
  server.on('clientError', (_error, socket) => { socket.end('HTTP/1.1 400 Bad Request\r\nConnection: close\r\nContent-Length: 0\r\n\r\n'); });
  server.on('upgrade', (_req, socket) => socket.destroy());
  server.on('connect', (_req, socket) => socket.destroy());
  server.on('close', () => { sessions.clear(); agent.destroy(); healthAgent.destroy(); });

  async function handle(req, res) {
    // Never trust forwarded headers for authority or abuse-limiting identity.
    if (req.headers.host !== config.host) return send(res, 403, 'hostRejected');
    if (!['GET', 'HEAD', 'POST', 'DELETE', 'OPTIONS'].includes(req.method)) return send(res, 405, 'methodRejected');
    const path = req.url;
    if (!path?.startsWith('/') || path.startsWith('//') || path.includes('?') ||
        path.includes('#') || /[\\\x00-\x20]/.test(path)) return send(res, 400, 'pathRejected');
    const health = req.method === 'GET' && path === '/health';
    if (!health && !permits.all()) return send(res, 429, 'rateLimited', { 'retry-after': '60' });
    if (!health && now() >= config.expires) {
      if (req.method === 'GET' && (path === '/' || path === '/_test/access')) return gate(res, config, true);
      return send(res, 410, 'testWindowClosed');
    }
    if (!health && active >= 16) return send(res, 503, 'busy');
    if (!health) active += 1;
    let released = false;
    const release = () => { if (!released) { released = true; if (!health) active -= 1; } };
    res.once('close', release);
    res.once('finish', release);
    req.setTimeout(15000, () => req.destroy());
    // An attacker cannot nominate these end-to-end headers as hop-by-hop.
    const connection = (req.headers.connection ?? '').toLowerCase().split(',').map(s => s.trim());
    if (connection.some(s => ['host', 'origin', 'cookie', 'authorization', 'content-length'].includes(s))) {
      return send(res, 400, 'requestRejected');
    }
    if (path === '/_test/access') {
      if (config.accessMode === 'public') {
        if (req.method !== 'GET') return send(res, 404, 'notFound');
        res.writeHead(303, { ...headers(), location: '/' });
        return res.end();
      }
      if (req.method === 'GET') return gate(res, config);
      if (req.method !== 'POST' || req.headers.origin !== config.origin ||
          req.headers['content-type']?.split(';')[0] !== 'application/x-www-form-urlencoded') {
        return send(res, 403, 'accessRejected');
      }
      if (!permits.unlock()) return send(res, 429, 'rateLimited', { 'retry-after': '60' });
      let bytes;
      try { bytes = await body(req, 256); } catch { return send(res, 413, 'bodyRejected'); }
      const form = new URLSearchParams(bytes.toString('utf8'));
      bytes.fill(0);
      const code = form.get('code') ?? '';
      if (now() >= config.expires) return send(res, 410, 'testWindowClosed');
      if (form.size !== 1 || !/^[A-Za-z0-9_-]{43}$/.test(code) ||
          !timingSafeEqual(digest(code), config.digest)) return send(res, 401, 'accessRejected');
      for (const [key, expiry] of sessions) if (expiry <= now()) sessions.delete(key);
      if (sessions.size >= 4) return send(res, 429, 'accessCapacity');
      const token = randomBytes(32).toString('base64url');
      const expiry = Math.min(config.expires, now() + 30 * 60 * 1000);
      sessions.set(digest(token).toString('hex'), expiry);
      res.writeHead(303, { ...headers(), location: '/',
        'set-cookie': `${COOKIE}=${token}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=${Math.floor((expiry - now()) / 1000)}` });
      return res.end();
    }
    let authorizedUntil = config.expires;
    const callback = req.method === 'POST' && CALLBACK.test(path) && !req.headers.origin;
    if (config.accessMode !== 'public' && !health && !callback) {
      const cookies = (req.headers.cookie ?? '').split(';').map(x => x.trim());
      const values = cookies.filter(x => x.startsWith(`${COOKIE}=`));
      const token = values.length === 1 ? values[0].slice(COOKIE.length + 1) : '';
      const expiry = /^[A-Za-z0-9_-]{43}$/.test(token) ? sessions.get(digest(token).toString('hex')) : undefined;
      if (!expiry || expiry <= now()) {
        if (path === '/' && req.method === 'GET') return gate(res, config);
        return send(res, 401, 'testAccessRequired');
      }
      authorizedUntil = Math.min(config.expires, expiry);
    }
    if (callback && !permits.callback()) return send(res, 429, 'rateLimited', { 'retry-after': '60' });
    if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method) && !permits.mutate()) return send(res, 429, 'rateLimited', { 'retry-after': '60' });
    if (req.method === 'POST' && path === '/v1/sessions' && !permits.start()) return send(res, 429, 'rateLimited', { 'retry-after': '60' });
    let bytes;
    try { bytes = await body(req, ['GET', 'HEAD', 'OPTIONS'].includes(req.method) ? 0 : MAX_BODY); }
    catch { return send(res, 413, 'bodyRejected'); }
    // Recheck after slow input: never start an operation after its gate expires.
    if (!health && now() >= authorizedUntil) { bytes.fill(0); return send(res, 410, 'testAccessExpired'); }
    // Body input is complete. Allow the unchanged backend's 120-second Apple
    // operation window plus transport overhead; never cut provisioning at 15s.
    req.setTimeout(135000, () => req.destroy());
    const outgoing = filteredHeaders(req.headers);
    for (const key of Object.keys(outgoing)) {
      if (key === 'forwarded' || key.startsWith('x-forwarded-') || key === 'expect') delete outgoing[key];
    }
    if (outgoing.cookie) {
      outgoing.cookie = outgoing.cookie.split(';').map(x => x.trim()).filter(x => !x.startsWith(`${COOKIE}=`)).join('; ');
      if (!outgoing.cookie) delete outgoing.cookie;
    }
    outgoing.host = req.headers.host; // Do not replace with the loopback host.
    outgoing['content-length'] = bytes.length;
    const upstream = http.request({ hostname: '127.0.0.1', port: upstreamPort,
      path, method: req.method, headers: outgoing, agent: health ? healthAgent : agent, timeout: health ? 2000 : 130000 }, response => {
      const downstream = filteredHeaders(response.headers);
      // Only an authenticated successful root readback proves the gate cookie
      // survived the redirect. Never trust an upstream-supplied marker.
      delete downstream['x-tetherless-test-access'];
      if (config.accessMode !== 'public' && req.method === 'GET' && path === '/' && response.statusCode === 200 && now() < authorizedUntil) {
        downstream['x-tetherless-test-access'] = 'granted';
      }
      // Preserve the frontend's own CSP rather than overriding its WASM policy.
      res.writeHead(response.statusCode ?? 502, { ...downstream, ...headers() });
      response.on('error', () => res.destroy());
      response.pipe(res);
    });
    upstream.on('timeout', () => upstream.destroy());
    upstream.on('error', () => send(res, 502, 'serviceUnavailable'));
    res.once('close', () => upstream.destroy());
    upstream.end(bytes, () => bytes.fill(0));
  }
  return server;
}
