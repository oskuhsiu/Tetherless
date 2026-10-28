// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "TetherlessCertificateCryptoConsumer",
    platforms: [.macOS(.v15)],
    dependencies: [
        .package(url: "https://github.com/mahee96/CodeSignKit", revision: "d0c67710fda9a2646b9e829cb2cf443892728371"),
        .package(url: "https://github.com/apple/swift-crypto.git", exact: "4.3.1")
    ],
    targets: [.executableTarget(name: "CertificateCryptoConsumer", dependencies: [
        .product(name: "CodeSignKit", package: "CodeSignKit"),
        .product(name: "Crypto", package: "swift-crypto")
    ], path: "Sources/Consumer")]
)
