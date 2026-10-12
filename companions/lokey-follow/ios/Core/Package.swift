// swift-tools-version: 5.9
import PackageDescription
let package = Package(name: "FollowCore", products: [.library(name: "FollowCore", targets: ["FollowCore"])], targets: [.target(name: "FollowCore"), .testTarget(name: "FollowCoreTests", dependencies: ["FollowCore"])])
