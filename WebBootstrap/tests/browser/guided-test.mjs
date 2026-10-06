import { test as base, expect } from '@playwright/test';
import { permitsLocalRequest } from './local-policy.mjs';
import { createGuidedService, guidedApiPath } from './guided-service.mjs';
// Separate fixture. The static suite's deny-all-mutations policy is unchanged.
export const test = base.extend({
  guidedApp: ['synthetic', { option: true }],
  guided: [async ({ context, baseURL, guidedApp }, use, testInfo) => {
    const service = createGuidedService(guidedApp); const workers = [], responses = [], completed = [];
    await context.route('**/*', async (route) => {
      const req = route.request(), api = guidedApiPath(req.url(), req.method(), baseURL);
      if (api) {
        let data;
        try { data = await service.handle(api, req.method(), req.postData() || '', req.headers().authorization); }
        catch (error) { service.blocked.push({ method: req.method(), path: api, reason: 'Synthetic contract rejected' }); await route.abort('blockedbyclient'); return; }
        // A cancelled test request may have disappeared while its response was held.
        try { await route.fulfill({ status: data.status || 200, contentType: 'application/json', body: JSON.stringify(data) }); } catch (error) { if (!req.failure()) throw error; } finally { completed.push({ path: api, method: req.method() }); }
        return;
      }
      // Only static local GET/HEAD may reach the preview server. Unknown API
      // routes never fall through, even if they happen to use GET.
      const url = new URL(req.url());
      if (!url.pathname.includes('/v1/') && permitsLocalRequest(req.url(), req.method(), baseURL)) return route.continue();
      service.blocked.push({ method: req.method(), url: req.url() }); await route.abort('blockedbyclient');
    });
    await context.routeWebSocket('**/*', socket => { service.blocked.push({ method: 'WEBSOCKET', url: socket.url() }); socket.close(); });
    context.on('page', page => page.on('worker', worker => workers.push(worker.url())));
    context.on('response', response => responses.push({ url: response.url(), status: response.status() }));
    await use(Object.assign(service, { workers, responses, completed }));
    await testInfo.attach('synthetic-guided-request-audit', { body: Buffer.from(JSON.stringify({ calls: service.calls, blocked: service.blocked, workers, responses, completed }, null, 2)), contentType: 'application/json' });
    expect(service.blocked, 'Guided fixture permits only exact local synthetic APIs and local static assets').toEqual([]);
  }, { auto: true }],
});
export { expect };
