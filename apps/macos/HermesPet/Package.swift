// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "HermesPet",
    platforms: [
        .macOS(.v13),
    ],
    products: [
        .executable(name: "HermesPetApp", targets: ["HermesPetApp"]),
    ],
    targets: [
        .executableTarget(name: "HermesPetApp"),
    ]
)
