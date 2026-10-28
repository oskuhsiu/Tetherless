// Local synthetic HTTP faults only. No proxy, credentials, or outbound traffic.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
const health = JSON.stringify({ protocol: 1, certificateLifecycle: 1, appleAuthAvailable: true, profileServiceAvailable: true });
export function createDiscoveryFixture() {
  const cases = new Map(); let next = 0, redirected = 0;
  const server = createServer(async (req, res) => {
    const path = new URL(req.url, 'http://localhost').pathname;
    res.setHeader('Cache-Control', 'no-store');
    if (req.method !== 'GET') { res.writeHead(405); return res.end(); }
    if (path === '/' || path === '/blocked') { res.setHeader('Content-Type', 'text/html'); res.setHeader('Content-Security-Policy', `default-src 'self'; script-src 'self'; connect-src ${path === '/blocked' ? "'none'" : "'self'"}`); return res.end('<!doctype html><title>Local discovery transport fixture</title>'); }
    if (['/src/account-discovery.js', '/src/ota.js'].includes(path)) {
      res.setHeader('Content-Type', 'text/javascript'); return res.end(await readFile(new URL(`../../${path.slice(1)}`, import.meta.url)));
    }
    if (path === '/redirect-target') { redirected++; res.setHeader('Content-Type', 'application/json'); return res.end(health); }
    const match = /^\/case\/(\d+)\/(health|config.json)$/.exec(path), entry = match && cases.get(match[1]);
    if (!entry) { res.writeHead(404); return res.end(); }
    if (match[2] === 'config.json') { entry.config++; res.setHeader('Content-Type', 'application/json'); return res.end('{}'); }
    entry.calls++;
    if (entry.mode.startsWith('redirect')) {
      res.writeHead(entry.status, { Location: entry.mode === 'redirect-foreign' ? `http://localhost:${server.address().port}/redirect-target` : '/redirect-target' }); return res.end();
    }
    res.setHeader('Content-Type', 'application/json');
    if (entry.mode === 'truncated') return res.end('{"protocol":');
    if (entry.mode === 'oversized') return res.end(' '.repeat(16385));
    if (entry.mode === 'interrupted' || (entry.mode === 'interrupted-first' && entry.calls === 1)) {
      res.writeHead(200); res.write('{"protocol":'); entry.headers++;
      const timer = setTimeout(() => res.destroy(), 60); res.on('close', () => clearTimeout(timer)); return;
    }
    if (entry.mode === 'delayed' || (entry.mode === 'delayed-first' && entry.calls === 1)) {
      const timer = setTimeout(() => res.end(health), 250); res.on('close', () => clearTimeout(timer)); return;
    }
    return res.end(health);
  });
  return {
    server,
    async start() { await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); return `http://127.0.0.1:${server.address().port}`; },
    add(mode, status = 302) { const id = String(++next); const entry = { mode, status, calls: 0, config: 0, headers: 0 }; cases.set(id, entry); return { path: `/case/${id}/`, entry }; },
    get redirected() { return redirected; },
    async close() { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); },
  };
}
