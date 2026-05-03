import AppKit

struct PetWireEvent: Codable {
    var `protocol`: String?
    var sourceId: String
    var label: String
    var state: String
    var message: String?
    var animation: String?
    var notificationCount: Int?

    enum CodingKeys: String, CodingKey {
        case `protocol`
        case sourceId = "source_id"
        case label
        case state
        case message
        case animation
        case notificationCount = "notification_count"
    }
}

final class PetView: NSView {
    private let symbol: String

    init(frame frameRect: NSRect, symbol: String) {
        self.symbol = symbol
        super.init(frame: frameRect)
    }

    required init?(coder: NSCoder) {
        self.symbol = "H"
        super.init(coder: coder)
    }

    override var isFlipped: Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)

        let bounds = self.bounds.insetBy(dx: 8, dy: 8)
        NSColor.clear.setFill()
        NSBezierPath(rect: dirtyRect).fill()

        let shadow = NSShadow()
        shadow.shadowOffset = NSSize(width: 0, height: -3)
        shadow.shadowBlurRadius = 8
        shadow.shadowColor = NSColor.black.withAlphaComponent(0.22)
        shadow.set()

        NSColor.white.setFill()
        NSBezierPath(ovalIn: bounds).fill()
        NSColor.black.setStroke()
        let outline = NSBezierPath(ovalIn: bounds)
        outline.lineWidth = 3
        outline.stroke()

        NSColor.black.setFill()
        let leftWing = NSBezierPath()
        leftWing.move(to: NSPoint(x: bounds.minX + 12, y: bounds.midY - 16))
        leftWing.line(to: NSPoint(x: bounds.minX - 7, y: bounds.midY - 7))
        leftWing.line(to: NSPoint(x: bounds.minX + 10, y: bounds.midY + 2))
        leftWing.close()
        leftWing.fill()

        let rightWing = NSBezierPath()
        rightWing.move(to: NSPoint(x: bounds.maxX - 12, y: bounds.midY - 16))
        rightWing.line(to: NSPoint(x: bounds.maxX + 7, y: bounds.midY - 7))
        rightWing.line(to: NSPoint(x: bounds.maxX - 10, y: bounds.midY + 2))
        rightWing.close()
        rightWing.fill()

        let text = symbol as NSString
        let attrs: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 30, weight: .black),
            .foregroundColor: NSColor.black,
        ]
        let size = text.size(withAttributes: attrs)
        text.draw(
            at: NSPoint(x: self.bounds.midX - size.width / 2, y: self.bounds.midY - size.height / 2),
            withAttributes: attrs
        )
    }
}

final class FloatingPetController {
    private let panel: NSPanel

    init(slot: PetSlot, index: Int) {
        precondition(Thread.isMainThread)
        let placement = slot.placement
        panel = NSPanel(
            contentRect: NSRect(
                x: placement.x,
                y: placement.y,
                width: placement.size,
                height: placement.size
            ),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.ignoresMouseEvents = false
        let symbol = String(slot.name.prefix(1)).uppercased()
        panel.contentView = PetView(
            frame: NSRect(x: 0, y: 0, width: placement.size, height: placement.size),
            symbol: symbol.isEmpty ? "\(index + 1)" : symbol
        )
    }

    func show() {
        panel.orderFrontRegardless()
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem?
    private var petControllers: [FloatingPetController] = []
    private var configuration = PetAppConfiguration.defaultConfiguration

    func applicationDidFinishLaunching(_ notification: Notification) {
        precondition(Thread.isMainThread)
        petControllers = configuration.enabledSlots.enumerated().map { index, slot in
            return FloatingPetController(slot: slot, index: index)
        }
        petControllers.forEach { $0.show() }

        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        item.button?.title = "H"
        let menu = NSMenu()
        menu.addItem(withTitle: "Hermes Pet", action: nil, keyEquivalent: "")
        menu.addItem(NSMenuItem.separator())
        let slots = NSMenuItem(
            title: "Pet Slots: \(petControllers.count)/\(UniversalPetLimits.maxPets)",
            action: nil,
            keyEquivalent: ""
        )
        slots.isEnabled = false
        menu.addItem(slots)
        let connector = NSMenuItem(
            title: "Connector: \(configuration.slots.first?.binding.displayName ?? "Disconnected")",
            action: nil,
            keyEquivalent: ""
        )
        connector.isEnabled = false
        menu.addItem(connector)
        menu.addItem(withTitle: "Quit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        item.menu = menu
        statusItem = item
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
