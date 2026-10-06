import forge from 'node-forge';
import { BlobReader, Uint8ArrayWriter, ZipReader } from '@zip.js/zip.js';
import { inspectArchive, LIMITS } from './archive.js';
import { parsePlist } from './plist.js';
import { tetherlessGroup } from './tetherless-identity.js';
const rawBytes = (bytes) => forge.util.binary.raw.encode(bytes);
const derBytes = (certificate) => forge.asn1.toDer(forge.pki.certificateToAsn1(certificate)).getBytes();
const equalBytes = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);
export function bundleMatches(pattern, id) { return pattern === id || (pattern.endsWith('.*') && id.startsWith(pattern.slice(0, -1))); }
export async function readProfile(bytes, options) {
  // Forge parses CMS; this is metadata consistency only, not Apple CMS chain verification.
  const message = forge.pkcs7.messageFromAsn1(forge.asn1.fromDer(rawBytes(bytes)));
  if (message.type !== forge.pki.oids.signedData || !message.rawCapture?.content) throw new Error('Choose an Apple CMS provisioning profile.');
  const contents = message.rawCapture.content.value;
  if (!Array.isArray(contents) || contents.length !== 1 || contents[0].type !== forge.asn1.Type.OCTETSTRING || typeof contents[0].value !== 'string') throw new Error('Unsupported provisioning profile content.');
  return parsePlist(forge.util.binary.raw.decode(contents[0].value), options);
}
export async function inspectInputs({ ipa, p12, profiles, password, udid = '' }, now = new Date(), signal) {
  if (!p12 || p12.size > LIMITS.signingMaterial || !profiles?.length || profiles.length > 20 || profiles.some((p) => p.size > LIMITS.signingMaterial)) throw new Error('Choose one P12 and 1–20 profiles, each at most 2 MiB.');
  if (password.length > 1024) throw new Error('Certificate password is too long.');
  if (udid && !/^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{8}-[0-9a-fA-F]{16})$/.test(udid)) throw new Error('Enter a 40-character or 8–16 device UDID.');
  const archive = await inspectArchive(ipa);
  let container;
  try { container = forge.pkcs12.pkcs12FromAsn1(forge.asn1.fromDer(rawBytes(new Uint8Array(await p12.arrayBuffer()))), false, password); }
  catch { throw new Error('The P12 could not be opened. Check the file and its password.'); }
  const certs = container.getBags({ bagType: forge.pki.oids.certBag })[forge.pki.oids.certBag] ?? [];
  const keys = [...(container.getBags({ bagType: forge.pki.oids.pkcs8ShroudedKeyBag })[forge.pki.oids.pkcs8ShroudedKeyBag] ?? []), ...(container.getBags({ bagType: forge.pki.oids.keyBag })[forge.pki.oids.keyBag] ?? [])];
  if (keys.filter((bag) => bag.key).length !== 1) throw new Error('The P12 must contain exactly one private signing key.');
  const cert = certs.find(({ cert }) => cert && keys.some(({ key }) => key?.n?.equals(cert.publicKey.n) && key.e?.equals(cert.publicKey.e)))?.cert;
  if (!cert) throw new Error('The P12 must contain a supported RSA signing key and matching certificate.');
  if (cert.validity.notBefore > now || cert.validity.notAfter <= now) throw new Error('The signing certificate is not currently valid.');
  const certBytes = forge.util.binary.raw.decode(derBytes(cert));
  const parsedProfiles = [];
  for (const file of profiles) {
    const profile = await readProfile(new Uint8Array(await file.arrayBuffer()), {signal});
    if (!(profile.ExpirationDate instanceof Date) || !Number.isFinite(+profile.ExpirationDate) || profile.ExpirationDate <= now) throw new Error('A provisioning profile is expired or has no valid expiry.');
    if (profile.ProvisionsAllDevices === true) throw new Error('Shared or enterprise distribution profiles are outside this personal bootstrap prototype.');
    if (!Array.isArray(profile.ProvisionedDevices) || !profile.ProvisionedDevices.length) throw new Error('Profiles must list registered devices.');
    if (udid && !profile.ProvisionedDevices.some((x) => x.toLowerCase() === udid.toLowerCase())) throw new Error('A provisioning profile does not contain this device UDID.');
    if (!profile.DeveloperCertificates?.some((x) => x instanceof Uint8Array && equalBytes(x, certBytes))) throw new Error('The selected certificate is absent from a provisioning profile.');
    const team = profile.TeamIdentifier?.[0], entitlement = profile.Entitlements?.['application-identifier'];
    const prefixes = profile.ApplicationIdentifierPrefix;
    if (!team || !Array.isArray(prefixes) || !prefixes.some((prefix) => typeof entitlement === 'string' && entitlement.startsWith(prefix + '.'))) throw new Error('The provisioning profile has inconsistent app/team metadata.');
    if (profile.Entitlements['com.apple.developer.team-identifier'] !== team) throw new Error('Profile team identifiers do not match.');
    const prefix = prefixes.find((prefix) => entitlement.startsWith(prefix + '.'));
    parsedProfiles.push({ groups: profile.Entitlements['com.apple.security.application-groups'] || [], team, pattern: entitlement.slice(prefix.length + 1), expires: profile.ExpirationDate.toISOString(), kind: profile.LocalProvision ? 'personal-team' : profile.Entitlements['get-task-allow'] ? 'development' : 'ad-hoc', file });
  }
  if (new Set(parsedProfiles.map((x) => x.team)).size !== 1) throw new Error('All bundles must use the same Apple Team.');
  const { bundles } = await inspectIpa(ipa, archive, signal);
  if (parsedProfiles.some((p) => p.pattern.includes('*'))) throw new Error('Wildcard profiles are unsupported by this runtime adapter. Supply one exact profile for each app and extension.');
  for (const { id } of bundles) if (parsedProfiles.filter((p) => p.pattern === id).length !== 1) throw new Error(`Missing a unique exact profile for ${id}. Bundle identifiers are preserved.`);
  const group = tetherlessGroup(bundles);
  if (group && parsedProfiles.some((p) => !Array.isArray(p.groups) || !p.groups.includes(group.identifier))) throw new Error(`Tetherless requires the shared App Group ${group.identifier} in every profile.`);
  if (parsedProfiles.length !== bundles.length) throw new Error('Supply exactly one profile per app bundle, with no extra profiles.');
  for (const a of bundles) for (const b of bundles) if (a.id !== b.id && b.id.endsWith(a.id)) throw new Error('These bundle IDs have an ambiguous suffix for this signing runtime.');
  return { archive, bundles, team: parsedProfiles[0].team, profiles: parsedProfiles.map(({ file, ...rest }) => rest), certificateExpiry: cert.validity.notAfter.toISOString() };
}

export async function inspectIpa(ipa, archive, signal) {
  archive ??= await inspectArchive(ipa);
  const reader = new ZipReader(new BlobReader(ipa), { useWebWorkers: false });
  const bundles = [];
  try {
    const entries = await reader.getEntries();
    for (const path of archive.bundles) {
      const entry = entries.find((e) => e.filename === path);
      const info = await parsePlist(await entry.getData(new Uint8ArrayWriter(), { checkSignature: true }), {signal});
      const id = info.CFBundleIdentifier;
      if (typeof id !== 'string' || !/^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$/.test(id)) throw new Error('An app bundle has an invalid identifier.');
      bundles.push({ path, id, name: String(info.CFBundleDisplayName || info.CFBundleName || id), version: String(info.CFBundleVersion || '1') });
    }
  } finally { await reader.close(); }
  if (new Set(bundles.map((b) => b.id)).size !== bundles.length) throw new Error('Two app bundles share the same bundle identifier.');
  bundles.sort((a, b) => Number(b.path === archive.root + 'Info.plist') - Number(a.path === archive.root + 'Info.plist'));
  return { archive, bundles };
}

export async function verifyEmbeddedProfiles(ipa, checked, inputProfiles) {
  const { archive, bundles } = await inspectIpa(ipa);
  const canonical = (values) => values.map(({path,id})=>[path,id]).sort((a,b)=>a[0].localeCompare(b[0]));
  if (JSON.stringify(canonical(bundles)) !== JSON.stringify(canonical(checked.bundles))) throw new Error('Signing changed the expected app bundle identities.');
  const expected = new Map();
  for (let i=0;i<checked.profiles.length;i++) expected.set(checked.profiles[i].pattern, new Uint8Array(await inputProfiles[i].arrayBuffer()));
  const reader = new ZipReader(new BlobReader(ipa), { useWebWorkers: false });
  try {
    const entries = await reader.getEntries();
    for (const bundle of bundles) {
      const path = bundle.path.replace(/Info\.plist$/, 'embedded.mobileprovision');
      const safe = archive.entries.find((entry)=>entry.name===path);
      if (!safe || safe.size > LIMITS.signingMaterial) throw new Error('A signed bundle has no bounded embedded provisioning profile.');
      const entry = entries.find((entry)=>entry.filename===path);
      const actual = await entry.getData(new Uint8ArrayWriter(), {checkSignature:true});
      if (!equalBytes(actual, expected.get(bundle.id))) throw new Error(`Signing embedded the wrong profile for ${bundle.id}. No download is offered.`);
    }
  } finally { await reader.close(); }
}
