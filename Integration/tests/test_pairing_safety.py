"""Pinned wireless safety contracts; compiled routes use synthetic data only."""
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
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load('pairing_safety')
prior = load('input_safety')
REVIEW = Path(os.environ.get('TETHERLESS_PAIRING_REVIEW_ROOT', ROOT.parent / 'Vendor/SideStore'))
AVAILABLE = all((REVIEW / name).is_file() for name in m.BLOBS)
LOGGERS = {
    'Dependencies/minimuxer/Sources/MinimuxerLogging.swift': 'ed1935e8a4695d6ef6ce2aa722ca588a0d23b33c',
    'Dependencies/minimuxer/DeviceGateway/DeviceGatewayLogging.swift': '7e30077f31ef2e8739a87ccef97f37f5b5fa8c7a',
}


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def prepared_inputs():
    result = {}
    for name, expected in m.BLOBS.items():
        raw = (REVIEW / name).read_bytes()
        if name in [m.MODEL, m.WRAPPER]:
            if blob(raw) != prior.BLOBS[name]:
                raise ValueError('Not the pinned original input: ' + name)
            raw = prior.PATCHES[name](raw.decode()).encode()
        if blob(raw) != expected:
            raise ValueError('Not the pinned prepared input: ' + name)
        result[name] = raw
    return result


class PairingSafetyTests(unittest.TestCase):
    def test_production_chain_includes_safety_after_input_hardening(self):
        prepare = (ROOT / 'prepare.py').read_text()
        self.assertLess(prepare.index('"input_safety.py"'), prepare.index('"archive_safety.py"'))
        chain = (ROOT / 'network_safety.py').read_text()
        self.assertIn('"pairing_safety.py"', chain)

    def test_patch_inventory_is_exact_and_not_a_runtime_feature_flag(self):
        self.assertEqual(set(m.BLOBS), set(m.PATCHES))
        self.assertTrue(all(len(x) == 40 for x in m.BLOBS.values()))
        source = (ROOT / 'pairing_safety.py').read_text()
        self.assertNotIn('UserDefaults', source)
        self.assertNotIn('lease.release()', source)
        self.assertNotIn('pairingSession = nil', source)

    def test_unknown_inputs_leave_every_file_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in m.BLOBS:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'unreviewed')
            with self.assertRaisesRegex(ValueError, 'Unreviewed'):
                m.apply(root)
            for name in m.BLOBS:
                self.assertEqual((root / name).read_bytes(), b'unreviewed')

    def test_pin_log_anchors_fail_closed_if_missing_or_duplicated(self):
        for fn in [m.patch_service, m.patch_gateway]:
            for source in ['', 'changed upstream']:
                with self.assertRaises(ValueError):
                    fn(source)

    @unittest.skipUnless(AVAILABLE, 'Pinned pairing source not mounted; native preimage checks not executed')
    def test_reviewed_transform_removes_values_and_preserves_protocol_callbacks(self):
        inputs = prepared_inputs()
        service = m.patch_service(inputs[m.SERVICE].decode())
        gateway = m.patch_gateway(inputs[m.GATEWAY].decode())
        self.assertIn('self.onPinReceived?(pinString)', service)
        self.assertIn('ctxObj.callback(pinStr)', gateway)
        self.assertIn('enteredPin = pin', gateway)
        for source in [service, gateway]:
            for line in source.splitlines():
                if 'debugLog(' in line or 'verboseLog(' in line:
                    self.assertNotIn('\\(pinString)', line)
                    self.assertNotIn('\\(pinStr)', line)
                    self.assertNotIn('\\(pin)', line)
        self.assertEqual(service.count('[WirelessPairService] pairing code is ready'), 1)
        self.assertEqual(gateway.count('[IdeviceGateway] pairing code'), 2)

    @unittest.skipUnless(AVAILABLE, 'Pinned pairing source not mounted; native preimage checks not executed')
    def test_gate_precedes_lease_storage_discovery_and_ffi(self):
        inputs = prepared_inputs()
        model = m.patch_model(inputs[m.MODEL].decode())
        wrapper = m.patch_wrapper(inputs[m.WRAPPER].decode())
        self.assertNotIn('NativePairingSession()', model)
        self.assertNotIn('session.importResult(', model)
        self.assertNotIn('wirelessPairing.start(', model)
        self.assertNotIn('wirelessPairing.trigger(', model)
        self.assertNotIn('minimuxer.wirelessPair.start(', wrapper)
        self.assertNotIn('minimuxer.wirelessPair.trigger(', wrapper)
        for method, following in [('openClientDialog', 'openServerDialog'), ('openServerDialog', 'onDialogAppear')]:
            part = model.split('    func ' + method + '() {')[1].split('    func ' + following)[0]
            self.assertNotIn('startDiscovery()', part)
            self.assertNotIn('isTargetDialogPresented = true', part)
        self.assertIn('Wireless pairing unavailable', model)
        self.assertIn('Existing pairing is retained', wrapper)
        self.assertNotIn('isShareSheetPresented = true', model)

    @unittest.skipUnless(AVAILABLE, 'Pinned pairing source not mounted; native preimage checks not executed')
    def test_apply_is_atomic_for_validation_failure_and_reapplication(self):
        inputs = prepared_inputs()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name, raw in inputs.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            # Last-input drift must not modify any earlier validated input.
            (root / m.GATEWAY).write_bytes(b'drift')
            before = {name: (root / name).read_bytes() for name in inputs}
            with self.assertRaises(ValueError):
                m.apply(root)
            self.assertEqual(before, {name: (root / name).read_bytes() for name in inputs})
            (root / m.GATEWAY).write_bytes(inputs[m.GATEWAY])
            m.apply(root)
            before = {name: (root / name).read_bytes() for name in inputs}
            with self.assertRaises(ValueError):
                m.apply(root)
            self.assertEqual(before, {name: (root / name).read_bytes() for name in inputs})

    @staticmethod
    def native_logger_method(source):
        start = '    public override func setLogging(_ enabled: Bool) {'
        end = '    private func syncStart('
        if source.count(start) != 1 or source.count(end) != 1:
            raise ValueError('Native logger method boundary drift')
        return start + source.split(start, 1)[1].split(end, 1)[0]

    @unittest.skipUnless(AVAILABLE, 'Pinned pairing source not mounted; native preimage checks not executed')
    def test_native_off_is_the_only_new_gateway_change(self):
        raw = prepared_inputs()[m.GATEWAY].decode()
        transformed = m.patch_gateway(raw)
        original_method = self.native_logger_method(raw)
        method = self.native_logger_method(transformed)
        self.assertEqual(m.BLOBS[m.GATEWAY], 'e9310d0236e244813ce945236bdb99af2582f649')
        # Restore only the new method. Every other byte must equal the actual
        # previously shipped PIN-only prepared gateway observed at cb8e4dd.
        restored = transformed.replace(method, original_method, 1).encode()
        self.assertEqual(blob(restored), '1b0874f599b0f5ed4453476d2ddb46f71e58070c')
        self.assertEqual(transformed.count('idevice_init_logger('), 1)
        self.assertIn('let disabled = IdeviceLogLevel(rawValue: 0)', method)
        self.assertIn('_ = idevice_init_logger(disabled, disabled, nil)', method)
        self.assertIn('super.setLogging(enabled)', method)
        self.assertNotIn('#if DEBUG', method)
        self.assertNotIn('rawValue: 5', method)
        self.assertNotIn('enabled ?', method)
        self.assertIn('setLogging(true)', transformed)  # Original DEBUG caller is unchanged.

    @unittest.skipUnless(AVAILABLE, 'Pinned pairing source not mounted; native preimage checks not executed')
    def test_native_logger_method_drift_and_duplication_fail_closed(self):
        raw = prepared_inputs()[m.GATEWAY].decode()
        method = self.native_logger_method(raw)
        for changed in [raw.replace(method, '', 1), raw + method,
                        raw.replace('let upperBoundLevel = IdeviceLogLevel(rawValue: 5)',
                                    'let upperBoundLevel = IdeviceLogLevel(rawValue: 4)', 1)]:
            with self.assertRaisesRegex(ValueError, 'Unreviewed'):
                m.patch_gateway(changed)

    @unittest.skipUnless(AVAILABLE, 'Pinned pairing source not mounted; native preimage checks not executed')
    def test_exact_native_logger_method_always_requests_off_in_debug_and_release(self):
        method = self.native_logger_method(m.patch_gateway(prepared_inputs()[m.GATEWAY].decode()))
        source = '''import Foundation
// This records FFI arguments only. No binary logger or device is invoked.
struct IdeviceLogLevel { let rawValue: UInt32 }
struct NativeLoggerCall: Equatable {
    let console: UInt32
    let file: UInt32
    let pathWasNil: Bool
}
final class NativeLoggerSpy: @unchecked Sendable {
    static let shared = NativeLoggerSpy()
    private let lock = NSLock()
    private var calls: [NativeLoggerCall] = []
    func record(_ call: NativeLoggerCall) { lock.withLock { calls.append(call) } }
    func snapshot() -> [NativeLoggerCall] { lock.withLock { calls } }
}
func idevice_init_logger(_ console: IdeviceLogLevel, _ file: IdeviceLogLevel,
                         _ path: UnsafeMutablePointer<CChar>?) -> Int32 {
    NativeLoggerSpy.shared.record(NativeLoggerCall(console: console.rawValue,
                                                   file: file.rawValue, pathWasNil: path == nil))
    return 0
}
public class BaseDeviceGateway {
    var requests: [Bool] = []
    public func setLogging(_ enabled: Bool) { requests.append(enabled) }
}
public final class Gateway: BaseDeviceGateway {
''' + method + '\n}\n'
        main = '''import Foundation
let sequences = [[false, true, true, false, false, true],
                 [true, false, true, false, true, true]]
for requests in sequences {
    let gateway = Gateway()
    let before = NativeLoggerSpy.shared.snapshot().count
    for enabled in requests { gateway.setLogging(enabled) }
    precondition(gateway.requests == requests, "Swift logging preference changed")
    let received = Array(NativeLoggerSpy.shared.snapshot().dropFirst(before))
    let off = NativeLoggerCall(console: 0, file: 0, pathWasNil: true)
    precondition(received == Array(repeating: off, count: requests.count),
                 "Native logging was enabled or a file path was supplied")
}
print("NATIVE_LOGGER_OFF_ARGUMENTS_PASSED")
'''
        for flags in [('-D', 'DEBUG', '-Onone'), ('-O',)]:
            with self.subTest(flags=flags):
                self.assertEqual(self.compile_run({'NativeLogger.swift': source}, main, flags),
                                 'NATIVE_LOGGER_OFF_ARGUMENTS_PASSED\n')

    def compile_run(self, sources, main, flags=()):
        compiler = shutil.which('swiftc')
        if not compiler:
            self.skipTest('Swift compiler unavailable; compiled safety boundary not executed')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            files = []
            for name, source in sources.items():
                path = root / name
                path.write_text(source)
                files.append(str(path))
            (root / 'main.swift').write_text(main)
            result = subprocess.run([compiler, '-swift-version', '6', *flags, *files, str(root / 'main.swift'),
                                     '-o', str(root / 'test')], capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(root / 'test')], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

    @unittest.skipUnless(AVAILABLE, 'Pinned pairing source not mounted; native preimage checks not executed')
    def test_exact_gated_wrapper_completes_once_without_transport_or_filename_callback(self):
        wrapper = m.patch_wrapper(prepared_inputs()[m.WRAPPER].decode())
        methods = '    public func start(' + wrapper.split('    public func start(', 1)[1].split('    public func stop() {', 1)[0]
        source = '''import Foundation
public struct MinimuxerPairedDevice: Sendable {}
public enum OperationError: Error { case invalidParameters(String) }
public enum AppConstants { public enum Minimuxer {
    public static let defaultHostName = "synthetic"
    public static let defaultHostModel = "synthetic"
} }
struct Harness {
    static let unavailableReason = "''' + m.UNAVAILABLE + '''"
''' + methods + '\n}\n'
        main = '''import Foundation
let harness = Harness()
var completions = 0
func verify(_ result: Result<MinimuxerPairedDevice, Error>) {
    switch result {
    case .success: fatalError("A gated operation succeeded")
    case .failure(let error):
        guard case OperationError.invalidParameters(let reason) = error else { fatalError("Wrong error") }
        precondition(reason == Harness.unavailableReason)
    }
}
for _ in 0..<3 {
    harness.start(outPath: "/must-not-create", resolveFileName: { _, _ in fatalError("Filename callback ran") }) {
        verify($0); completions += 1
    }
    harness.trigger(targetIp: "192.0.2.1", targetPort: 1, outPath: "/must-not-create",
                    resolveFileName: { _, _ in fatalError("Filename callback ran") }) {
        verify($0); completions += 1
    }
}
precondition(completions == 6)
print("PASS")
'''
        self.assertEqual(self.compile_run({'Gate.swift': source}, main), 'PASS\n')

    @unittest.skipUnless(AVAILABLE, 'Pinned pairing source not mounted; native preimage checks not executed')
    def test_synthetic_pins_absent_with_real_upstream_loggers_in_both_modes(self):
        inputs = prepared_inputs()
        cases = [(next(iter(LOGGERS)), 'MinimuxerLogging', m.patch_service(inputs[m.SERVICE].decode())),
                 (list(LOGGERS)[1], 'DeviceGatewayLogging', m.patch_gateway(inputs[m.GATEWAY].decode()))]
        for path, symbol, transformed in cases:
            raw = (REVIEW / path).read_bytes()
            self.assertEqual(blob(raw), LOGGERS[path])
            # The logger itself is unchanged; only external logging bridges are
            # harmless stand-ins for compilation outside its package.
            logger = raw.decode().replace('internal import MinimuxerCommon\n', '').replace('import DeviceGatewayAPI\n', '')
            if symbol == 'MinimuxerLogging':
                logger += '''\nenum MinimuxerCommonLogging { static func setLogging(_ value: Bool) {} }
enum DeviceGatewayLogging { static func setLogging(_ value: Bool) {} }
'''
            statements = '\n'.join(line.strip() for line in transformed.splitlines()
                                   if 'Log(' in line and '] pairing code ' in line)
            self.assertTrue(statements)
            main = '''import Foundation
let pinString = "SYNTHETIC_GENERATED_PIN_730491"
let pinStr = "SYNTHETIC_DISPLAY_PIN_827630"
let pin = "SYNTHETIC_ENTERED_PIN_619285"
for enabled in [false, true] {
''' + symbol + '.setLogging(enabled)\n' + statements + '\n}\nprint("PASS")\n'
            output = self.compile_run({'Logger.swift': logger}, main)
            self.assertNotIn('SYNTHETIC_', output)
            for secret in ['730491', '827630', '619285']:
                self.assertNotIn(secret, output)
            self.assertIn('pairing code', output)
            self.assertTrue(output.endswith('PASS\n'))


if __name__ == '__main__':
    unittest.main()
