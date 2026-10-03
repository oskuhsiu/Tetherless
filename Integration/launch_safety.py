#!/usr/bin/env python3
"""Resolve real Simulator App Groups and gate UI on successful database startup."""
from pathlib import Path
import hashlib
import sys

LAUNCH = 'AltStore/LaunchViewController.swift'
BUNDLE = 'Shared/Extensions/Bundle+AltStore.swift'
CONTAINER = 'AltStore/Core/Model/DatabaseManager/PersistentContainer.swift'
BLOBS = {CONTAINER: '594f5463473a949ec1d0e94a8aeb7a6bde392e44', LAUNCH: 'b2cebcc01b305789aedca690448c08b5e62aa6ad',
         BUNDLE: '54f1ea2c417e0152baf04d433e0b4f3ed17681e7'}


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Launch safety anchor changed')
    return source.replace(old, new, 1)


def patch_bundle(source):
    source = once(source, 'import CodeSignKit\n', '''import CodeSignKit
#if targetEnvironment(simulator)
import MachO

/// Only the already-loaded main Simulator executable is inspected. Simulator
/// iOS entitlements live in __TEXT, not the macOS host ad-hoc signature.
/// Never synthesize a group or redirect the database to a sandbox fallback.
private struct TetherlessSimulatorGroupProbe {
    let groups: [String]
    let stage: String
}
private let tetherlessSimulatorGroupProbe: TetherlessSimulatorGroupProbe = {
    func failure(_ stage: String) -> TetherlessSimulatorGroupProbe { .init(groups: [], stage: stage) }
    guard let executable = Bundle.main.executableURL else { return failure("missing-executable-url") }
    let expected = executable.resolvingSymlinksInPath().standardizedFileURL
    let count = _dyld_image_count()
    guard count > 0, count <= 4096 else { return failure("image-table-limit") }
    var matchedHeader: UnsafePointer<mach_header>?
    for index in 0..<count {
        guard let name = _dyld_get_image_name(index) else { continue }
        let actual = URL(fileURLWithPath: String(cString: name)).resolvingSymlinksInPath().standardizedFileURL
        if actual == expected { matchedHeader = _dyld_get_image_header(index); break }
    }
    guard let header = matchedHeader else { return failure("executable-not-loaded") }
    guard header.pointee.magic == MH_MAGIC_64, header.pointee.filetype == MH_EXECUTE else {
        return failure("unexpected-executable-header")
    }
    let image = UnsafeRawPointer(header).assumingMemoryBound(to: mach_header_64.self)
    var size: UInt = 0
    guard let bytes = getsectiondata(image, "__TEXT", "__entitlements", &size),
          size > 0, size <= 1_048_576 else { return failure("missing-or-oversized-section") }
    var data = Data(bytes: bytes, count: Int(size))
    while data.last == 0 { data.removeLast() }
    guard let plist = try? PropertyListSerialization.propertyList(from: data, options: [], format: nil),
          let dictionary = plist as? [String: Any] else { return failure("invalid-linked-plist") }
    guard let groups = dictionary["com.apple.security.application-groups"] as? [String],
          !groups.isEmpty else { return failure("linked-groups-absent") }
    return .init(groups: groups, stage: "linked-groups-present")
}()

#endif
''')
    source = once(source, '    var appGroups: [String] {\n', '''    var appGroups: [String] {
        #if targetEnvironment(simulator)
        if self.bundleURL == Bundle.main.bundleURL {
            return tetherlessSimulatorGroupProbe.groups
        }
        #endif
''')
    return once(source, '    @objc dynamic var altstoreAppGroup: String? {', '''    // Only allowlisted categories are exposed: never group IDs or paths.
    var tetherlessAppGroupDiagnostic: String {
        #if targetEnvironment(simulator)
        if self.bundleURL == Bundle.main.bundleURL && tetherlessSimulatorGroupProbe.groups.isEmpty {
            return tetherlessSimulatorGroupProbe.stage
        }
        #endif
        guard !appGroups.isEmpty else { return "signature-groups-absent" }
        guard altstoreAppGroup != nil else { return "no-matching-app-group" }
        return "group-present-container-unavailable"
    }

    @objc dynamic var altstoreAppGroup: String? {''')


def patch_launch(source):
    source = once(source, '    private var didFinishLaunching = false\n',
                  '    private var didFinishLaunching = false\n'
                  '    private var launchReadiness = LaunchReadiness(onboardingDismissed: true)\n')
    source = once(source, '''                let hostingController = UIHostingController(rootView: OnboardingView { [weak self] in
                    Task { @MainActor in
                        self?.transitionToMainInterface()
''', '''                launchReadiness = LaunchReadiness(onboardingDismissed: false)
                let hostingController = UIHostingController(rootView: OnboardingView { [weak self] in
                    Task { @MainActor in
                        self?.launchReadiness.dismissOnboarding()
                        self?.transitionToMainInterface()
''')
    # Both completion orders go through the same database-ready transition.
    # The old wizard callback entered the main interface even after DB failure.
    source = once(source, '''        #if !os(tvOS)
            if #available(iOS 17.0, *), !UserDefaults.standard.hasCompletedOnboarding {
                await AppManager.shared.reconcileInstalledApps()
                AppManager.shared.updateAllSources { _ in }
                updateKnownSources()
                didFinishLaunching = true
                return
            }
        #endif

''', '')
    source = once(source, '''        transitionToMainInterface()
    }

    @MainActor
    private func transitionToMainInterface() {
''', '''        launchReadiness.databaseDidStart()
        transitionToMainInterface()
    }

    @MainActor
    private func transitionToMainInterface() {
        guard launchReadiness.claimTransition() else { return }
''')
    return source


def patch_container(source):
    return once(source,
        'reason: NSLocalizedString("Unable to access the shared App Group container. Refusing to create or use a private sandbox fallback database.", comment: "")',
        'reason: NSLocalizedString("Unable to access the shared App Group container. Refusing to create or use a private sandbox fallback database.", comment: "") + " [group/" + Bundle.main.tetherlessAppGroupDiagnostic + "]"')


def apply(root):
    outputs = {}
    for relative, patch in [(BUNDLE, patch_bundle), (LAUNCH, patch_launch), (CONTAINER, patch_container)]:
        raw = (root / relative).read_bytes()
        digest = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if digest != BLOBS[relative]:
            raise ValueError('Unreviewed launch input: ' + relative)
        outputs[relative] = patch(raw.decode())
    # Validate all sources before publishing any replacement.
    for relative, content in outputs.items():
        (root / relative).write_text(content)


if __name__ == '__main__':
    apply(Path(sys.argv[1]))
