// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "GitHubBar",
    platforms: [.macOS(.v13)],
    targets: [
        .target(name: "GitHubBarCore"),
        .executableTarget(name: "GitHubBar", dependencies: ["GitHubBarCore"]),
        // Command Line Tools ship neither XCTest nor swift-testing, so checks are a plain executable.
        .executableTarget(name: "GitHubBarChecks", dependencies: ["GitHubBarCore"]),
    ]
)
