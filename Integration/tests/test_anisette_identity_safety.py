"""Exact production transformations; no Apple account or provisioning fixture."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/(name+'.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value

module = load('anisette_identity_safety')
REVIEW = Path(os.environ.get('TETHERLESS_AUTH_REVIEW_ROOT', ROOT.parent/'Vendor/SideStore'))

def blob(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def prepared_inputs():
    result = {}
    for path, expected in module.BLOBS.items():
        raw = (REVIEW/path).read_bytes()
        if path == module.KEYCHAIN and not os.environ.get('TETHERLESS_AUTH_REVIEW_ROOT'):
            # CI has pristine pinned upstream. Reproduce only its earlier reviewed
            # keychain transformations; never accept an unknown intermediate hash.
            prepare, auth, signer = load('prepare'), load('auth_safety'), load('certificate_safety')
            if blob(raw) != prepare.BLOBS[path]: raise ValueError('Unreviewed pristine Keychain')
            raw = prepare.patch_keychain(raw.decode()).encode()
            if blob(raw) != auth.BLOBS[path]: raise ValueError('Unreviewed account Keychain input')
            raw = auth.patch_keychain(raw.decode()).encode()
            if blob(raw) != signer.BLOBS[path]: raise ValueError('Unreviewed signing Keychain input')
            raw = signer.patch_keychain(raw.decode()).encode()
        if blob(raw) != expected: raise ValueError('Unreviewed identity input: '+path)
        result[path] = raw
    return result


class AnisetteIdentityIntegrationTests(unittest.TestCase):
    def test_wired_after_existing_safety_transforms(self):
        text = (ROOT/'network_safety.py').read_text()
        self.assertLess(text.index('"anisette_package_safety.py"'), text.index('"anisette_identity_safety.py"'))
        native = (ROOT/'Native/NativeAnisetteIdentity.swift').read_text()
        self.assertIn('NativeMutationGate.withLease', native)
        self.assertIn('NativeMutationGate.withSynchronousLease', native)
        self.assertIn('admission.acquire()', native)
        self.assertEqual(native.count('defer { token.release() }'), 2)
        self.assertIn('store().use(readLegacy: legacy, removeLegacy: cleanup, fetch: fetch)', native)
        self.assertIn('service: "org.tetherless.anisette."', native)
        self.assertNotIn('try?', native)

    def test_headless_engine_and_repairs_convey_real_mutation_ownership(self):
        engine = (ROOT.parent/'Sources/TetherlessCore/RenewalEngine.swift').read_text()
        self.assertIn('lease.withMutationScope', engine)
        self.assertIn('runAcquired(trigger: trigger, force: force)', engine)
        runtime = (ROOT/'Native/NativeRenewalRuntime.swift').read_text()
        for name, end in [('reEnrollRepairedApps()', 'func confirmRepair()'),
                          ('confirmRepair()', 'static func classify')]:
            body = runtime.split('func '+name)[1].split(end)[0]
            self.assertIn('NativeMutationGate.withLease', body)
            self.assertNotIn('NativeRenewalStorage.acquire()', body)
        self.assertIn('error is AnisetteIdentityFailure', runtime)

    def test_late_bad_input_prevents_every_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in module.BLOBS:
                output = root/path; output.parent.mkdir(parents=True, exist_ok=True); output.write_text('unreviewed')
            before = {p:(root/p).read_bytes() for p in module.BLOBS}
            with self.assertRaises(ValueError): module.apply(root)
            self.assertEqual(before, {p:(root/p).read_bytes() for p in module.BLOBS})

    @unittest.skipUnless(all((REVIEW/p).is_file() for p in module.BLOBS), 'Pinned sources not mounted; required separately by native preparation')
    def test_actual_prepared_inputs_and_unchanged_reapplication(self):
        inputs = prepared_inputs()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path, raw in inputs.items():
                output = root/path; output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(raw)
            module.apply(root)
            outputs = {p:(root/p).read_bytes() for p in module.BLOBS}
            with self.assertRaises(ValueError): module.apply(root)
            self.assertEqual(outputs, {p:(root/p).read_bytes() for p in module.BLOBS})
            compiler = shutil.which('swiftc')
            self.assertIsNotNone(compiler, 'Swift syntax check must run')
            for path in module.BLOBS:
                result = subprocess.run([compiler, '-frontend', '-parse', str(root/path)], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
            # Hash drift at the LAST input must not rewrite the first three.
            for path, raw in inputs.items(): (root/path).write_bytes(raw)
            (root/module.KEYCHAIN).write_text('late mismatch')
            with self.assertRaises(ValueError): module.apply(root)
            for path, raw in inputs.items():
                if path != module.KEYCHAIN: self.assertEqual((root/path).read_bytes(), raw)

    @unittest.skipUnless(all((REVIEW/p).is_file() for p in module.BLOBS), 'Pinned sources not mounted')
    def test_both_providers_use_the_same_guarded_transaction(self):
        inputs = prepared_inputs()
        for path in [module.DEVICE, module.REMOTE]:
            text = module.TRANSFORMS[path](inputs[path].decode())
            self.assertIn('return try await NativeAnisetteIdentity.withIdentity { identity in', text)
            self.assertIn('identity.blob', text)
            self.assertIn('identity.identifier', text)
            self.assertNotIn('anisetteAdiBlob', text)
            self.assertNotIn('resolveDeviceIdentifier', text)
            self.assertNotIn('ignoreUnknownCharacters', text)
            self.assertNotIn('saved new adi.pb', text)
        config = module.patch_config(inputs[module.CONFIG].decode())
        for name in ['anisetteIdentifier', 'anisetteAdiBlob', 'resolveDeviceIdentifier']:
            self.assertNotIn(name, config)

    @unittest.skipUnless(all((REVIEW/p).is_file() for p in module.BLOBS), 'Pinned sources not mounted')
    def test_resets_include_new_identity_and_legacy_access_is_checked(self):
        text = module.patch_keychain(prepared_inputs()[module.KEYCHAIN].decode())
        self.assertNotIn('@KeychainItem(key: "adiPb")', text)
        self.assertNotIn('@KeychainItem(key: "identifier")', text)
        self.assertNotIn('self.adiPb =', text)
        self.assertIn('try NativeAnisetteIdentity.reset(keepingIdentifier: true)', text)
        start = text.index('func clearAllVerified()')
        end = text.index('public func clearCertificates()', start)
        self.assertLess(text[start:end].index('NativeAnisetteIdentity.reset'), text[start:end].index('keychain.removeAll()'))
        self.assertIn('try removeVerified(["identifier", "adiPb"])', text)
        self.assertIn('public func clearSignInInfo(keepAnisetteData: Bool = true) throws', text)
        self.assertIn('public func clearAll() throws', text)
