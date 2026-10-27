import { test as base, expect } from '@playwright/test';
import { permitsLocalRequest } from './local-policy.mjs';

// Automatic fixture installs the guard before page creation. Dedicated workers
// remain real; service workers are blocked by the config. Blob downloads work.
export const test = base.extend({
  localTraffic: [async ({ context, baseURL }, use, testInfo) => {
    const traffic = { blocked: [], responses: [], workers: [] };
    await context.route('**/*', async (route) => {
      const request = route.request();
      if (permitsLocalRequest(request.url(), request.method(), baseURL)) return route.continue();
      traffic.blocked.push({ method: request.method(), url: request.url() });
      await route.abort('blockedbyclient');
    });
    await context.routeWebSocket('**/*', (socket) => {
      traffic.blocked.push({ method: 'WEBSOCKET', url: socket.url() });
      socket.close(); // Never connectToServer().
    });
    context.on('response', (response) => traffic.responses.push({
      url: response.url(), status: response.status(), type: response.headers()['content-type'] || '',
    }));
    context.on('page', (page) => page.on('worker', (worker) => traffic.workers.push(worker.url())));
    await use(traffic);
    await testInfo.attach('local-request-audit', {
      body: Buffer.from(JSON.stringify(traffic, null, 2)), contentType: 'application/json',
    });
    expect(traffic.blocked, 'No application requests may leave this test origin/project path').toEqual([]);
  }, { auto: true }],
});
export { expect };
