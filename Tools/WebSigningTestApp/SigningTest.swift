import UIKit

// Owned, dependency-free test fixture. This is not the Tetherless application.
@main
final class SigningTestAppDelegate: UIResponder, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        configurationForConnecting connectingSceneSession: UISceneSession,
        options: UIScene.ConnectionOptions
    ) -> UISceneConfiguration {
        let configuration = UISceneConfiguration(name: "Signing test", sessionRole: connectingSceneSession.role)
        configuration.sceneClass = UIWindowScene.self
        configuration.delegateClass = SigningTestSceneDelegate.self
        return configuration
    }
}

final class SigningTestSceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options: UIScene.ConnectionOptions) {
        guard let windowScene = scene as? UIWindowScene else { return }
        let window = UIWindow(windowScene: windowScene)
        window.rootViewController = SigningTestViewController()
        self.window = window
        window.makeKeyAndVisible()
    }
}

final class SigningTestViewController: UIViewController {
    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        let stack = UIStackView()
        stack.axis = .vertical
        stack.spacing = 20
        stack.translatesAutoresizingMaskIntoConstraints = false

        addLabel("Signing test app, not Tetherless", style: .largeTitle, to: stack)
        addLabel("This small owned app is only a fixture for an authorized custom-IPA signing test.", style: .body, to: stack)
        addLabel("It does not test Tetherless, pairing, renewal, background operation, or product readiness.", style: .body, to: stack)
        addLabel("No account login, network requests, credentials, or stored user data.", style: .body, to: stack)

        if let url = Bundle.main.url(forResource: "BuildIdentity", withExtension: "json"),
           let data = try? Data(contentsOf: url),
           let identity = try? JSONSerialization.jsonObject(with: data) as? [String: String],
           let commit = identity["source_commit"], let run = identity["run_id"],
           let attempt = identity["run_attempt"], let bundle = identity["bundle_identifier"] {
            addLabel("Source: \(commit)\nCI run: \(run), attempt \(attempt)\nApp ID: \(bundle)", style: .caption1, to: stack)
        } else {
            addLabel("Build identity unavailable. Do not use this copy for verification.", style: .body, to: stack)
        }

        let scroll = UIScrollView()
        scroll.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(scroll)
        scroll.addSubview(stack)
        NSLayoutConstraint.activate([
            scroll.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor),
            scroll.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            scroll.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor),
            stack.leadingAnchor.constraint(equalTo: scroll.contentLayoutGuide.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: scroll.contentLayoutGuide.trailingAnchor, constant: -24),
            stack.topAnchor.constraint(equalTo: scroll.contentLayoutGuide.topAnchor, constant: 32),
            stack.bottomAnchor.constraint(equalTo: scroll.contentLayoutGuide.bottomAnchor, constant: -32),
            stack.widthAnchor.constraint(equalTo: scroll.frameLayoutGuide.widthAnchor, constant: -48)
        ])
    }

    private func addLabel(_ text: String, style: UIFont.TextStyle, to stack: UIStackView) {
        let label = UILabel()
        label.text = text
        label.font = .preferredFont(forTextStyle: style)
        label.adjustsFontForContentSizeCategory = true
        label.numberOfLines = 0
        stack.addArrangedSubview(label)
    }
}
