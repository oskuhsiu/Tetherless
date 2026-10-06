// SPDX-License-Identifier: AGPL-3.0-only
import { spawn } from 'node:child_process';
import { access, readFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { createProxy, readConfig } from './proxy.mjs';

export async function start(env = process.env) {
  // Production uses the immutable, build-generated identity, never a runtime
  // SOURCE_COMMIT value or operator-supplied repository URL. File override is
  // for local integration fixtures; do not configure it on a hosted deployment.
  const sourceFile = env.NODE_ENV === 'production' ? '/app/build-info/source-commit.txt'
    : (env.TETHERLESS_SOURCE_COMMIT_FILE ?? '/app/build-info/source-commit.txt');
  if (!sourceFile.startsWith('/')) throw new Error('Absolute source identity file is required');
  const sourceBytes = await readFile(sourceFile);
  if (sourceBytes.length > 64) throw new Error('Invalid source identity file');
  const config = readConfig(env, Date.now(), sourceBytes.toString('utf8').trim());
  const binary = env.TETHERLESS_SERVICE_BINARY ?? '/app/tetherless-web-bootstrap-service';
  if (!binary.startsWith('/')) throw new Error('Absolute backend binary is required');
  await access(binary, constants.X_OK);
  await access(`${config.frontend}/index.html`, constants.R_OK);
  // Discard all backend output; no inherited cloud secrets or proxy gate digest.
  const child = spawn(binary, [], { stdio: 'ignore', env: {
    PATH: '/usr/local/bin:/usr/bin:/bin', LANG: 'C.UTF-8',
    FRONTEND_ORIGIN: config.origin, TETHERLESS_PUBLIC_HOST: config.host,
    TETHERLESS_FRONTEND_DIR: config.frontend, TETHERLESS_BIND: '127.0.0.1:8787',
    RUST_BACKTRACE: '0',
  } });
  let stopping = false;
  let failed = false;
  let server;
  let killTimer;
  const stop = (failure = false) => {
    if (stopping) return;
    stopping = true;
    process.exitCode = failure ? 1 : 0;
    server?.close();
    // The unchanged Rust backend listens for SIGINT and cancels in-memory sessions.
    child.kill('SIGINT');
    killTimer = setTimeout(() => { server?.closeAllConnections(); child.kill('SIGKILL'); }, 10000);
    killTimer.unref();
  };
  child.once('error', () => { failed = true; stop(true); });
  child.once('exit', () => {
    failed = true;
    if (!stopping) { process.stderr.write('Account service stopped; process will not restart it.\n'); stop(true); }
    clearTimeout(killTimer);
    server?.closeAllConnections();
  });
  process.once('SIGTERM', () => stop());
  process.once('SIGINT', () => stop());
  try {
    let ready = false;
    for (let attempt = 0; attempt < 100 && !stopping && !failed; attempt += 1) {
      ready = await new Promise(resolve => {
        const req = http.get({ hostname: '127.0.0.1', port: 8787, path: '/health',
          headers: { host: config.host }, timeout: 250 }, response => {
          response.resume(); resolve(response.statusCode === 200);
        });
        req.on('timeout', () => { req.destroy(); });
        req.on('error', () => resolve(false));
      });
      if (ready) break;
      await new Promise(resolve => setTimeout(resolve, 250));
    }
    if (!ready || failed || stopping) throw new Error('Backend readiness failed');
    server = createProxy(config);
    server.once('error', () => stop(true));
    await new Promise((resolve, reject) => {
      server.once('error', reject);
      server.listen(config.port, '0.0.0.0', resolve);
    });
    process.stdout.write('Tetherless bounded test service ready. Request logging is disabled.\n');
    return { server, child, stop };
  } catch {
    stop(true);
    throw new Error('Service startup failed');
  }
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  start().catch(() => {
    process.stderr.write('Service startup failed; check required deployment configuration.\n');
    process.exitCode = 1;
  });
}
