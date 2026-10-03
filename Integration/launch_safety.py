#!/usr/bin/env python3
"""Resolve real Simulator App Groups and gate UI on successful database startup."""
from pathlib import Path
import hashlib
import sys

LAUNCH = 'AltStore/LaunchViewController.swift'
BUNDLE = 'Shared/Extensions/Bundle+AltStore.swift'
BLOBS = {LAUNCH: 'b2cebcc01b305789aedca690448c08b5e62aa6ad',
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
private func tetherlessLoadedSimulatorGroups() -> [String] {
    guard let header = _dyld_get_image_header(0),
          header.pointee.magic == MH_MAGIC_64 else { return [] }
    let image = UnsafeRawPointer(header).assumingMemoryBound(to: mach_header_64.self)
    var size: UInt = 0
    guard let bytes = getsectiondata(image, "__TEXT", "__entitlements", &size),
          size > 0, size <= 1_048_576 else { return [] }
    var data = Data(bytes: bytes, count: Int(size))
    while data.last == 0 { data.removeLast() }
    guard let plist = try? PropertyListSerialization.propertyList(from: data, options: [], format: nil),
          let dictionary = plist as? [String: Any],
          let groups = dictionary["com.apple.security.application-groups"] as? [String] else { return [] }
    return groups
}
#endif
''')
    return once(source, '    var appGroups: [String] {\n', '''    var appGroups: [String] {
        #if targetEnvironment(simulator)
        if self.bundleURL == Bundle.main.bundleURL {
            return tetherlessLoadedSimulatorGroups()
        }
        #endif
''')


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


def apply(root):
    outputs = {}
    for relative, patch in [(BUNDLE, patch_bundle), (LAUNCH, patch_launch)]:
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
