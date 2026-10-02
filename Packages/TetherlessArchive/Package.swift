// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "TetherlessArchive",
    platforms: [.iOS(.v17), .macOS(.v13)],
    products: [.library(name: "TetherlessArchive", targets: ["TetherlessArchive"])],
    dependencies: [.package(url: "https://github.com/weichsel/ZIPFoundation.git", exact: "0.9.20")],
    targets: [
        .target(name: "TetherlessArchive", dependencies: [.product(name: "ZIPFoundation", package: "ZIPFoundation")]),
        .testTarget(name: "TetherlessArchiveTests", dependencies: ["TetherlessArchive", "ZIPFoundation"])
    ]
)
