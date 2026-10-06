// Ordinary upload admission. It does not inspect Mach-O or establish Apple trust.
export const LIMITS = Object.freeze({ input: 150 * 1024 * 1024, expanded: 384 * 1024 * 1024, entries: 20000, metadata: 1024 * 1024, signingMaterial: 2 * 1024 * 1024 });
const fail = (text) => { throw new Error(text); };
const utf8 = new TextDecoder('utf-8', { fatal: true });
export function safeArchivePath(bytes, flags) {
  if (!(flags & 0x800) && bytes.some((x) => x > 127)) fail('ZIP filenames must use ASCII or the UTF-8 flag.');
  const name = utf8.decode(bytes);
  if (!name || name.length > 1024 || /[\\\x00-\x1f\x7f:]/.test(name) || name.startsWith('/') || name.split('/').some((p) => p === '.' || p === '..') || name.includes('//')) fail('The IPA has an unsafe archive path.');
  return name;
}
export async function inspectArchive(file) {
  if (!file || file.size < 22 || file.size > LIMITS.input) fail('Choose an IPA between 22 bytes and 150 MiB.');
  const tailStart = Math.max(0, file.size - 65557);
  const tail = new Uint8Array(await file.slice(tailStart).arrayBuffer());
  const tv = new DataView(tail.buffer);
  let e = -1;
  for (let i = tail.length - 22; i >= 0; i--) if (tv.getUint32(i, true) === 0x06054b50 && i + 22 + tv.getUint16(i + 20, true) === tail.length) { e = i; break; }
  if (e < 0) fail('The IPA is not a supported complete ZIP archive.');
  const count = tv.getUint16(e + 10, true), size = tv.getUint32(e + 12, true), offset = tv.getUint32(e + 16, true);
  if (tv.getUint16(e + 4, true) || tv.getUint16(e + 6, true) || tv.getUint16(e + 8, true) !== count || count === 65535 || count < 1 || count > LIMITS.entries || size > 16 * 1024 * 1024 || offset + size !== tailStart + e) fail('Split, ZIP64, oversized, or inconsistent ZIP archives are unsupported.');
  const central = new Uint8Array(await file.slice(offset, offset + size).arrayBuffer());
  const cv = new DataView(central.buffer), entries = [], seen = new Set(), spans = [];
  let cursor = 0, expanded = 0;
  for (let index = 0; index < count; index++) {
    if (cursor + 46 > size || cv.getUint32(cursor, true) !== 0x02014b50) fail('The IPA directory is incomplete.');
    const flags = cv.getUint16(cursor + 8, true), method = cv.getUint16(cursor + 10, true), crc = cv.getUint32(cursor + 16, true), compressed = cv.getUint32(cursor + 20, true), uncompressed = cv.getUint32(cursor + 24, true);
    const nameLength = cv.getUint16(cursor + 28, true), extra = cv.getUint16(cursor + 30, true), comment = cv.getUint16(cursor + 32, true), disk = cv.getUint16(cursor + 34, true), attrs = cv.getUint32(cursor + 38, true), local = cv.getUint32(cursor + 42, true);
    const end = cursor + 46 + nameLength + extra + comment;
    if (end > size || !nameLength || flags & ~0x80e || ![0, 8].includes(method) || disk || [compressed, uncompressed, local].includes(0xffffffff)) fail('Encrypted, ZIP64, or unsupported ZIP entries are not accepted.');
    const nameBytes = central.slice(cursor + 46, cursor + 46 + nameLength), name = safeArchivePath(nameBytes, flags), key = name.normalize('NFC').toLowerCase().replace(/\/$/, '');
    if (seen.has(key)) fail('Duplicate or case-colliding ZIP paths are unsupported.');
    seen.add(key);
    // Extra fields can override filenames in some extractors. Admit no alternative path encoding.
    for (let p = cursor + 46 + nameLength; p < cursor + 46 + nameLength + extra;) {
      if (p + 4 > cursor + 46 + nameLength + extra) fail('Invalid ZIP extra field.');
      const tag = cv.getUint16(p, true), length = cv.getUint16(p + 2, true); p += 4;
      if ([1, 0x7075].includes(tag) || p + length > cursor + 46 + nameLength + extra) fail('ZIP64 and alternate ZIP filenames are unsupported.');
      p += length;
    }
    const type = (attrs >>> 16) & 0xf000;
    if (type && ![0x8000, 0x4000].includes(type)) fail('Symlinks and special files are unsupported.');
    expanded += uncompressed;
    if (expanded > LIMITS.expanded || (uncompressed > 1024 * 1024 && uncompressed > Math.max(compressed, 1) * 200)) fail('The expanded IPA exceeds browser memory or compression limits.');
    if (local + 30 + nameLength > offset) fail('Invalid local ZIP header.');
    const header = new Uint8Array(await file.slice(local, local + 30 + nameLength).arrayBuffer()), hv = new DataView(header.buffer);
    if (hv.getUint32(0, true) !== 0x04034b50 || hv.getUint16(6, true) !== flags || hv.getUint16(8, true) !== method || hv.getUint16(26, true) !== nameLength || header.slice(30).some((v, i) => v !== nameBytes[i])) fail('Local and directory ZIP entries disagree.');
    if (!(flags & 8) && (hv.getUint32(14, true) !== crc || hv.getUint32(18, true) !== compressed || hv.getUint32(22, true) !== uncompressed)) fail('Local ZIP sizes or CRC disagree.');
    const dataStart = local + 30 + nameLength + hv.getUint16(28, true), dataEnd = dataStart + compressed;
    if (dataEnd > offset) fail('ZIP data extends outside the IPA.');
    spans.push([local, dataEnd]); entries.push({ name, size: uncompressed, directory: name.endsWith('/') }); cursor = end;
  }
  if (cursor !== size) fail('Unexpected ZIP directory data.');
  spans.sort((a, b) => a[0] - b[0]);
  for (let i = 1; i < spans.length; i++) if (spans[i][0] < spans[i - 1][1]) fail('ZIP entries overlap.');
  const mains = entries.filter((e) => /^Payload\/[^/]+\.app\/Info\.plist$/.test(e.name));
  if (mains.length !== 1) fail('Select an IPA with exactly one top-level Payload app.');
  const root = mains[0].name.slice(0, -'Info.plist'.length);
  const bundles = entries.filter((e) => e.name.startsWith(root) && /\.(app|appex)\/Info\.plist$/.test(e.name));
  if (bundles.length > 20 || bundles.some((e) => e.size > LIMITS.metadata)) fail('Too many bundles or oversized app metadata.');
  return { entries, bundles: bundles.map((e) => e.name), root, expanded };
}
