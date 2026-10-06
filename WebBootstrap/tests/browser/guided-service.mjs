// Synthetic in-process responses only. This is not an Apple implementation.
import assert from 'node:assert/strict';
import forge from 'node-forge';
export const SYNTHETIC = Object.freeze({ appleId: 'browser-test@example.invalid', password: 'not-a-real-password', code: '123456', teamId: 'TESTTEAM01', udid: '00000000-0000000000000000', bundleId: 'org.tetherless.TestFixture' });
export function syntheticProvision(csrPem) {
  assert.equal(typeof csrPem, 'string'); assert(csrPem.length < 8192);
  assert(!csrPem.includes('PRIVATE KEY'));
  const csr = forge.pki.certificationRequestFromPem(csrPem); assert(csr.verify());
  assert.equal(csr.subject.getField('CN').value, 'Tetherless browser signing');
  const issuerKeys = forge.pki.rsa.generateKeyPair(2048);
  const issuer = forge.pki.createCertificate(); issuer.publicKey = issuerKeys.publicKey; issuer.serialNumber = '01'; issuer.validity.notBefore = new Date('2020-01-01Z'); issuer.validity.notAfter = new Date('2035-01-01Z'); issuer.setSubject([{ name: 'commonName', value: 'SYNTHETIC TEST CA NOT APPLE' }]); issuer.setIssuer(issuer.subject.attributes); issuer.sign(issuerKeys.privateKey, forge.md.sha256.create());
  const cert = forge.pki.createCertificate(); cert.publicKey = csr.publicKey; cert.serialNumber = '02'; cert.validity.notBefore = new Date('2020-01-01Z'); cert.validity.notAfter = new Date('2035-01-01Z'); cert.setSubject([{ name: 'commonName', value: 'SYNTHETIC BROWSER SIGNING NOT APPLE' }, { name: 'organizationalUnitName', value: SYNTHETIC.teamId }]); cert.setIssuer(issuer.subject.attributes); cert.sign(issuerKeys.privateKey, forge.md.sha256.create());
  const der = forge.asn1.toDer(forge.pki.certificateToAsn1(cert)).getBytes();
  const xml = `<?xml version="1.0"?><plist version="1.0"><dict><key>Name</key><string>Synthetic browser profile NOT APPLE</string><key>UUID</key><string>00000000-1111-2222-3333-444444444444</string><key>ExpirationDate</key><date>2035-01-01T00:00:00Z</date><key>TeamIdentifier</key><array><string>${SYNTHETIC.teamId}</string></array><key>ApplicationIdentifierPrefix</key><array><string>${SYNTHETIC.teamId}</string></array><key>ProvisionedDevices</key><array><string>${SYNTHETIC.udid}</string></array><key>LocalProvision</key><true/><key>DeveloperCertificates</key><array><data>${forge.util.encode64(der)}</data></array><key>Entitlements</key><dict><key>application-identifier</key><string>${SYNTHETIC.teamId}.${SYNTHETIC.bundleId}</string><key>com.apple.developer.team-identifier</key><string>${SYNTHETIC.teamId}</string><key>get-task-allow</key><true/></dict></dict></plist>`;
  const cms = forge.pkcs7.createSignedData(); cms.content = forge.util.createBuffer(xml, 'utf8'); cms.addCertificate(issuer); cms.addSigner({ key: issuerKeys.privateKey, certificate: issuer, digestAlgorithm: forge.pki.oids.sha256 }); cms.sign();
  const profile = Buffer.from(forge.asn1.toDer(cms.toAsn1()).getBytes(), 'binary');
  return { response: { certificateDerBase64: forge.util.encode64(der), profiles: [{ profileBase64: profile.toString('base64') }] }, profile };
}
export function guidedApiPath(raw, method, baseURL) {
  try {
    const url = new URL(raw), base = new URL(baseURL);
    if (url.origin !== base.origin || url.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(url.hostname) || url.username || url.password || url.search || url.hash || !url.pathname.startsWith(base.pathname)) return null;
    const path = url.pathname.slice(base.pathname.length);
    if (method === 'GET' && ['health', 'config.json'].includes(path)) return path;
    if (method === 'POST' && path === 'v1/sessions') return path;
    if (/^v1\/sessions\/synthetic-session-[1-9][0-9]?$/.test(path) && ['GET', 'DELETE'].includes(method)) return path;
    if (/^v1\/sessions\/synthetic-session-[1-9][0-9]?\/teams\/[A-Za-z0-9]{1,64}\/devices$/.test(path) && method === 'GET') return path;
    if (/^v1\/sessions\/synthetic-session-[1-9][0-9]?\/teams$/.test(path) && method === 'GET') return path;
    if (/^v1\/sessions\/synthetic-session-[1-9][0-9]?\/(2fa|provision)$/.test(path) && method === 'POST') return path;
    return null;
  } catch { return null; }
}
export function createGuidedService() {
  const sessions = new Map(), holds = new Map(); let counter = 0;
  const service = { teams: [{ id: SYNTHETIC.teamId, name: 'Synthetic Personal Team', type: 'personal' }], deviceLists: new Map([[SYNTHETIC.teamId, [{ udid: SYNTHETIC.udid, name: 'My iPhone', status: 'active', selectable: true }]]]), failNextDevices: false, calls: [], blocked: [], profiles: [], provisioningBodies: [], failNextProvision: false,
    holdNext(name) { assert(!holds.has(name)); let enter, release; const entered = new Promise(r => enter = r), wait = new Promise(r => release = r); holds.set(name, { enter, wait }); return { entered, release }; },
    async handle(path, method, text, authorization) {
      assert(text.length <= 32 * 1024); const body = text ? JSON.parse(text) : {};
      const name = path.endsWith('/devices') ? `devices:${path.split('/')[4]}` : path === 'v1/sessions' ? 'login' : path.endsWith('/provision') ? 'provision' : path.endsWith('/2fa') ? 'twoFactor' : path;
      service.calls.push({ path, method, name }); let response;
      if (path === 'health') response = { protocol: 1, appleAuthAvailable: true, profileServiceAvailable: false };
      else if (path === 'config.json') response = { accountServiceUrl: null, officialRelease: null };
      else if (path === 'v1/sessions') {
        assert.equal(method, 'POST'); assert.deepEqual(body, { appleId: SYNTHETIC.appleId, password: SYNTHETIC.password }); assert(counter < 10);
        const sessionId = `synthetic-session-${++counter}`, sessionToken = `synthetic-token-${counter}`; sessions.set(sessionId, { sessionToken, state: 'awaitingTwoFactor' }); response = { sessionId, sessionToken, expiresInSeconds: 600 };
      } else {
        const [, , id, action] = path.split('/'), session = sessions.get(id); assert(session); assert.equal(authorization, `Bearer ${session.sessionToken}`);
        if (method === 'DELETE') { sessions.delete(id); response = { ok: true }; }
        else if (!action) response = { state: session.state, challenge: { retry: false, numbers: [] } };
        else if (action === '2fa') { assert.deepEqual(body, { action: 'submitCode', code: SYNTHETIC.code }); session.state = 'authenticated'; response = {}; }
        else if (action === 'teams' && path.endsWith('/devices')) { assert.equal(session.state, 'authenticated'); const teamId = path.split('/')[4]; assert(service.teams.some(team => team.id === teamId)); session.listedTeams ||= new Set(); session.listedTeams.add(teamId); if (service.failNextDevices) { service.failNextDevices = false; response = { status: 502, error: 'appleRequestFailed' }; } else response = { teamId, devices: service.deviceLists.get(teamId) || [] }; }
        else if (action === 'teams') { assert.equal(session.state, 'authenticated'); response = { teams: service.teams }; }
        else if (action === 'provision') {
          assert.equal(session.state, 'authenticated'); assert.deepEqual(Object.keys(body).sort(), ['apps', 'consent', 'csrPem', 'device', 'machineName', 'teamId']);
          const existing = body.device.existingOnly === true; assert.equal(body.consent, existing ? 'use-existing-device-register-app-ids-and-issue-certificate' : 'register-device-app-ids-and-issue-certificate'); if (existing) assert(session.listedTeams?.has(body.teamId)); assert.equal(body.teamId, SYNTHETIC.teamId); assert.equal(body.device.udid, SYNTHETIC.udid); assert.equal(body.device.name, 'My iPhone'); assert.equal(body.machineName, 'Tetherless Web'); assert.deepEqual(body.apps, [{ bundleId: SYNTHETIC.bundleId, name: 'Fixture' }]);
          service.provisioningBodies.push(text);
          if (session.provisionBody) assert.equal(text, session.provisionBody); else { session.provisionBody = text; session.material = syntheticProvision(body.csrPem); service.profiles.push(session.material.profile); }
          if (service.failNextProvision) { service.failNextProvision = false; response = { status: 503, error: 'provisioningUncertain' }; } else response = session.material.response;
        } else throw new Error('Unexpected synthetic API action');
      }
      const hold = holds.get(name); if (hold) { holds.delete(name); hold.enter(); await hold.wait; }
      return response;
    },
  };
  return service;
}
