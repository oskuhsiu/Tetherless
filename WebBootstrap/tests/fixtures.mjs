import forge from 'node-forge';
import { readFileSync } from 'node:fs';
import { ZipWriter, Uint8ArrayWriter, Uint8ArrayReader, TextReader } from '@zip.js/zip.js';
export async function makeIpa({ extra = [], bundleId = 'org.tetherless.TestFixture' } = {}) {
  const writer = new Uint8ArrayWriter(); const zip = new ZipWriter(writer, { level: 1, useWebWorkers: false });
  const info = `<?xml version="1.0"?><plist version="1.0"><dict><key>CFBundleIdentifier</key><string>${bundleId}</string><key>CFBundleExecutable</key><string>Fixture</string><key>CFBundleName</key><string>Fixture</string><key>CFBundleVersion</key><string>1</string><key>CFBundlePackageType</key><string>APPL</string></dict></plist>`;
  await zip.add('Payload/Fixture.app/Info.plist', new TextReader(info));
  await zip.add('Payload/Fixture.app/Fixture', new Uint8ArrayReader(readFileSync(new URL('./fixtures/demo1.dylib', import.meta.url))), { executable: true });
  for (const [name, content] of extra) await zip.add(name, new TextReader(content));
  return zip.close();
}
export function makeMaterial({ bundleId = 'org.tetherless.TestFixture', team = 'TESTTEAM01', udid = '00000000-0000000000000000', personal = true, password = 'fixture-only', expires = '2035-01-01T00:00:00Z' } = {}) {
  const keys = forge.pki.rsa.generateKeyPair(2048); const cert = forge.pki.createCertificate();
  cert.publicKey = keys.publicKey; cert.serialNumber = '01'; cert.validity.notBefore = new Date('2020-01-01T00:00:00Z'); cert.validity.notAfter = new Date(expires);
  cert.setSubject([{ name: 'commonName', value: 'Tetherless Synthetic Fixture (NOT APPLE)' }, { name: 'organizationalUnitName', value: team }]); cert.setIssuer(cert.subject.attributes);
  cert.sign(keys.privateKey, forge.md.sha256.create());
  const certDer = forge.asn1.toDer(forge.pki.certificateToAsn1(cert)).getBytes();
  const profileXml = `<?xml version="1.0"?><plist version="1.0"><dict><key>Name</key><string>Synthetic test only</string><key>UUID</key><string>00000000-1111-2222-3333-444444444444</string><key>ExpirationDate</key><date>${expires}</date><key>TeamIdentifier</key><array><string>${team}</string></array><key>ApplicationIdentifierPrefix</key><array><string>${team}</string></array><key>ProvisionedDevices</key><array><string>${udid}</string></array><key>LocalProvision</key><${personal ? 'true' : 'false'}/><key>DeveloperCertificates</key><array><data>${forge.util.encode64(certDer)}</data></array><key>Entitlements</key><dict><key>application-identifier</key><string>${team}.${bundleId}</string><key>com.apple.developer.team-identifier</key><string>${team}</string><key>get-task-allow</key><${personal ? 'true' : 'false'}/></dict></dict></plist>`;
  const cms = forge.pkcs7.createSignedData(); cms.content = forge.util.createBuffer(profileXml, 'utf8'); cms.addCertificate(cert); cms.addSigner({ key: keys.privateKey, certificate: cert, digestAlgorithm: forge.pki.oids.sha256 }); cms.sign();
  const profile = Buffer.from(forge.asn1.toDer(cms.toAsn1()).getBytes(), 'binary');
  const p12 = Buffer.from(forge.asn1.toDer(forge.pkcs12.toPkcs12Asn1(keys.privateKey, [cert], password, { algorithm: '3des' })).getBytes(), 'binary');
  return { p12, profile, password, certPem: forge.pki.certificateToPem(cert) };
}
export async function makeSignedFixture(ipa, material) {
  const vm = await import('node:vm');
  const sandbox={console,WebAssembly,TextDecoder,TextEncoder,URL,performance,setTimeout,clearTimeout,crypto,process};vm.createContext(sandbox);vm.runInContext(readFileSync(new URL('../public/wasm/zsign-mobile.js',import.meta.url),'utf8'),sandbox);
  const mod=await sandbox.createZsignModule({noInitialRun:true,wasmBinary:readFileSync(new URL('../public/wasm/zsign-mobile.wasm',import.meta.url)),print:()=>{},printErr:()=>{}});
  mod.FS.mkdir('/work');mod.FS.chdir('/work');mod.FS.writeFile('/work/input.ipa',new Uint8Array(await ipa.arrayBuffer()));mod.FS.writeFile('/work/signing.p12',material.p12);mod.FS.writeFile('/work/profile.mobileprovision',material.profile);
  const code=mod.callMain(['-k','/work/signing.p12','-p',material.password,'-m','/work/profile.mobileprovision','-z','1','-o','/work/signed.ipa','/work/input.ipa']);if(code!==0)throw new Error('Synthetic signing failed');return new Uint8Array(mod.FS.readFile('/work/signed.ipa'));
}
