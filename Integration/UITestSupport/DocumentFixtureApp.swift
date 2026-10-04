// SPDX-License-Identifier: AGPL-3.0-only
// Simulator-only test document source. Never linked into Tetherless.
import Foundation
import UIKit

@main
@MainActor
final class DocumentFixtureApp: UIResponder, UIApplicationDelegate {
    var window: UIWindow?

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        let label = UILabel()
        label.numberOfLines = 0
        label.textAlignment = .center
        let controller = UIViewController()
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
