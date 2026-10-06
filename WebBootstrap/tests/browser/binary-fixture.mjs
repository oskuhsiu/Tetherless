import { readFileSync } from 'node:fs';
import { ZipWriter, Uint8ArrayReader, Uint8ArrayWriter } from '@zip.js/zip.js';

// Python plistlib FMT_BINARY encoding of the same five Info.plist keys as makeIpa.
// This exercises the built browser plist worker without another dependency.
export const binaryInfo = Buffer.from('YnBsaXN0MDDVAQIDBAUGBwYICV8QEkNGQnVuZGxlRXhlY3V0YWJsZV8QEkNGQnVuZGxlSWRlbnRpZmllclxDRkJ1bmRsZU5hbWVfEBNDRkJ1bmRsZVBhY2thZ2VUeXBlXxAPQ0ZCdW5kbGVWZXJzaW9uV0ZpeHR1cmVfEBpvcmcudGV0aGVybGVzcy5UZXN0Rml4dHVyZVRBUFBMUTEIEyg9SmByepecAAAAAAAAAQEAAAAAAAAACgAAAAAAAAAAAAAAAAAAAJ4=', 'base64');
export async function makeBinaryIpa() {
  const writer = new ZipWriter(new Uint8ArrayWriter(), { level: 1, useWebWorkers: false });
  await writer.add('Payload/Fixture.app/Info.plist', new Uint8ArrayReader(binaryInfo));
  await writer.add('Payload/Fixture.app/Fixture', new Uint8ArrayReader(readFileSync(new URL('../fixtures/demo1.dylib', import.meta.url))), { executable: true });
  return Buffer.from(await writer.close());
}
