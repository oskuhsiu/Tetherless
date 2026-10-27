/* Runtime adapter inspired by SylvaSigner f7127d6, MIT (licenses/SylvaSigner-MIT.txt).
 * Only signing with user-supplied material is exposed. No dylib injection, ad-hoc
 * hash-only signing, trust bypasses, filesystem persistence, or network uploads. */
self.onmessage = async ({ data }) => {
  try {
    const runtimeBase = new URL('./wasm/', self.location.href);
    importScripts(new URL('zsign-mobile.js', runtimeBase).href);
    const mod = await createZsignModule({ noInitialRun: true, locateFile: (name) => new URL(name, runtimeBase).href, print: () => {}, printErr: () => {} });
    const { FS } = mod;
    for (const path of ['/blob', '/output', '/work', '/tmp']) { try { FS.mkdir(path); } catch (error) { if (error.errno !== 20) throw error; } }
    FS.chdir('/work');
    const blobs = [{ name: 'input.ipa', data: data.ipa }, { name: 'signing.p12', data: data.p12 }, ...data.profiles.map((file, i) => ({ name: `profile-${i}.mobileprovision`, data: file }))];
    FS.mount(mod.WORKERFS, { blobs }, '/blob');
    const args = ['-k', '/blob/signing.p12', '-p', data.password, '-z', '1', '-o', '/output/signed.ipa'];
    data.profiles.forEach((_, i) => args.push('-m', `/blob/profile-${i}.mobileprovision`));
    args.push('/blob/input.ipa');
    self.postMessage({ phase: 'signing' });
    let result;
    try { result = mod.callMain(args); } catch (error) { if (Number.isInteger(error?.status)) result = error.status; else throw error; }
    args.fill(''); data.password = '';
    if (result !== 0) throw new Error('SIGN_FAILED');
    const node = FS.analyzePath('/output/signed.ipa').object;
    if (!node?.contents || !node.usedBytes) throw new Error('NO_OUTPUT');
    const bytes = node.contents.subarray(0, node.usedBytes);
    self.postMessage({ phase: 'done', bytes }, [bytes.buffer]);
  } catch {
    // Native diagnostics can contain filenames and identity data; do not expose or persist them.
    self.postMessage({ phase: 'error', message: 'The signing runtime rejected these inputs or ran out of memory. Check matching profiles and certificate, or try a smaller IPA.' });
  }
};
