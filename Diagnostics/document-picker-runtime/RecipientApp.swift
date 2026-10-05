// SPDX-License-Identifier: AGPL-3.0-only
// A separate UIKit recipient. Never bundled into the product or document source.
import Foundation
import UIKit
import UniformTypeIdentifiers

@main
@MainActor
final class RuntimeRecipientApp: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        window = UIWindow(frame: UIScreen.main.bounds)
        window?.rootViewController = RuntimeRecipient()
        window?.makeKeyAndVisible()
        return true
    }
}

@MainActor
final class RuntimeRecipient: UIViewController, UIDocumentPickerDelegate {
    private struct Presentation: Codable {
        var outcome = "waiting"
        var callbackCount = 0
        var dismissed = false
    }
    private let openButton = UIButton(type: .system)
    private let outcomeLabel = UILabel()
    private let countsLabel = UILabel()
    private let dismissedLabel = UILabel()
    private let violationLabel = UILabel()
    // Retain each delegate relationship for this short test: late or duplicate
    // callbacks remain visible and cannot silently disappear behind a nil delegate.
    private var pickers: [UIDocumentPickerViewController] = []
    private var records: [Presentation] = []
    private var activePicker: UIDocumentPickerViewController?
    private var protocolViolation = false
    private var evidenceWriteFailed = false

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        openButton.setTitle("Open system document picker", for: .normal)
        openButton.accessibilityIdentifier = "runtime.open"
        openButton.addTarget(self, action: #selector(openPicker), for: .touchUpInside)
        for (label, identifier) in [(outcomeLabel, "runtime.outcome"),
                                    (countsLabel, "runtime.callbackCounts"),
                                    (dismissedLabel, "runtime.dismissed"),
                                    (violationLabel, "runtime.violation")] {
            label.accessibilityIdentifier = identifier
            label.textAlignment = .center
        }
        let stack = UIStackView(arrangedSubviews: [openButton, outcomeLabel, countsLabel,
                                                   dismissedLabel, violationLabel])
        stack.axis = .vertical
        stack.spacing = 12
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: view.centerYAnchor)
        ])
        publish()
    }

    @objc private func openPicker() {
        guard activePicker == nil, presentedViewController == nil, records.count < 3 else {
            protocolViolation = true
            publish()
            return
        }
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: [.propertyList, .xml], asCopy: false)
        picker.allowsMultipleSelection = false
        picker.shouldShowFileExtensions = true
        picker.delegate = self
        picker.modalPresentationStyle = .fullScreen
        pickers.append(picker)
        records.append(Presentation())
        activePicker = picker
        openButton.isEnabled = false
        publish()
        present(picker, animated: true)
    }

    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        // Only callback shape is examined. No selected bytes, parser or product
        // state is accessed, and no URL/path/content is written to diagnostics.
        receive(controller, outcome: urls.count == 1 && urls.first?.isFileURL == true
                ? "selectedFileURL" : "invalidSelection")
    }

    func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        receive(controller, outcome: "cancelled")
    }

    private func receive(_ controller: UIDocumentPickerViewController, outcome: String) {
        guard let index = pickers.firstIndex(where: { $0 === controller }) else {
            protocolViolation = true
            publish()
            return
        }
        records[index].callbackCount += 1
        records[index].outcome = outcome
        guard controller === activePicker, records[index].callbackCount == 1 else {
            protocolViolation = true
            publish()
            return
        }
        publish()
        // UIKit can deliver cancellation AFTER it has already dismissed the
        // picker. Observe that real detached state without asking it to dismiss
        // twice or relying on a completion for a no-longer-presented controller.
        if controller.presentingViewController == nil && presentedViewController == nil {
            observeDismissal(controller, index: index)
        } else {
            controller.dismiss(animated: true) { [weak self, weak controller] in
                guard let self, let controller else { return }
                self.observeDismissal(controller, index: index)
            }
        }
    }

    private func observeDismissal(_ controller: UIDocumentPickerViewController, index: Int) {
        records[index].dismissed = presentedViewController == nil && controller.presentingViewController == nil
        if records[index].dismissed {
            activePicker = nil
            openButton.isEnabled = true
        }
        publish()
    }

    private func publish() {
        outcomeLabel.text = records.last?.outcome ?? "idle"
        countsLabel.text = records.map { String($0.callbackCount) }.joined(separator: ",")
        dismissedLabel.text = records.last?.dismissed == true ? "true" : "false"
        violationLabel.text = protocolViolation || evidenceWriteFailed ? "true" : "false"
        NSLog("[Tetherless.RuntimeRecipient] presentations=%d callbacks=%@ outcome=%@ dismissed=%@ violation=%@ productAccepted=false",
              records.count, countsLabel.text!, outcomeLabel.text!, dismissedLabel.text!, violationLabel.text!)
        struct Observation: Encodable {
            let schema = 1
            let productAccepted = false
            let selectedBytesRead = false
            let presentations: [Presentation]
            let protocolViolation: Bool
            let evidenceWriteFailed: Bool
        }
        do {
            // Private observations only. The recipient never publishes its
            // Documents directory and never creates the source fixture.
            let cache = try FileManager.default.url(for: .cachesDirectory, in: .userDomainMask,
                                                     appropriateFor: nil, create: true)
            let data = try JSONEncoder().encode(Observation(presentations: records,
                    protocolViolation: protocolViolation, evidenceWriteFailed: evidenceWriteFailed))
            try data.write(to: cache.appendingPathComponent("RuntimeObservation.json"), options: .atomic)
        } catch {
            evidenceWriteFailed = true
            violationLabel.text = "true"
            NSLog("[Tetherless.RuntimeRecipient] observationWriteFailed productAccepted=false")
        }
    }
}
