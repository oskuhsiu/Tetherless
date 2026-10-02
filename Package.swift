// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "TetherlessCore",
    platforms: [.iOS(.v17), .macOS(.v13)],
    products: [.library(name: "TetherlessCore", targets: ["TetherlessCore"])],
    targets: [
        .target(name: "TetherlessCore"),
        .testTarget(name: "TetherlessCoreTests", dependencies: ["TetherlessCore"])
    ]
)
