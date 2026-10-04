// SPDX-License-Identifier: AGPL-3.0-only
// Simulator-only test document source. Never linked into Tetherless.
import Foundation
import UIKit
import UniformTypeIdentifiers

@main
@MainActor
final class DocumentFixtureApp: UIResponder, UIApplicationDelegate {
    var window: UIWindow?

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        let label = UILabel()
        label.numberOfLines = 0
        label.textAlignment = .center
        let controller = DocumentPickerControl()
        controller.view.backgroundColor = .systemBackground
        label.translatesAutoresizingMaskIntoConstraints = false
        controller.view.addSubview(label)
        NSLayoutConstraint.activate([
            label.leadingAnchor.constraint(equalTo: controller.view.leadingAnchor, constant: 16),
            label.trailingAnchor.constraint(equalTo: controller.view.trailingAnchor, constant: -16),
            label.centerYAnchor.constraint(equalTo: controller.view.centerYAnchor)
        ])
        window = UIWindow(frame: UIScreen.main.bounds)
        window?.rootViewController = controller
        window?.makeKeyAndVisible()
        do {
            try publishInvalidDocument()
            label.text = "Invalid public test document ready"
            label.accessibilityIdentifier = "fixture.documentReady"
        } catch {
            label.text = "Test document preparation failed"
            label.accessibilityIdentifier = "fixture.documentFailed"
        }
        return true
    }

    private func publishInvalidDocument() throws {
        enum Failure: Error { case invalidPayload, unsafeFile, unavailable }
        guard let input = Bundle.main.url(forResource: "InvalidPairingFixture", withExtension: "plist") else {
            throw Failure.invalidPayload
        }
        let payload = try Data(contentsOf: input)
        // This helper cannot turn into a source of simulated valid credentials.
        guard payload.count == 241,
              let object = try PropertyListSerialization.propertyList(from: payload, format: nil) as? [String: Bool],
              object == ["TetherlessInvalidPairingFixture": true] else { throw Failure.invalidPayload }
        let directory = try FileManager.default.url(for: .documentDirectory, in: .userDomainMask,
                                                     appropriateFor: nil, create: true)
        let output = directory.appendingPathComponent("Tetherless-Invalid-Pairing.plist")
        let coordinator = NSFileCoordinator(filePresenter: nil)
        var coordinationError: NSError?
        var result: Result<Void, Error>?
        coordinator.coordinate(writingItemAt: output, options: .forReplacing, error: &coordinationError) { url in
            result = Result {
                if FileManager.default.fileExists(atPath: url.path) {
                    let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
                    guard values.isRegularFile == true, values.isSymbolicLink != true,
                          values.fileSize == payload.count, try Data(contentsOf: url) == payload else {
                        throw Failure.unsafeFile
                    }
                } else {
                    try payload.write(to: url, options: .withoutOverwriting)
                }
                guard try Data(contentsOf: url) == payload else { throw Failure.unavailable }
            }
        }
        guard coordinationError == nil, let result else { throw Failure.unavailable }
        try result.get()
    }
}

/// Deliberately independent UIKit control. It has no SwiftUI, Tetherless import
/// flow, success backend or test-triggered delegate invocation. The test only
/// opens it AFTER the original product outcome has already failed and is frozen.
@MainActor
final class DocumentPickerControl: UIViewController, UIDocumentPickerDelegate {
    private enum Outcome: String {
        case idle, waiting, selectedFileURL, invalidSelection, cancelled
    }
    private let resultLabel = UILabel()
    private let openButton = UIButton(type: .system)
    private var activePicker: UIDocumentPickerViewController?

    override func viewDidLoad() {
        super.viewDidLoad()
        openButton.setTitle("Open independent system picker", for: .normal)
        openButton.accessibilityIdentifier = "fixture.openControl"
        openButton.addTarget(self, action: #selector(openControl), for: .touchUpInside)
        resultLabel.accessibilityIdentifier = "fixture.controlOutcome"
        resultLabel.textAlignment = .center
        let controls: [UIView] = [openButton, resultLabel]
        for item in controls {
            item.translatesAutoresizingMaskIntoConstraints = false
            view.addSubview(item)
        }
        NSLayoutConstraint.activate([
            openButton.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            openButton.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -65),
            resultLabel.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            resultLabel.topAnchor.constraint(equalTo: openButton.bottomAnchor, constant: 12)
        ])
        observe(.idle)
    }

    @objc private func openControl() {
        guard activePicker == nil, presentedViewController == nil else { return }
        // The same open-in-place semantics; never switch to copying or invoke
        // an app-owned fake picker to manufacture callback delivery.
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: [.propertyList, .xml], asCopy: false)
        picker.allowsMultipleSelection = false
        picker.shouldShowFileExtensions = true
        picker.delegate = self
        picker.modalPresentationStyle = .fullScreen
        activePicker = picker
        openButton.isEnabled = false
        observe(.waiting)
        present(picker, animated: true)
    }

    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        guard controller === activePicker else { return }
        let valid = urls.count == 1 && urls.first?.isFileURL == true
        // No URL/path/content is logged. This reports callback delivery only,
        // not byte access, pairing validity or product acceptance.
        observe(valid ? .selectedFileURL : .invalidSelection)
        finish(controller)
    }

    func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        guard controller === activePicker else { return }
        observe(.cancelled)
        finish(controller)
    }

    private func finish(_ controller: UIDocumentPickerViewController) {
        controller.delegate = nil
        controller.dismiss(animated: true)
        activePicker = nil
        openButton.isEnabled = true
    }

    private func observe(_ outcome: Outcome) {
        resultLabel.text = outcome.rawValue
        print("[Tetherless.DocumentControl] \(outcome.rawValue)")
    }
}
