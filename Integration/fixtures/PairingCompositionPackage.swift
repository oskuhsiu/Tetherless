// swift-tools-version: 6.0
// Synthetic C registration/FFI ownership spies. Never used by the app build.
import PackageDescription
let package = Package(name: "TetherlessCore", platforms: [.macOS(.v13)], targets: [
    .target(name: "IDevice", path: "Sources/IDevice", publicHeadersPath: "include"),
    .target(name: "TetherlessCore", dependencies: ["IDevice"]),
    .testTarget(name: "TetherlessCoreTests", dependencies: ["TetherlessCore", "IDevice"])
])
