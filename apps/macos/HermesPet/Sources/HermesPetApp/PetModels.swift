import Foundation

enum UniversalPetLimits {
    static let maxPets = 4
}

enum PetConnectorKind: String, Codable, CaseIterable, Identifiable {
    case hermes
    case openClaw = "openclaw"
    case codex
    case kimi
    case claudeCode = "claude-code"
    case opencode
    case custom

    var id: String { rawValue }
}

enum PetAgentMode: String, Codable, CaseIterable {
    case cli
    case tui
    case chat
    case custom
}

enum PetTransportKind: String, Codable, CaseIterable {
    case local
    case ssh
    case telegram
    case relay
}

struct PetPlacement: Codable, Hashable {
    var x: Double
    var y: Double
    var size: Double

    static func defaultPlacement(index: Int) -> PetPlacement {
        PetPlacement(
            x: 160 + Double(index * 26),
            y: 160 + Double(index * 26),
            size: 96
        )
    }
}

struct PetArtworkRef: Codable, Hashable {
    var assetID: String
    var displayName: String
    var assetDirectory: String?

    static let bundledHermes = PetArtworkRef(
        assetID: "bundled-hermes",
        displayName: "Bundled Hermes",
        assetDirectory: nil
    )
}

struct PetAgentBinding: Codable, Hashable {
    var connector: PetConnectorKind
    var mode: PetAgentMode
    var transport: PetTransportKind
    var sessionID: String?
    var displayName: String
    var command: String?
    var sshTarget: String?
    var telegramChatID: String?
    var relayURL: String?

    static let disconnected = PetAgentBinding(
        connector: .custom,
        mode: .custom,
        transport: .local,
        sessionID: nil,
        displayName: "Disconnected",
        command: nil,
        sshTarget: nil,
        telegramChatID: nil,
        relayURL: nil
    )

    static func hermesLocal(mode: PetAgentMode, sessionID: String? = nil) -> PetAgentBinding {
        PetAgentBinding(
            connector: .hermes,
            mode: mode,
            transport: .local,
            sessionID: sessionID,
            displayName: mode == .tui ? "Hermes TUI" : "Hermes CLI",
            command: nil,
            sshTarget: nil,
            telegramChatID: nil,
            relayURL: nil
        )
    }
}

struct PetSlot: Codable, Identifiable, Hashable {
    var id: UUID
    var name: String
    var enabled: Bool
    var placement: PetPlacement
    var artwork: PetArtworkRef
    var binding: PetAgentBinding

    static func defaultHermes(index: Int = 0) -> PetSlot {
        PetSlot(
            id: UUID(),
            name: "Hermes Pet",
            enabled: true,
            placement: .defaultPlacement(index: index),
            artwork: .bundledHermes,
            binding: .hermesLocal(mode: .cli)
        )
    }
}

struct PetAppConfiguration: Codable, Hashable {
    var slots: [PetSlot]
    var enabledSlots: [PetSlot] {
        Array(slots.filter { $0.enabled }.prefix(UniversalPetLimits.maxPets))
    }

    init(slots: [PetSlot]) {
        self.slots = Array(slots.prefix(UniversalPetLimits.maxPets))
    }

    mutating func replaceSlots(_ newSlots: [PetSlot]) {
        slots = Array(newSlots.prefix(UniversalPetLimits.maxPets))
    }

    static let defaultConfiguration = PetAppConfiguration(slots: [
        .defaultHermes(index: 0),
    ])
}
