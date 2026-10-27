// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "LoKeyAdaptiveController",
    products: [
        .library(name: "LoKeyAdaptiveCore", targets: ["LoKeyAdaptiveCore"]),
        .executable(name: "lokey-adaptive-replay", targets: ["LoKeyAdaptiveReplay"])
    ],
    targets: [
        .target(name: "LoKeyAdaptiveCore"),
        .executableTarget(name: "LoKeyAdaptiveReplay", dependencies: ["LoKeyAdaptiveCore"]),
        .testTarget(name: "LoKeyAdaptiveCoreTests", dependencies: ["LoKeyAdaptiveCore"])
    ]
)
