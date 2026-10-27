// SPDX-License-Identifier: AGPL-3.0-only
import http from 'node:http';
const req = http.get({ hostname: '127.0.0.1', port: Number(process.env.PORT ?? 10000),
  path: '/health', headers: { host: process.env.TETHERLESS_PUBLIC_HOST ?? '' }, timeout: 3000 }, res => {
  res.resume(); process.exitCode = res.statusCode === 200 ? 0 : 1;
});
req.on('error', () => { process.exitCode = 1; });
req.on('timeout', () => req.destroy());
