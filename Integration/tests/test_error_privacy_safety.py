"""Closed history/source-error metadata; synthetic inputs, no account/device access."""
from pathlib import Path
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


m = module('error_privacy_safety')
REVIEW = Path(os.environ.get('TETHERLESS_ERROR_PRIVACY_REVIEW_ROOT', ROOT.parent / 'Vendor/SideStore'))
PINNED = all((REVIEW / name).is_file() for name in m.BLOBS)


def digest(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def prepared_inputs():
    catalog, maintenance = module('catalog_safety'), module('maintenance_safety')
    originals = {name: (REVIEW / name).read_bytes() for name in m.BLOBS}
    manager = originals[m.MANAGER]
    # Never mistake previously prepared source for the upstream raw preimage.
    assert digest(manager) == catalog.BLOBS[m.MANAGER]
    manager = catalog.patch_manager(manager.decode()).encode()
    assert digest(manager) == maintenance.BLOBS[m.MANAGER]
    manager = maintenance.patch_app(manager.decode()).encode()
    originals[m.MANAGER] = manager
    for name, raw in originals.items():
        assert digest(raw) == m.BLOBS[name]
    return originals


def populate(root, originals):
    for name, raw in originals.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)


class ErrorPrivacySafetyTests(unittest.TestCase):
    def test_unreviewed_source_is_not_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            populate(root, {name: b'unreviewed source' for name in m.BLOBS})
            with self.assertRaises(ValueError):
                m.apply(root)
            self.assertTrue(all((root / name).read_bytes() == b'unreviewed source' for name in m.BLOBS))

    @unittest.skipUnless(PINNED, 'Pinned raw error-history sources unavailable')
    def test_exact_preimages_apply_then_refuse_reapplication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            populate(root, prepared_inputs())
            m.apply(root)
            outputs = {name: (root / name).read_bytes() for name in m.BLOBS}
            self.assertIn(m.OVERRIDE.read_bytes(), outputs[m.MODEL])
            self.assertEqual(outputs[m.MODEL].count(b'enum TetherlessErrorRecordPolicy'), 1)
            with self.assertRaises(ValueError):
                m.apply(root)
            self.assertEqual(outputs, {name: (root / name).read_bytes() for name in m.BLOBS})

    @unittest.skipUnless(PINNED, 'Pinned raw error-history sources unavailable')
    def test_changed_or_missing_later_preimage_writes_nothing(self):
        originals = prepared_inputs()
        for changed in (m.MANAGER, m.MY_APPS, m.SOURCES):
            for missing in (False, True):
                with self.subTest(changed=changed, missing=missing), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    populate(root, originals)
                    if missing:
                        (root / changed).unlink()
                    else:
                        (root / changed).write_text('changed source')
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        m.apply(root)
                    for name, raw in originals.items():
                        if name != changed:
                            self.assertEqual((root / name).read_bytes(), raw)
                    if not missing:
                        self.assertEqual((root / changed).read_text(), 'changed source')

    @unittest.skipUnless(PINNED, 'Pinned raw error-history sources unavailable')
    def test_core_data_schema_and_app_relationships_are_unchanged(self):
        original = prepared_inputs()[m.MODEL].decode()
        output = m.patch_model(original)
        declarations = lambda text: re.findall(r'^.*@NSManaged.*$', text, re.M)
        self.assertEqual(declarations(original), declarations(output))
        for start, end in [('        self.appName = app.name', '\n}\n\npublic extension'),
                           ('    var app: AppProtocol', '    var error: NSError'),
                           ('    var localizedFailure:', '\n}\n\npublic extension')]:
            self.assertEqual(original.split(start)[1].split(end)[0], output.split(start)[1].split(end)[0])
        self.assertIn('self.date = date', output)
        self.assertIn('self._operation = operation?.rawValue', output)
        self.assertIn('self.code = Int32(nsError.code)', output)

    @unittest.skipUnless(PINNED, 'Pinned raw error-history sources unavailable')
    def test_legacy_display_never_reconstructs_raw_user_info(self):
        output = m.patch_model(prepared_inputs()[m.MODEL].decode())
        getter = output.split('    var error: NSError {')[1].split('\n    }')[0]
        self.assertIn('snapshot(domain: self.domain, code: Int(self.code))', getter)
        self.assertNotIn('userInfo', getter)
        self.assertNotIn('self.domain =', getter)
        self.assertNotIn('save(', getter)
        self.assertNotIn('delete(', output)

    @unittest.skipUnless(PINNED, 'Pinned raw error-history sources unavailable')
    def test_log_handoff_preserves_cancellation_and_save_handling(self):
        original = prepared_inputs()[m.MANAGER].decode()
        output = m.patch_manager(original)
        signature = '    func log(_ error: Error, operation: LoggedError.Operation, app: AppProtocol)'
        before = original.split(signature)[1]
        after = output.split(signature)[1]
        self.assertEqual(before.split('        // Sanitize NSError')[0],
                         after.split('        // Capture only closed')[0])
        boundary = '        DatabaseManager.shared.persistentContainer.performBackgroundTask'
        self.assertEqual(before.split(boundary)[1], after.split(boundary)[1])
        self.assertIn('case is CancellationError: return', after)
        self.assertIn('case let nsError as NSError where nsError.domain == CancellationError()._domain: return', after)
        self.assertNotIn('sanitizedForSerialization()', after)

    @unittest.skipUnless(PINNED, 'Pinned raw error-history sources unavailable')
    def test_only_three_manager_capture_sites_change(self):
        original = prepared_inputs()[m.MANAGER].decode()
        output = m.patch_manager(original)
        # Exact reconstruction proves original live errors, source lookup,
        # throws, cancellation, success/failure and save branches are untouched.
        expected = original.replace(
            '// Sanitize NSError on same thread before performing background task.\n'
            '        let sanitizedError = (error as NSError).sanitizedForSerialization()',
            '// Capture only closed diagnostic metadata before crossing queues.\n'
            '        let sanitizedError = TetherlessErrorRecordPolicy.sanitized(error as NSError)')
        expected = expected.replace('source.error = error.sanitizedForSerialization()',
            'source.error = TetherlessErrorRecordPolicy.sanitized(error)')
        expected = expected.replace('let sanitizedError = (mergeError as NSError).sanitizedForSerialization()',
            'let sanitizedError = TetherlessErrorRecordPolicy.sanitized(mergeError as NSError)')
        self.assertEqual(output, expected)
        self.assertIn('errors[source] = error', output)
        self.assertEqual(output.count('throw mergeError'), original.count('throw mergeError'))
        self.assertEqual(output.count('source.error ='), original.count('source.error ='))
        self.assertEqual(output.count('.sanitizedForSerialization()'), original.count('.sanitizedForSerialization()') - 3)

    @unittest.skipUnless(PINNED, 'Pinned raw error-history sources unavailable')
    def test_foreground_merge_preserves_original_throw_and_source_selection(self):
        original = prepared_inputs()[m.MY_APPS].decode()
        output = m.patch_source_merge_error(original)
        self.assertEqual(output, original.replace(
            'let sanitizedError = (mergeError as NSError).sanitizedForSerialization()',
            'let sanitizedError = TetherlessErrorRecordPolicy.sanitized(mergeError as NSError)'))
        self.assertIn('guard let sourceID = mergeError.sourceID else { throw mergeError }', output)
        self.assertEqual(output.count('throw mergeError'), original.count('throw mergeError'))
        self.assertEqual(output.count('source.error ='), 1)

    @unittest.skipUnless(PINNED, 'Pinned raw error-history sources unavailable')
    def test_both_source_display_reads_sanitize_without_changing_optional_state(self):
        original = prepared_inputs()[m.SOURCES].decode()
        output = m.patch_source_views(original)
        self.assertEqual(output.count('source.error.map(TetherlessErrorRecordPolicy.sanitized)'), 2)
        self.assertEqual(output, original.replace('if let error = source.error\n',
            'if let error = source.error.map(TetherlessErrorRecordPolicy.sanitized)\n'))
        self.assertNotIn('source.error =', output)
        self.assertEqual(output.count('self.present(error)'), original.count('self.present(error)'))
        with self.assertRaises(ValueError):
            m.patch_source_views(original.replace('if let error = source.error\n', '', 1))

    def test_policy_has_no_free_form_payload_processing(self):
        source = m.OVERRIDE.read_text()
        executable = '\n'.join(line for line in source.splitlines() if not line.lstrip().startswith('//'))
        for forbidden in ['.userInfo', '.localizedDescription', '.description', 'String(describing:',
                          'NSUnderlyingErrorKey', 'regularExpression', 'NSRegularExpression', '\\(']:
            self.assertNotIn(forbidden, executable)
        self.assertIn('Category(rawValue: code) ?? .unexpected', source)
        self.assertIn('return snapshot(domain: error.domain, code: error.code)', source)
        self.assertNotIn('sourceCode,', source)

    @unittest.skipUnless(shutil.which('swiftc'), 'Swift compiler unavailable; native policy execution pending')
    def test_actual_swift_policy_and_secure_archive_round_trip(self):
        source = r'''
import Foundation

// A diagnostic must never touch these free-form accessors, even indirectly.
final class UnreadableError: NSError, @unchecked Sendable {
    override var userInfo: [String: Any] { fatalError("userInfo evaluated") }
    override var localizedDescription: String { fatalError("description evaluated") }
    override var description: String { fatalError("description evaluated") }
}

@main struct Main {
    static func main() throws {
        typealias Policy = TetherlessErrorRecordPolicy
        typealias Category = Policy.Category
        let secret = "SYNTHETIC_EMAIL_PIN_TOKEN_UDID_SERVER_SENTINEL"
        let raw = NSError(domain: secret, code: Int.max, userInfo: [
            secret: secret,
            NSLocalizedDescriptionKey: secret,
            NSLocalizedFailureReasonErrorKey: secret,
            NSLocalizedRecoverySuggestionErrorKey: secret,
            NSDebugDescriptionErrorKey: secret,
            NSURLErrorFailingURLErrorKey: URL(string: "https://example.invalid/?token=" + secret)!,
            NSUnderlyingErrorKey: NSError(domain: secret, code: Int.min, userInfo: [secret: secret]),
            "nested": [[secret: Data(secret.utf8)]]
        ])
        let safe = Policy.sanitized(raw)
        precondition(safe.domain == Policy.domain && safe.code == Category.unexpected.rawValue)
        precondition(raw.domain == secret && raw.code == Int.max)
        precondition(raw.userInfo[NSLocalizedDescriptionKey] as? String == secret)
        let allowedKeys: Set<String> = [NSLocalizedDescriptionKey, "category", "outcome"]
        func check(_ error: NSError) throws {
            precondition(error.domain == Policy.domain)
            precondition(Category(rawValue: error.code) != nil)
            precondition(Int32(exactly: error.code) != nil)
            precondition(Set(error.userInfo.keys) == allowedKeys)
            precondition(error.userInfo.values.allSatisfy { $0 is String })
            precondition(!error.description.contains(secret))
            let archive = try NSKeyedArchiver.archivedData(withRootObject: error, requiringSecureCoding: true)
            precondition(archive.range(of: Data(secret.utf8)) == nil)
            let decoded = try NSKeyedUnarchiver.unarchivedObject(ofClass: NSError.self, from: archive)!
            precondition(decoded.domain == error.domain && decoded.code == error.code)
            precondition(NSDictionary(dictionary: decoded.userInfo).isEqual(to: error.userInfo))
            let repeated = Policy.sanitized(error)
            precondition(repeated.domain == error.domain && repeated.code == error.code)
            precondition(NSDictionary(dictionary: repeated.userInfo).isEqual(to: error.userInfo))
        }
        try check(safe)
        let cases: [(String, Int, Category)] = [
            (NSURLErrorDomain, NSURLErrorTimedOut, .timedOut),
            (NSURLErrorDomain, NSURLErrorNotConnectedToInternet, .offline),
            (NSURLErrorDomain, NSURLErrorCancelled, .cancelled),
            (NSURLErrorDomain, NSURLErrorSecureConnectionFailed, .secureConnection),
            (NSURLErrorDomain, NSURLErrorCannotParseResponse, .invalidResponse),
            (NSURLErrorDomain, Int.max, .network),
            (NSCocoaErrorDomain, NSFileReadNoPermissionError, .permissionDenied),
            (NSCocoaErrorDomain, NSFileWriteNoPermissionError, .permissionDenied),
            (NSCocoaErrorDomain, NSFileWriteOutOfSpaceError, .storageFull),
            (NSCocoaErrorDomain, NSFileNoSuchFileError, .missingFile),
            (NSCocoaErrorDomain, NSFileReadNoSuchFileError, .missingFile),
            (NSCocoaErrorDomain, NSUserCancelledError, .cancelled),
            (NSCocoaErrorDomain, Int.min, .filesystem),
            ("SideSign.DeveloperPortalError", Int.max, .authentication),
            ("SideSign.ServerError", Int.min, .server),
            ("Swift.CancellationError", 1, .cancelled),
            (secret, 123456789, .unexpected),
            (Policy.domain, Int.max, .unexpected)
        ]
        for (domain, code, expected) in cases {
            let error = UnreadableError(domain: domain, code: code)
            let sanitized = Policy.sanitized(error)
            precondition(sanitized.code == expected.rawValue)
            precondition(sanitized.userInfo["outcome"] as? String == (expected == .cancelled ? "cancelled" : "failed"))
            try check(sanitized)
        }
        // Spoofed/legacy records in our own domain still cannot carry userInfo.
        for category in Category.allCases {
            let legacy = NSError(domain: Policy.domain, code: category.rawValue, userInfo: [secret: secret])
            let rebuilt = Policy.sanitized(legacy)
            precondition(rebuilt.code == category.rawValue)
            try check(rebuilt)
        }
        // Use the source-screen expression itself, preserving empty/success
        // state and reconstructing a non-nil legacy error before display.
        struct SourceProbe { var error: NSError? }
        var source = SourceProbe(error: nil)
        precondition(source.error.map(Policy.sanitized) == nil)
        source.error = raw
        if let error = source.error.map(TetherlessErrorRecordPolicy.sanitized) {
            try check(error)
        } else { preconditionFailure("A stored failure disappeared") }
        precondition(source.error === raw)
        source.error = Policy.sanitized(raw)
        try check(source.error!)
        source.error = nil
        precondition(source.error.map(Policy.sanitized) == nil)
        print("error-history privacy passed")
    }
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            harness = root / 'main.swift'
            harness.write_text(source)
            for flags in ([], ['-O']):
                binary = root / ('release' if flags else 'debug')
                built = subprocess.run([shutil.which('swiftc'), '-swift-version', '6', '-parse-as-library',
                    *flags, str(m.OVERRIDE), str(harness), '-o', str(binary)],
                    capture_output=True, text=True, timeout=60)
                self.assertEqual(built.returncode, 0, built.stderr)
                result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, 'error-history privacy passed\n')
                self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
