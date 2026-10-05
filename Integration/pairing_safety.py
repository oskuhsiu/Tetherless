#!/usr/bin/env python3
"""Pinned PIN/native-log privacy and temporary wireless cancellation safety gate.

The existing imported-record path remains available. This gate is not completion
of PAIR-01: do not enable wireless generation until the native worker can be
cancelled and joined without sending a fabricated PIN or dropping its lease.
"""
from pathlib import Path
import hashlib
import sys

MODEL = 'SideStore/Views/Settings/Advanced/PairingFile/WirelessPair/WirelessPairViewModel.swift'
WRAPPER = 'SideStore/Core/DeviceApi/MinimuxerWrapper.swift'
SERVICE = 'Dependencies/minimuxer/Sources/Services/WirelessPairService.swift'
GATEWAY = 'Dependencies/minimuxer/DeviceGateway/idevice/IdeviceGateway.swift'

# MODEL and WRAPPER are exact outputs of input_safety.py. minimuxer is unchanged
# by preceding transformations. All inputs are checked before any output write.
BLOBS = {
    MODEL: 'e77eecac67d8dfbf2e4fa573287bcefa7c9fec65',
    WRAPPER: 'd6fcf7f9203c7a9db3236efef3ae5aa209be7778',
    SERVICE: '1a24b36ddad6f1c6c13ae8daa06a14b65d1fdabd',
    GATEWAY: 'e9310d0236e244813ce945236bdb99af2582f649',
}

UNAVAILABLE = ('Wireless pairing is unavailable in this build while safe cancellation '
               'is being completed. Import a pairing record from your authorized '
               'bootstrap process. Existing pairing is retained.')


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Unreviewed pairing safety anchor')
    return source.replace(old, new, 1)


def body(source, signature, next_signature, replacement):
    """Replace one reviewed method including its body, preserving the next one."""
    if source.count(signature) != 1 or source.count(next_signature) != 1:
        raise ValueError('Unreviewed pairing safety method boundary')
    before, tail = source.split(signature)
    _, after = tail.split(next_signature)
    return before + signature + replacement + next_signature + after


def patch_service(source):
    # Remove the value at its source, not just from a disabled logging mode.
    return once(source,
        'debugLog("[WirelessPairService] gateway onPin callback (pin=\'\\(pinString)\')")',
        'debugLog("[WirelessPairService] pairing code is ready")')


def patch_gateway(source):
    source = once(source,
        'verboseLog("[IdeviceGateway] startWirelessPair() received pin: \\(pinStr)")',
        'verboseLog("[IdeviceGateway] pairing code is ready")')
    source = once(source,
        'debugLog("[IdeviceGateway] pin_callback received user entered PIN: \'\\(pin)\'")',
        'debugLog("[IdeviceGateway] pairing code was supplied")')
    # The native tracing subscriber is process-global and initializes only once.
    # Debug's first call previously selected Trace even for enabled == false.
    # Consume the same supported initializer with no console/file sinks in both
    # build modes; later user preferences and DEBUG start cannot enable it.
    return once(source, '''    public override func setLogging(_ enabled: Bool) {
        let lowerBoundLevel = IdeviceLogLevel(rawValue: 0)
        #if DEBUG
        let upperBoundLevel = IdeviceLogLevel(rawValue: 5)
        #else
        let upperBoundLevel = IdeviceLogLevel(rawValue: enabled ? 1 : 0)
        #endif
        // set actual logging
        idevice_init_logger(upperBoundLevel, lowerBoundLevel, nil)
        super.setLogging(enabled)
    }''', '''    public override func setLogging(_ enabled: Bool) {
        // Native payload logging is disabled for the lifetime of this process.
        // The native logger is Once-initialized; a later false call cannot undo
        // an earlier enabled subscriber. Preserve the Swift logging preference.
        let disabled = IdeviceLogLevel(rawValue: 0)
        _ = idevice_init_logger(disabled, disabled, nil)
        super.setLogging(enabled)
    }''')


def patch_wrapper(source):
    # Defence in depth: no caller can reach the non-cancellable native start or
    # trigger through the product wrapper, even outside the current view model.
    marker = 'public final class WirelessPairWrapper {'
    source = once(source, marker, marker + '\n    public static let unavailableReason = "' + UNAVAILABLE + '"\n')
    start = '''    public func start(
        outPath: String,
        resolveFileName: (@Sendable (String, String) -> String)? = nil,
        completion: @escaping (Result<MinimuxerPairedDevice, Error>) -> Void
    ) {'''
    trigger = '''    public func trigger(
        targetIp: String,
        targetPort: UInt16,
        hostName: String = AppConstants.Minimuxer.defaultHostName,
        hostModel: String = AppConstants.Minimuxer.defaultHostModel,
        outPath: String,
        resolveFileName: (@Sendable (String, String) -> String)? = nil,
        completion: @escaping (Result<MinimuxerPairedDevice, Error>) -> Void
    ) {'''
    denied = '''
        // No native worker, socket, PIN request or output file is created.
        completion(.failure(OperationError.invalidParameters(Self.unavailableReason)))
    }

'''
    source = body(source, start, trigger, denied)
    return body(source, trigger, '    public func stop() {', denied)


def patch_model(source):
    source = once(source, '@Published var statusText = "Ready to pair"',
                  '@Published var statusText = "Wireless pairing unavailable"')
    source = once(source,
                  '@Published var subStatusText = "Tap Start to advertise this device on the local network."',
                  '@Published var subStatusText = WirelessPairWrapper.unavailableReason')
    denied = '''
        statusText = "Wireless pairing unavailable"
        subStatusText = WirelessPairWrapper.unavailableReason
        errorMessage = WirelessPairWrapper.unavailableReason
    }

'''
    for signature, next_signature in [
        ('    func openClientDialog() {', '    func openServerDialog() {'),
        ('    func openServerDialog() {', '    func onDialogAppear() {'),
        ('    func togglePairing() {', '    func startPairing() {'),
        ('    func startPairing() {', '    func stopPairing() {'),
    ]:
        source = body(source, signature, next_signature, denied)
    trigger = '''    func triggerPairing(
        targetIp: String,
        targetPort: UInt16,
        targetName: String? = nil,
        completion: ((Result<MinimuxerPairedDevice, Swift.Error>) -> Void)? = nil
    ) {'''
    trigger_denied = '''
        statusText = "Wireless pairing unavailable"
        subStatusText = WirelessPairWrapper.unavailableReason
        errorMessage = WirelessPairWrapper.unavailableReason
        completion?(.failure(OperationError.invalidParameters(WirelessPairWrapper.unavailableReason)))
    }

'''
    return body(source, trigger, '    nonisolated static func pairingFileName(', trigger_denied)


PATCHES = {MODEL: patch_model, WRAPPER: patch_wrapper,
           SERVICE: patch_service, GATEWAY: patch_gateway}


def apply(root: Path):
    outputs = {}
    for name, expected in BLOBS.items():
        data = (root / name).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if actual != expected:
            raise ValueError('Unreviewed pairing safety source: ' + name)
        outputs[name] = PATCHES[name](data.decode())
    for name, source in outputs.items():
        (root / name).write_text(source)


if __name__ == '__main__':
    apply(Path(sys.argv[1]))
