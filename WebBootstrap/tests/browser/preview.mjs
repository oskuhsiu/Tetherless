// Test-only static preview. No proxy, SPA fallback, service, or outbound requests.
import { createServer } from 'node:http';
import { readFile, realpath } from 'node:fs/promises';
import { extname, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const dist = fileURLToPath(new URL('../../dist/', import.meta.url));
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.wasm': 'application/wasm', '.txt': 'text/plain; charset=utf-8', '.md': 'text/plain; charset=utf-8' };
const response = (status, body = '', type = 'text/plain; charset=utf-8') => ({
  status,
  headers: { 'Content-Type': type, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' },
  body,
});

// Importing this function for offline tests never opens a socket.
export async function staticResponse(rawUrl, method = 'GET', root = dist) {
  if (!['GET', 'HEAD'].includes(method)) return response(405, 'Method not allowed');
  let pathname;
  try { pathname = decodeURIComponent(new URL(rawUrl, 'http://127.0.0.1:4173').pathname); }
  catch { return response(400, 'Invalid URL'); }
  if (pathname.includes('\\') || pathname.includes('\0') || pathname.split('/').includes('..')) return response(400, 'Invalid path');
  if (pathname === '/Tetherless') return { ...response(308), headers: { Location: '/Tetherless/', 'Cache-Control': 'no-store' } };
  const relative = pathname.startsWith('/Tetherless/') ? pathname.slice('/Tetherless/'.length) : pathname.slice(1);
  try {
    const rootPath = await realpath(root);
    const file = await realpath(resolve(rootPath, relative || 'index.html'));
    if (!file.startsWith(rootPath + sep)) return response(403, 'Outside preview root');
    const body = await readFile(file);
    return response(200, method === 'HEAD' ? '' : body, types[extname(file)] || 'application/octet-stream');
  } catch (error) {
    if (['ENOENT', 'ENOTDIR', 'EISDIR'].includes(error.code)) return response(404, 'Not found');
    throw error;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await readFile(resolve(dist, 'index.html')); // Fail immediately if the build is missing.
  const server = createServer(async (request, reply) => {
    try {
      const result = await staticResponse(request.url, request.method);
      reply.writeHead(result.status, result.headers);
      reply.end(result.body);
    } catch {
      reply.writeHead(500, { 'Content-Type': 'text/plain' });
      reply.end('Preview read failed');
    }
  });
  server.listen(4173, '127.0.0.1');
  process.once('SIGTERM', () => server.close(() => process.exit(0)));
  process.once('SIGINT', () => server.close(() => process.exit(0)));
}
