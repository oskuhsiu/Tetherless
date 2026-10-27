#!/usr/bin/env python3
"""Pinned pairing/import hardening. Applied to a disposable, prepared native tree."""
from pathlib import Path
import hashlib
import sys

PAIR = 'SideStore/Core/Pairing/PairingFileManager.swift'
MODEL = 'SideStore/Views/Settings/Advanced/PairingFile/PairingFileManagementViewModel.swift'
DETAIL = 'SideStore/Views/Settings/Advanced/PairingFile/PairingFileDetailView.swift'
PICKER = 'SideStore/Views/Settings/Advanced/PairingFile/PairingViewController.swift'
WIRELESS = 'SideStore/Views/Settings/Advanced/PairingFile/WirelessPair/WirelessPairViewModel.swift'
MAINTENANCE = 'SideStore/MaintenanceManager.swift'
WRAPPER = 'SideStore/Core/DeviceApi/MinimuxerWrapper.swift'


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Pairing patch anchor changed')
    return source.replace(old, new, 1)


def between(source, start, end, replacement):
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError('Pairing patch boundary changed')
    before, tail = source.split(start)
    _, after = tail.split(end)
    return before + replacement + end + after


def patch_model(source):
    source = once(source, '''        PairingFileManager.shared.deletePairingFile(for: proto)
        refresh()''', '''        Task { @MainActor in
            do {
                try await NativeMutationGate.withLease {
                    try await minimuxerStop()
                    try PairingFileManager.shared.deletePairingFile(for: proto)
                }
                refresh()
            } catch { activeAlert = .importError("Pairing deletion could not complete; another operation may be active.") }
        }''')
    source = once(source, '''        PairingFileManager.shared.resetAllPairingFiles()
        refresh()
        activeAlert = .resetCompleted''', '''        Task { @MainActor in
            do {
                try await NativeMutationGate.withLease {
                    try await minimuxerStop()
                    try PairingFileManager.shared.resetAllPairingFiles()
                }
                refresh()
                activeAlert = .resetCompleted
            } catch { activeAlert = .importError("Pairing reset could not complete. Retry after other operations finish.") }
        }''')
    source = once(source, '''            PairingFileManager.shared.preferredProtocol = newProtocol
            try PairingFileManager.shared.importPairingFile(from: url, preferred: newProtocol)''', '''            try NativeMutationGate.withSynchronousLease {
                try PairingFileManager.shared.importPairingFile(from: url, preferred: newProtocol)
                PairingFileManager.shared.preferredProtocol = newProtocol
            }''')
    source = once(source, '''        PairingFileManager.shared.preferredProtocol = proto
        refresh()''', '''        do {
            try NativeMutationGate.withSynchronousLease { PairingFileManager.shared.preferredProtocol = proto }
            refresh()
        } catch { activeAlert = .importError("Finish the active operation before changing pairing preferences.") }''')
    return once(source, '''        PairingFileManager.shared.preferredProtocol = nil
        refresh()''', '''        do {
            try NativeMutationGate.withSynchronousLease { PairingFileManager.shared.preferredProtocol = nil }
            refresh()
        } catch { activeAlert = .importError("Finish the active operation before changing pairing preferences.") }''')


def patch_picker(source):
    source = once(source, '''                    PairingFileManager.shared.preferredProtocol = providedProtocol
                    PairingFileManager.shared.persistedActiveProtocol = providedProtocol
                    continuation.resume(returning: true)''', '''                    do {
                        try NativeMutationGate.withSynchronousLease {
                            PairingFileManager.shared.preferredProtocol = providedProtocol
                            PairingFileManager.shared.persistedActiveProtocol = providedProtocol
                        }
                        continuation.resume(returning: true)
                    } catch { continuation.resume(returning: false) }''')
    # Cancelling a picker must not undo a durable reset tombstone.
    source = once(source, '            UserDefaults.standard.isPairingReset = false\n', '')
    return '\n'.join(line for line in source.split('\n') if 'debugLog(' not in line)


def patch_detail(source):
    return between(source, '''        do {
            _ = try PropertyListSerialization.propertyList(from: data, options: [], format: nil)''',
        '''        do {
            try PairingFileManager.shared.savePairingFile''', '''        guard data.count <= PairingRecord.maximumBytes else {
            invalidPlistMessage = "Pairing file is too large."
            showingInvalidPlistAlert = true
            return
        }

''')


def patch_maintenance(source):
    marker = '    func migratePairingFiles() async {'
    if source.count(marker) != 1 or not source.rstrip().endswith('}\n}'):
        raise ValueError('Maintenance pairing boundary changed')
    source = source.split(marker)[0] + '''    func migratePairingFiles() async {
        // Actual migration is performed before maintenance-counter checks below.
        // Do not copy private pairing records back into Documents.
    }
}
'''
    signature = '    public func performMaintenanceIfNeeded() async {'
    return once(source, signature, '''    public func performMaintenanceIfNeeded() async {
        do {
            try await NativeMutationGate.withLease {
                try PairingFileManager.shared.migrateLegacyFiles()
                await self.performMaintenanceWithLease()
            }
        } catch {
            // Keep both the source and maintenance counter on failure/busy.
            // No raw file content or device identifier is logged.
        }
    }

    private func performMaintenanceWithLease() async {''')


def patch_wrapper(source):
    start = 'func minimuxerSwitchPairingProtocol(to proto: PairingProtocol) async throws {'
    source = once(source, start, start + '''
    try await NativeMutationGate.withLease { try await switchPairingWithLease(to: proto) }
}

private func switchPairingWithLease(to proto: PairingProtocol) async throws {''')
    return source


def patch_wireless(source):
    marker = 'final class WirelessPairViewModel: ObservableObject {'
    source = once(source, marker, marker + '\n    private var pairingSession: NativePairingSession?\n')
    # Both entry points must prepare a protected, random directory while holding
    # the process lease. No raw device-supplied name enters a filesystem path.
    start = '        let docsPath = FileManager.default.documentsDirectory.path'
    if source.count(start) != 2:
        raise ValueError('Wireless output-path count changed')
    source = source.replace(start, '''        guard pairingSession == nil else { return }
        let session: NativePairingSession
        do { session = try NativePairingSession() }
        catch {
            errorMessage = "Pairing cannot start while another operation is active or protected storage is unavailable."
            return
        }
        pairingSession = session
        let docsPath = session.directory.path''')
    callback = '        ) { [weak self] (result: Result<MinimuxerPairedDevice, Swift.Error>) in'
    if source.count(callback) != 2:
        raise ValueError('Wireless callback count changed')
    source = source.replace(callback, '''        ) { [weak self, session] (result: Result<MinimuxerPairedDevice, Swift.Error>) in''')
    # Work on method tails only, not unrelated weak-self discovery callbacks.
    before, tail = source.split('    func startPairing() {')
    tail = tail.replace('                guard let self = self else { return }', '''                guard let self, self.pairingSession === session else { return }
                defer { self.pairingSession = nil }
                let result = result.flatMap { device -> Result<MinimuxerPairedDevice, Swift.Error> in
                    do { return .success(try session.importResult(device)) }
                    catch { return .failure(PrivateFileError.invalidContent) }
                }''')
    tail = tail.replace('        wirelessPairing.stop()', '''        guard pairingSession != nil else { return }
        wirelessPairing.stop()
        pairingSession = nil''')
    tail = tail.replace('Pairing file saved to documents.', 'Pairing saved in protected local storage.')
    tail = tail.replace('                    self.shareSheetURL = URL(fileURLWithPath: device.pairingFilePath)\n                    self.isShareSheetPresented = true',
                        '                    self.shareSheetURL = nil\n                    self.isShareSheetPresented = false')
    tail = between(tail, '    nonisolated static func pairingFileName(',
                   '    private func pairingFilePath(', '''    nonisolated static func pairingFileName(for deviceName: String? = nil, model: String? = nil) -> String {
        "pairing.plist"
    }

''')
    source = before + '    func startPairing() {' + tail
    # No PIN values in logs, and no fake 000000 on empty input/cancel.
    source = once(source, '''        let finalPin = pin.isEmpty ? "000000" : pin''', '''        guard pin.count == 6, pin.utf8.allSatisfy({ (48...57).contains($0) }) else {
            errorMessage = "Enter the six-digit pairing PIN."
            return
        }
        let finalPin = pin''')
    source = once(source, '        pinPromptCallback?("000000")', '        stopPairing()')
    return '\n'.join(line for line in source.split('\n') if 'debugLog(' not in line)

PATCHES = {MODEL: patch_model, PICKER: patch_picker, DETAIL: patch_detail,
           MAINTENANCE: patch_maintenance, WIRELESS: patch_wireless, WRAPPER: patch_wrapper}
BLOBS = {'SideStore/Core/Pairing/PairingFileManager.swift': '7af80486942e1d0edac5d4a4bee6b6d68284b6df', 'SideStore/Views/Settings/Advanced/PairingFile/PairingFileManagementViewModel.swift': 'c000671607e601568fdab500327d47c2ae4a79ae', 'SideStore/Views/Settings/Advanced/PairingFile/PairingViewController.swift': '1b125bb926ad15626b246d22726219f78209ee87', 'SideStore/Views/Settings/Advanced/PairingFile/PairingFileDetailView.swift': 'c391a3ef616d68687a92d216906623ca0a446853', 'SideStore/MaintenanceManager.swift': '84edde4ec2f245eff6d389c2a310553982fcba69', 'SideStore/Views/Settings/Advanced/PairingFile/WirelessPair/WirelessPairViewModel.swift': '2a6c7514b9ad10638daa71551669b312e1f46479', 'SideStore/Core/DeviceApi/MinimuxerWrapper.swift': '9dfb2c5d9f8a52efc34b9dbefb4447712ee88587'}


def apply(root: Path) -> None:
    outputs = {}
    for path in [PAIR, *PATCHES]:
        raw = (root / path).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != BLOBS[path]:
            raise ValueError('Unreviewed pairing source: ' + path)
        outputs[root / path] = (Path(__file__).parent / 'Overrides/PairingFileManager.swift').read_text() if path == PAIR else PATCHES[path](raw.decode())
    for path, content in outputs.items():
        path.write_text(content)

if __name__ == '__main__':
    apply(Path(sys.argv[1]))
