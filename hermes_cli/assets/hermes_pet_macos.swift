import AppKit
import Foundation

struct PetSnapshot: Decodable {
    let pets: [PetState]
    let sessions: [PetMenuSession]?
    let connected_modes: [String]?
    let preferences: PetPreferences?
    let share: PetShareResponse?
    let asset_version: String?
    let asset_dir: String?
    let artwork: PetArtworkMenu?
    let ui_language: String?
}

struct PetState: Decodable {
    let source_id: String
    let label: String
    let state: String
    let message: String
    let animation: String?
    let direction: String?
    let pet_action: String?
    let emotion: String?
    let asset_id: String?
    let asset_dir: String?
    let asset_version: String?
    let notification_count: Int?
    let notification_kind: String?
    let notification_label: String?
}

struct PetShareResponse: Decodable {
    let request_id: String
    let status: String
    let message: String
    let query: String
    let pets: [PetShareResult]
}

struct PetShareResult: Decodable {
    let id: String
    let display_name: String
    let owner_name: String
    let description: String
    let like_count: Int
    let view_count: Int
    let tags: [String]
    let thumbnail_path: String?
    let share_url: String?
}

struct PetMenuSession: Decodable {
    let mode: String
    let session_id: String
    let label: String
    let cwd: String
    let pid: Int?
    let ppid: Int?
    let active: Bool?
    let tty: String?
    let term_program: String?
    let terminal_app: String?
    let terminal_bundle_id: String?
    let iterm_session_id: String?
    let tmux: String?
}

struct PetPreferences: Decodable {
    let language: String?
    let left_click_opens_terminal: Bool?
    let session_list_limit: Int?
    let terminal_launcher: String?
    let terminal_options: [PetTerminalOption]?
}

struct PetTerminalOption: Decodable {
    let id: String
    let label: String
    let available: Bool?
    let reason: String?
}

struct PetAssetManifest: Decodable {
    let animations: [String: PetAnimationManifest]?
}

struct PetAnimationManifest: Decodable {
    let frames: [String]
    let durationMs: Int?
    let frameDurationsMs: [Int]?
    let loopStartIndex: Int?
}

struct PetImageBundle {
    let images: [String: NSImage]
    let animationFrames: [String: [NSImage]]
    let animationDurations: [String: TimeInterval]
    let animationFrameDurations: [String: [TimeInterval]]
    let animationLoopStartIndexes: [String: Int]
}

struct PetArtworkMenu: Decodable {
    let current: PetArtworkEntry?
    let installed: [PetArtworkEntry]
}

struct PetArtworkEntry: Decodable {
    let asset_id: String?
    let pet_id: String?
    let id: String?
    let display_name: String
    let owner_name: String?
    let source: String?
}

struct AnimationPlayback {
    let key: String
    let startedAt: TimeInterval
}

final class PetOverlayView: NSView {
    private let petSize: CGFloat
    private let slotWidth: CGFloat
    private var assetDir: URL
    private var pets: [PetState]
    private var sessions: [PetMenuSession] = []
    private var images: [String: NSImage] = [:]
    private var animationFrames: [String: [NSImage]] = [:]
    private var animationDurations: [String: TimeInterval] = [:]
    private var animationFrameDurations: [String: [TimeInterval]] = [:]
    private var animationLoopStartIndexes: [String: Int] = [:]
    private var petImageBundles: [String: PetImageBundle] = [:]
    private var animationPlayback: [String: AnimationPlayback] = [:]
    private var assetVersion: String = ""
    private var lastShareRequestID: String = ""
    private var artwork: PetArtworkMenu?
    private var uiLanguage: String = "ko"
    private var connectedModes: Set<String> = []
    private var leftClickOpensTerminal = false
    private var sessionListLimit = 5
    private var terminalLauncher = "macos"
    private let supportedLanguages = ["ko", "en", "ja", "zh"]
    private var terminalOptions: [PetTerminalOption] = [
        PetTerminalOption(id: "macos", label: "macOS Terminal", available: true, reason: nil)
    ]
    private var pendingPetSelectionID: String?
    private var petShareSelectionButtons: [NSButton] = []
    private var dragStartMouse: NSPoint?
    private var dragStartOrigin: NSPoint?
    private var dragLastMouse: NSPoint?
    private var dragExceededClickThreshold = false
    private var dragAnimationKey: String?
    private var hoverAnimationEnabled = false
    private var trackingArea: NSTrackingArea?
    private weak var panel: NSWindow?

    override var isFlipped: Bool { false }
    override var acceptsFirstResponder: Bool { true }

    init(frame: NSRect, petSize: CGFloat, assetDir: URL, initialPets: [PetState]) {
        self.petSize = petSize
        self.slotWidth = petSize + 18
        self.assetDir = assetDir
        self.pets = initialPets
        super.init(frame: frame)
        wantsLayer = true
        layer?.backgroundColor = NSColor.clear.cgColor
        loadImages()
    }

    required init?(coder: NSCoder) {
        nil
    }

    func attach(panel: NSWindow) {
        self.panel = panel
    }

    func setSnapshot(_ snapshot: PetSnapshot) {
        var assetsChanged = false
        if let assetDirPath = snapshot.asset_dir {
            let nextAssetDir = URL(fileURLWithPath: assetDirPath, isDirectory: true)
            if nextAssetDir.path != assetDir.path {
                assetDir = nextAssetDir
                assetsChanged = true
            }
        }
        if let version = snapshot.asset_version, version != assetVersion {
            assetVersion = version
            assetsChanged = true
        }
        if assetsChanged {
            loadImages()
        }
        self.artwork = snapshot.artwork
        if let language = snapshot.ui_language, supportedLanguages.contains(language) {
            self.uiLanguage = language
        }
        if let preferences = snapshot.preferences {
            if let language = preferences.language, supportedLanguages.contains(language) {
                self.uiLanguage = language
            }
            if let opensTerminal = preferences.left_click_opens_terminal {
                self.leftClickOpensTerminal = opensTerminal
            }
            if let limit = preferences.session_list_limit {
                self.sessionListLimit = max(1, min(limit, 50))
            }
            if let launcher = preferences.terminal_launcher, !launcher.isEmpty {
                self.terminalLauncher = launcher
            }
            if let options = preferences.terminal_options, !options.isEmpty {
                self.terminalOptions = options
            }
        }
        self.pets = snapshot.pets
        let activeSourceIDs = Set(snapshot.pets.map { $0.source_id })
        animationPlayback = animationPlayback.filter { activeSourceIDs.contains($0.key) }
        self.sessions = snapshot.sessions ?? []
        self.connectedModes = Set((snapshot.connected_modes ?? []).map { $0.lowercased() })
        resizeWindow()
        needsDisplay = true
        if let share = snapshot.share, share.request_id != lastShareRequestID {
            lastShareRequestID = share.request_id
            showPetShareResponse(share)
        }
    }

    func startAnimation() {
        Timer.scheduledTimer(withTimeInterval: 0.10, repeats: true) { [weak self] _ in
            guard let self else { return }
            if self.dragStartMouse != nil && (NSEvent.pressedMouseButtons & 1) == 0 {
                self.clearDragState()
            }
            self.needsDisplay = true
        }
    }

    private func loadImages() {
        let bundle = loadImageBundle(from: assetDir)
        images = bundle.images
        animationFrames = bundle.animationFrames
        animationDurations = bundle.animationDurations
        animationFrameDurations = bundle.animationFrameDurations
        animationLoopStartIndexes = bundle.animationLoopStartIndexes
        petImageBundles.removeAll()
        animationPlayback.removeAll()
    }

    private func loadImageBundle(from directory: URL) -> PetImageBundle {
        var loadedImages: [String: NSImage] = [:]
        var loadedFrames: [String: [NSImage]] = [:]
        var loadedDurations: [String: TimeInterval] = [:]
        var loadedFrameDurations: [String: [TimeInterval]] = [:]
        var loadedLoopStartIndexes: [String: Int] = [:]
        let files: [String: String] = [
            "idle": "hermes_pet_idle.png",
            "blink": "hermes_pet_blink.png",
            "working": "hermes_pet_working.png",
            "review": "hermes_pet_review.png",
        ]

        for (key, file) in files {
            let base = directory.appendingPathComponent(file)
            let sized = directory.appendingPathComponent(sizedFileName(file))
            let url = FileManager.default.fileExists(atPath: sized.path) ? sized : base
            if let image = NSImage(contentsOf: url) {
                loadedImages[key] = image
            }
        }
        loadAnimations(
            from: directory,
            frames: &loadedFrames,
            durations: &loadedDurations,
            frameDurations: &loadedFrameDurations,
            loopStartIndexes: &loadedLoopStartIndexes
        )
        return PetImageBundle(
            images: loadedImages,
            animationFrames: loadedFrames,
            animationDurations: loadedDurations,
            animationFrameDurations: loadedFrameDurations,
            animationLoopStartIndexes: loadedLoopStartIndexes
        )
    }

    private func sizedFileName(_ file: String) -> String {
        let url = URL(fileURLWithPath: file)
        let stem = url.deletingPathExtension().lastPathComponent
        let ext = url.pathExtension
        return "\(stem)_\(Int(petSize)).\(ext)"
    }

    private func loadAnimations(
        from directory: URL,
        frames loadedFrames: inout [String: [NSImage]],
        durations loadedDurations: inout [String: TimeInterval],
        frameDurations loadedFrameDurations: inout [String: [TimeInterval]],
        loopStartIndexes loadedLoopStartIndexes: inout [String: Int]
    ) {
        let manifestURL = directory.appendingPathComponent("manifest.json")
        guard let data = try? Data(contentsOf: manifestURL),
              let manifest = try? JSONDecoder().decode(PetAssetManifest.self, from: data),
              let animations = manifest.animations
        else {
            return
        }

        for (key, spec) in animations {
            let loaded = spec.frames.compactMap { file -> NSImage? in
                NSImage(contentsOf: directory.appendingPathComponent(file))
            }
            if !loaded.isEmpty {
                loadedFrames[key] = loaded
                loadedDurations[key] = TimeInterval(max(spec.durationMs ?? 1000, 200)) / 1000.0
                if let frameDurationsMs = spec.frameDurationsMs,
                   frameDurationsMs.count == loaded.count {
                    loadedFrameDurations[key] = frameDurationsMs.map {
                        TimeInterval(max($0, 10)) / 1000.0
                    }
                }
                if let loopStartIndex = spec.loopStartIndex,
                   loopStartIndex >= 0,
                   loopStartIndex < loaded.count {
                    loadedLoopStartIndexes[key] = loopStartIndex
                }
            }
        }
    }

    private func resizeWindow() {
        guard let panel else { return }
        let count = max(1, pets.count)
        let width = max(CGFloat(count) * slotWidth + 8, petSize + 26)
        let height = petSize + 30
        var frame = panel.frame
        frame.size = NSSize(width: width, height: height)
        panel.setFrame(frame, display: true)
        self.frame = NSRect(origin: .zero, size: frame.size)
    }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        true
    }

    override func updateTrackingAreas() {
        if let trackingArea {
            removeTrackingArea(trackingArea)
        }
        let nextTrackingArea = NSTrackingArea(
            rect: .zero,
            options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
            owner: self,
            userInfo: nil
        )
        addTrackingArea(nextTrackingArea)
        trackingArea = nextTrackingArea
        super.updateTrackingAreas()
    }

    override func mouseEntered(with event: NSEvent) {
        hoverAnimationEnabled = true
    }

    override func mouseExited(with event: NSEvent) {
        hoverAnimationEnabled = false
    }

    override func mouseDown(with event: NSEvent) {
        dragStartMouse = NSEvent.mouseLocation
        dragStartOrigin = window?.frame.origin
        dragLastMouse = dragStartMouse
        dragExceededClickThreshold = false
        dragAnimationKey = nil
    }

    override func mouseDragged(with event: NSEvent) {
        guard let window, let dragStartMouse, let dragStartOrigin else { return }
        let current = NSEvent.mouseLocation
        let dx = current.x - dragStartMouse.x
        let dy = current.y - dragStartMouse.y
        if abs(dx) > 4.0 || abs(dy) > 4.0 {
            dragExceededClickThreshold = true
        }
        window.setFrameOrigin(NSPoint(x: dragStartOrigin.x + dx, y: dragStartOrigin.y + dy))

        let previous = dragLastMouse ?? dragStartMouse
        let stepX = current.x - previous.x
        let stepY = current.y - previous.y
        if abs(stepX) < 4.0 && abs(stepY) < 4.0 {
            return
        }
        if stepX <= -4.0 {
            dragAnimationKey = "running-left"
        } else if stepX >= 4.0 {
            dragAnimationKey = "running-right"
        }
        dragLastMouse = current
    }

    override func mouseUp(with event: NSEvent) {
        if !dragExceededClickThreshold {
            handlePrimaryClick(with: event)
        }
        clearDragState()
    }

    private func clearDragState() {
        dragStartMouse = nil
        dragStartOrigin = nil
        dragLastMouse = nil
        dragExceededClickThreshold = false
        dragAnimationKey = nil
    }

    private func handlePrimaryClick(with event: NSEvent) {
        if totalNotificationCount() > 0 {
            emitAction("clear_notifications")
        }
        let activeSessions = sessions.filter { $0.active ?? false }
        if activeSessions.count == 1, let session = activeSessions.first {
            emitSessionAction(
                "focus_session",
                sessionID: session.session_id,
                allowResume: leftClickOpensTerminal
            )
        } else if activeSessions.count > 1 {
            showSessionFocusMenu(with: event, sessions: activeSessions)
        } else if leftClickOpensTerminal && !sessions.isEmpty {
            showSessionFocusMenu(with: event, sessions: sessions)
        }
    }

    private func showSessionFocusMenu(with event: NSEvent, sessions menuSessions: [PetMenuSession]) {
        let menu = NSMenu()
        for session in menuSessions.prefix(sessionListLimit) {
            let item = sessionMenuItem(title: sessionTitle(session), action: #selector(focusSession(_:)), session: session)
            item.target = self
            menu.addItem(item)
        }
        NSMenu.popUpContextMenu(menu, with: event, for: self)
    }

    override func rightMouseDown(with event: NSEvent) {
        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "Hermes Pet", action: nil, keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator())
        addLaunchMenu(to: menu)
        addSessionsMenu(to: menu)
        menu.addItem(NSMenuItem.separator())
        addArtworkMenu(to: menu)
        menu.addItem(NSMenuItem.separator())
        addMenuItem(menu, title: tr("settings"), action: #selector(promptSettings))
        addRuntimeMenu(to: menu)
        menu.addItem(NSMenuItem.separator())
        addNotificationMenuItem(to: menu)
        if pets.count > 1 {
            addMenuItem(menu, title: tr("clearExtraPets"), action: #selector(clearRemotePets))
        }
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: tr("quit"), action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        NSMenu.popUpContextMenu(menu, with: event, for: self)
    }

    private func addMenuItem(_ menu: NSMenu, title: String, action: Selector) {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
        item.target = self
        menu.addItem(item)
    }

    private func addLaunchMenuItem(_ menu: NSMenu, title: String, mode: String, action: Selector) {
        let connected = connectedModes.contains(mode)
        let item = NSMenuItem(title: connected ? "● \(title)" : title, action: action, keyEquivalent: "")
        item.target = self
        if connected {
            let label = NSMutableAttributedString(
                string: "● ",
                attributes: [.foregroundColor: NSColor.systemGreen]
            )
            label.append(NSAttributedString(
                string: title,
                attributes: [.foregroundColor: NSColor.labelColor]
            ))
            item.attributedTitle = label
        }
        menu.addItem(item)
    }

    private func sessionMenuItem(title: String, action: Selector?, session: PetMenuSession) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
        item.target = self
        item.representedObject = session.session_id
        if session.active ?? false {
            let label = NSMutableAttributedString(
                string: "● ",
                attributes: [.foregroundColor: NSColor.systemGreen]
            )
            label.append(NSAttributedString(
                string: title,
                attributes: [.foregroundColor: NSColor.labelColor]
            ))
            item.attributedTitle = label
        }
        return item
    }

    private func tr(_ key: String) -> String {
        let language = supportedLanguages.contains(uiLanguage) ? uiLanguage : "en"
        let table: [String: [String: String]] = [
            "operationMode": [
                "ko": "Hermes 작동 방식",
                "en": "Hermes Mode",
                "ja": "Hermes 動作モード",
                "zh": "Hermes 运行模式",
            ],
            "petArtwork": ["ko": "펫 아트워크", "en": "Pet Artwork", "ja": "ペットアート", "zh": "宠物图像"],
            "current": ["ko": "현재", "en": "Current", "ja": "現在", "zh": "当前"],
            "searchPetShare": ["ko": "Codex Pet Share 검색...", "en": "Search Codex Pet Share...", "ja": "Codex Pet Share を検索...", "zh": "搜索 Codex Pet Share..."],
            "openPetShare": ["ko": "Codex Pet Share 사이트 열기", "en": "Open Codex Pet Share Site", "ja": "Codex Pet Share サイトを開く", "zh": "打开 Codex Pet Share 网站"],
            "newestPets": ["ko": "최신 공유 펫", "en": "Newest Shared Pets", "ja": "最新の共有ペット", "zh": "最新共享宠物"],
            "popularPets": ["ko": "인기 공유 펫", "en": "Popular Shared Pets", "ja": "人気の共有ペット", "zh": "热门共享宠物"],
            "viewedPets": ["ko": "조회수 높은 공유 펫", "en": "Most Viewed Shared Pets", "ja": "閲覧数の多い共有ペット", "zh": "最多浏览宠物"],
            "recentPets": ["ko": "최근 펫", "en": "Recent Pets", "ja": "最近のペット", "zh": "最近宠物"],
            "bundledArtwork": ["ko": "기본 Hermes 아트워크 사용", "en": "Use Bundled Hermes Artwork", "ja": "標準 Hermes アートを使う", "zh": "使用内置 Hermes 图像"],
            "activeSessions": ["ko": "활성 세션", "en": "Active Sessions", "ja": "アクティブセッション", "zh": "活动会话"],
            "noActiveSessions": ["ko": "활성 Hermes 세션 없음", "en": "No Active Hermes Sessions", "ja": "アクティブな Hermes セッションはありません", "zh": "没有活动 Hermes 会话"],
            "focusSession": ["ko": "열려있는 탭 앞으로 가져오기", "en": "Focus Existing Tab", "ja": "開いているタブを前面へ", "zh": "聚焦已打开标签"],
            "openCLI": ["ko": "CLI 새 탭에서 열기", "en": "Open in CLI Tab", "ja": "CLI タブで開く", "zh": "在 CLI 标签打开"],
            "openTUI": ["ko": "TUI 새 탭에서 열기", "en": "Open in TUI Tab", "ja": "TUI タブで開く", "zh": "在 TUI 标签打开"],
            "language": ["ko": "언어", "en": "Language", "ja": "言語", "zh": "语言"],
            "korean": ["ko": "한국어", "en": "Korean", "ja": "韓国語", "zh": "韩语"],
            "english": ["ko": "영어", "en": "English", "ja": "英語", "zh": "英语"],
            "japanese": ["ko": "일본어", "en": "Japanese", "ja": "日本語", "zh": "日语"],
            "chinese": ["ko": "중국어", "en": "Chinese", "ja": "中国語", "zh": "中文"],
            "settings": ["ko": "설정...", "en": "Settings...", "ja": "設定...", "zh": "设置..."],
            "settingsTitle": ["ko": "Hermes Pet 설정", "en": "Hermes Pet Settings", "ja": "Hermes Pet 設定", "zh": "Hermes Pet 设置"],
            "settingsSubtitle": ["ko": "로컬 펫 동작과 세션 메뉴를 조정합니다.", "en": "Tune local pet behavior and session menus.", "ja": "ローカルペットの動作とセッションメニューを調整します。", "zh": "调整本地宠物行为和会话菜单。"],
            "petRuntime": ["ko": "펫 실행 관리", "en": "Pet Runtime", "ja": "ペット実行管理", "zh": "宠物运行管理"],
            "restartPet": ["ko": "Hermes Pet 재시작", "en": "Restart Hermes Pet", "ja": "Hermes Pet を再起動", "zh": "重启 Hermes Pet"],
            "loginItemStatus": ["ko": "로그인 실행 상태 확인", "en": "Check Login Item Status", "ja": "ログイン項目の状態を確認", "zh": "检查登录项状态"],
            "installLoginItem": ["ko": "로그인 시 자동 실행 설치", "en": "Install Login Item", "ja": "ログイン時に自動起動をインストール", "zh": "安装登录时自动启动"],
            "startLoginItem": ["ko": "로그인 실행 시작", "en": "Start Login Item", "ja": "ログイン項目を開始", "zh": "启动登录项"],
            "stopLoginItem": ["ko": "로그인 실행 중지", "en": "Stop Login Item", "ja": "ログイン項目を停止", "zh": "停止登录项"],
            "leftClickTerminal": ["ko": "좌클릭 시 선택 터미널 열기", "en": "Open selected terminal on left-click", "ja": "左クリックで選択したターミナルを開く", "zh": "左键点击时打开所选终端"],
            "terminalLauncher": ["ko": "터미널", "en": "Terminal", "ja": "ターミナル", "zh": "终端"],
            "sessionListLimit": ["ko": "세션 목록 개수", "en": "Session list count", "ja": "セッション表示数", "zh": "会话列表数量"],
            "save": ["ko": "저장", "en": "Save", "ja": "保存", "zh": "保存"],
            "clearNotifications": ["ko": "알림 지우기", "en": "Clear Notifications", "ja": "通知を消去", "zh": "清除通知"],
            "clearExtraPets": ["ko": "추가 펫 지우기", "en": "Clear Extra Pets", "ja": "追加ペットを消去", "zh": "清除额外宠物"],
            "quit": ["ko": "Hermes Pet 종료", "en": "Quit Hermes Pet", "ja": "Hermes Pet を終了", "zh": "退出 Hermes Pet"],
            "cancel": ["ko": "취소", "en": "Cancel", "ja": "キャンセル", "zh": "取消"],
            "searchPetShareTitle": ["ko": "Codex Pet Share 검색", "en": "Search Codex Pet Share", "ja": "Codex Pet Share 検索", "zh": "搜索 Codex Pet Share"],
            "searchPetShareInfo": ["ko": "검색어를 입력하세요. 비워두면 최신 펫을 보여줍니다.", "en": "Enter a search term, or leave it blank for newest pets.", "ja": "検索語を入力します。空欄なら最新ペットを表示します。", "zh": "输入搜索词，留空则显示最新宠物。"],
            "search": ["ko": "검색", "en": "Search", "ja": "検索", "zh": "搜索"],
            "noPetsFound": ["ko": "펫을 찾지 못했습니다", "en": "No Pets Found", "ja": "ペットが見つかりません", "zh": "未找到宠物"],
            "noNewestPets": ["ko": "최신 공유 펫이 아직 없습니다.", "en": "No newest pets were returned.", "ja": "最新の共有ペットはまだありません。", "zh": "还没有最新共享宠物。"],
            "noSearchResults": ["ko": "검색 결과 없음:", "en": "No results for:", "ja": "検索結果なし:", "zh": "没有搜索结果:"],
            "searchAgain": ["ko": "다시 검색", "en": "Search Again", "ja": "再検索", "zh": "重新搜索"],
            "changePet": ["ko": "Hermes Pet 변경", "en": "Change Hermes Pet", "ja": "Hermes Pet を変更", "zh": "更换 Hermes Pet"],
            "chooseApply": ["ko": "적용할 펫을 선택하세요.", "en": "Choose one to apply.", "ja": "適用するペットを選んでください。", "zh": "选择一个要应用的宠物。"],
            "apply": ["ko": "적용", "en": "Apply", "ja": "適用", "zh": "应用"],
            "ok": ["ko": "확인", "en": "OK", "ja": "OK", "zh": "确定"],
        ]
        return table[key]?[language] ?? table[key]?["en"] ?? key
    }

    private func languageOptions() -> [(code: String, title: String)] {
        [
            ("ko", tr("korean")),
            ("en", tr("english")),
            ("ja", tr("japanese")),
            ("zh", tr("chinese")),
        ]
    }

    private func addLaunchMenu(to menu: NSMenu) {
        let root = NSMenuItem(title: tr("operationMode"), action: nil, keyEquivalent: "")
        let submenu = NSMenu()
        addLaunchMenuItem(submenu, title: "CLI", mode: "cli", action: #selector(launchCLI))
        addLaunchMenuItem(submenu, title: "TUI", mode: "tui", action: #selector(launchTUI))
        menu.setSubmenu(submenu, for: root)
        menu.addItem(root)
    }

    private func addArtworkMenu(to menu: NSMenu) {
        let root = NSMenuItem(title: tr("petArtwork"), action: nil, keyEquivalent: "")
        let submenu = NSMenu()
        if let current = artwork?.current {
            let currentItem = NSMenuItem(title: "\(tr("current")): \(current.display_name)", action: nil, keyEquivalent: "")
            currentItem.isEnabled = false
            submenu.addItem(currentItem)
            submenu.addItem(NSMenuItem.separator())
        }
        let change = NSMenuItem(title: tr("searchPetShare"), action: #selector(promptPetSearch), keyEquivalent: "")
        change.target = self
        submenu.addItem(change)
        let site = NSMenuItem(title: tr("openPetShare"), action: #selector(openPetShareSite), keyEquivalent: "")
        site.target = self
        submenu.addItem(site)
        addMenuItem(submenu, title: tr("newestPets"), action: #selector(listNewestPets))
        addMenuItem(submenu, title: tr("popularPets"), action: #selector(listPopularPets))
        addMenuItem(submenu, title: tr("viewedPets"), action: #selector(listViewedPets))
        addRecentArtworkMenu(to: submenu)
        submenu.addItem(NSMenuItem.separator())
        let clear = NSMenuItem(title: tr("bundledArtwork"), action: #selector(clearPetArtwork), keyEquivalent: "")
        clear.target = self
        submenu.addItem(clear)
        menu.setSubmenu(submenu, for: root)
        menu.addItem(root)
    }

    private func addRecentArtworkMenu(to menu: NSMenu) {
        let installed = artwork?.installed ?? []
        if installed.isEmpty {
            return
        }
        let root = NSMenuItem(title: tr("recentPets"), action: nil, keyEquivalent: "")
        let submenu = NSMenu()
        for entry in installed.prefix(8) {
            guard let assetID = entry.asset_id else { continue }
            let owner = (entry.owner_name ?? "").isEmpty ? "" : " · \(entry.owner_name!)"
            let item = NSMenuItem(title: "\(entry.display_name)\(owner)", action: #selector(applyInstalledPetArtwork(_:)), keyEquivalent: "")
            item.target = self
            item.representedObject = assetID
            submenu.addItem(item)
        }
        menu.setSubmenu(submenu, for: root)
        menu.addItem(root)
    }

    private func addSessionsMenu(to menu: NSMenu) {
        menu.addItem(NSMenuItem.separator())
        if sessions.isEmpty {
            let item = NSMenuItem(title: tr("noActiveSessions"), action: nil, keyEquivalent: "")
            item.isEnabled = false
            menu.addItem(item)
            return
        }

        let root = NSMenuItem(title: tr("activeSessions"), action: nil, keyEquivalent: "")
        let submenu = NSMenu()
        for session in sessions.prefix(sessionListLimit) {
            let sessionItem = sessionMenuItem(title: sessionTitle(session), action: nil, session: session)
            let actions = NSMenu()
            if session.active ?? false {
                let focus = NSMenuItem(title: tr("focusSession"), action: #selector(focusSession(_:)), keyEquivalent: "")
                focus.target = self
                focus.representedObject = session.session_id
                actions.addItem(focus)
                actions.addItem(NSMenuItem.separator())
            }
            let cli = NSMenuItem(title: tr("openCLI"), action: #selector(openSessionCLI(_:)), keyEquivalent: "")
            cli.target = self
            cli.representedObject = session.session_id
            actions.addItem(cli)
            let tui = NSMenuItem(title: tr("openTUI"), action: #selector(openSessionTUI(_:)), keyEquivalent: "")
            tui.target = self
            tui.representedObject = session.session_id
            actions.addItem(tui)
            submenu.setSubmenu(actions, for: sessionItem)
            submenu.addItem(sessionItem)
        }
        menu.setSubmenu(submenu, for: root)
        menu.addItem(root)
    }

    private func addRuntimeMenu(to menu: NSMenu) {
        let root = NSMenuItem(title: tr("petRuntime"), action: nil, keyEquivalent: "")
        let submenu = NSMenu()
        addMenuItem(submenu, title: tr("restartPet"), action: #selector(restartPet))
        submenu.addItem(NSMenuItem.separator())
        addMenuItem(submenu, title: tr("loginItemStatus"), action: #selector(checkLaunchAgentStatus))
        addMenuItem(submenu, title: tr("installLoginItem"), action: #selector(installLaunchAgent))
        addMenuItem(submenu, title: tr("startLoginItem"), action: #selector(startLaunchAgent))
        addMenuItem(submenu, title: tr("stopLoginItem"), action: #selector(stopLaunchAgent))
        menu.setSubmenu(submenu, for: root)
        menu.addItem(root)
    }

    private func addLanguageMenu(to menu: NSMenu) {
        let root = NSMenuItem(title: tr("language"), action: nil, keyEquivalent: "")
        let submenu = NSMenu()
        for option in languageOptions() {
            let item = NSMenuItem(title: option.title, action: #selector(setLanguageFromMenu(_:)), keyEquivalent: "")
            item.target = self
            item.representedObject = option.code
            item.state = uiLanguage == option.code ? .on : .off
            submenu.addItem(item)
        }
        menu.setSubmenu(submenu, for: root)
        menu.addItem(root)
    }

    private func addNotificationMenuItem(to menu: NSMenu) {
        let count = totalNotificationCount()
        if count <= 0 {
            return
        }
        let title = count > 1 ? "\(tr("clearNotifications")) (\(min(count, 99)))" : tr("clearNotifications")
        addMenuItem(menu, title: title, action: #selector(clearNotifications))
    }

    private func totalNotificationCount() -> Int {
        pets.reduce(0) { total, pet in
            total + max(pet.notification_count ?? 0, 0)
        }
    }

    private func sessionTitle(_ session: PetMenuSession) -> String {
        let mode = session.mode.uppercased()
        let name = sessionDisplayName(session)
        return "[\(mode)] \(name)"
    }

    private func sessionDisplayName(_ session: PetMenuSession) -> String {
        let label = session.label.trimmingCharacters(in: .whitespacesAndNewlines)
        if !label.isEmpty {
            return label
        }
        let tail = String(session.session_id.suffix(12))
        let cwdName = URL(fileURLWithPath: session.cwd).lastPathComponent
        if cwdName.isEmpty {
            return tail
        }
        return "\(tail) · \(cwdName)"
    }

    @objc private func launchCLI() {
        emitAction("launch_cli")
    }

    @objc private func launchTUI() {
        emitAction("launch_tui")
    }

    @objc private func promptLaunchSSH() {
        NSApp.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        alert.messageText = tr("launchSSHTitle")
        alert.informativeText = tr("launchSSHInfo")
        alert.alertStyle = .informational
        let input = NSTextField(frame: NSRect(x: 0, y: 0, width: 320, height: 24))
        input.placeholderString = "user@host"
        alert.accessoryView = input
        alert.addButton(withTitle: tr("openSSH"))
        alert.addButton(withTitle: tr("cancel"))
        if alert.runModal() == .alertFirstButtonReturn {
            emitJSONAction([
                "action": "launch_ssh",
                "target": input.stringValue,
            ])
        }
    }

    @objc private func launchTelegramRelay() {
        emitAction("launch_telegram")
    }

    @objc private func setLanguageFromMenu(_ sender: NSMenuItem) {
        guard let language = sender.representedObject as? String,
              supportedLanguages.contains(language)
        else {
            return
        }
        uiLanguage = language
        emitJSONAction([
            "action": "set_language",
            "language": language,
        ])
    }

    @objc private func clearRemotePets() {
        emitAction("clear_remotes")
    }

    @objc private func clearNotifications() {
        emitAction("clear_notifications")
    }

    @objc private func restartPet() {
        emitAction("restart_pet")
    }

    @objc private func checkLaunchAgentStatus() {
        emitAction("launch_agent_status")
    }

    @objc private func installLaunchAgent() {
        emitAction("install_launch_agent")
    }

    @objc private func startLaunchAgent() {
        emitAction("start_launch_agent")
    }

    @objc private func stopLaunchAgent() {
        emitAction("stop_launch_agent")
    }

    private func neoColor(_ hex: UInt32, alpha: CGFloat = 1.0) -> NSColor {
        let red = CGFloat((hex >> 16) & 0xff) / 255.0
        let green = CGFloat((hex >> 8) & 0xff) / 255.0
        let blue = CGFloat(hex & 0xff) / 255.0
        return NSColor(calibratedRed: red, green: green, blue: blue, alpha: alpha)
    }

    private func configureNeoAlert(_ alert: NSAlert) {
        alert.alertStyle = .informational
        alert.icon = NSImage(size: NSSize(width: 1, height: 1))
        alert.messageText = " "
        alert.informativeText = ""
    }

    private func makeNeoLabel(
        _ text: String,
        frame: NSRect,
        size: CGFloat = 12,
        weight: NSFont.Weight = .semibold
    ) -> NSTextField {
        let label = NSTextField(labelWithString: text)
        label.frame = frame
        label.font = NSFont.systemFont(ofSize: size, weight: weight)
        label.textColor = neoColor(0x111111)
        label.backgroundColor = .clear
        label.isSelectable = false
        return label
    }

    private func makeNeoPanel(
        width: CGFloat,
        height: CGFloat,
        title: String,
        subtitle: String? = nil,
        accent: NSColor = NSColor.systemYellow
    ) -> (container: NSView, card: NSView) {
        let container = NSView(frame: NSRect(x: 0, y: 0, width: width, height: height))
        let cardWidth = width - 8
        let cardHeight = height - 8

        let shadow = NSView(frame: NSRect(x: 8, y: 0, width: cardWidth, height: cardHeight))
        shadow.wantsLayer = true
        shadow.layer?.backgroundColor = NSColor.black.cgColor
        container.addSubview(shadow)

        let card = NSView(frame: NSRect(x: 0, y: 8, width: cardWidth, height: cardHeight))
        card.wantsLayer = true
        card.layer?.backgroundColor = neoColor(0xfff4d8).cgColor
        card.layer?.borderColor = NSColor.black.cgColor
        card.layer?.borderWidth = 3
        card.layer?.cornerRadius = 0
        container.addSubview(card)

        let stripe = NSView(frame: NSRect(x: 0, y: cardHeight - 12, width: cardWidth, height: 12))
        stripe.wantsLayer = true
        stripe.layer?.backgroundColor = accent.cgColor
        card.addSubview(stripe)

        let titleLabel = makeNeoLabel(
            title,
            frame: NSRect(x: 18, y: cardHeight - 42, width: cardWidth - 36, height: 24),
            size: 18,
            weight: .heavy
        )
        titleLabel.lineBreakMode = .byTruncatingTail
        card.addSubview(titleLabel)

        if let subtitle, !subtitle.isEmpty {
            let subtitleLabel = makeNeoLabel(
                subtitle,
                frame: NSRect(x: 18, y: cardHeight - 76, width: cardWidth - 36, height: 34),
                size: 12,
                weight: .medium
            )
            subtitleLabel.maximumNumberOfLines = 2
            subtitleLabel.lineBreakMode = .byWordWrapping
            card.addSubview(subtitleLabel)
        }

        return (container, card)
    }

    private func styleNeoTextField(_ field: NSTextField) {
        field.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
        field.isBezeled = true
        field.bezelStyle = .squareBezel
        field.wantsLayer = true
        field.layer?.backgroundColor = NSColor.white.cgColor
        field.layer?.borderColor = NSColor.black.cgColor
        field.layer?.borderWidth = 2
        field.layer?.cornerRadius = 0
    }

    private func styleNeoPopup(_ popup: NSPopUpButton) {
        popup.bezelStyle = .regularSquare
        popup.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
        popup.wantsLayer = true
        popup.layer?.backgroundColor = NSColor.white.cgColor
        popup.layer?.borderColor = NSColor.black.cgColor
        popup.layer?.borderWidth = 2
        popup.layer?.cornerRadius = 0
    }

    private func styleNeoPetButton(_ button: NSButton) {
        button.bezelStyle = .regularSquare
        button.wantsLayer = true
        button.layer?.backgroundColor = (button.state == .on ? neoColor(0xb9ff66) : NSColor.white).cgColor
        button.layer?.borderColor = NSColor.black.cgColor
        button.layer?.borderWidth = button.state == .on ? 3 : 2
        button.layer?.cornerRadius = 0
    }

    private func updatePetShareButtonStyles() {
        for button in petShareSelectionButtons {
            styleNeoPetButton(button)
        }
    }

    private func makeNeoMessageView(title: String, message: String) -> NSView {
        let panel = makeNeoPanel(
            width: 430,
            height: 162,
            title: title,
            subtitle: nil,
            accent: neoColor(0xff6b6b)
        )
        let messageLabel = makeNeoLabel(
            message,
            frame: NSRect(x: 18, y: 20, width: 386, height: 82),
            size: 13,
            weight: .medium
        )
        messageLabel.maximumNumberOfLines = 5
        messageLabel.lineBreakMode = .byWordWrapping
        panel.card.addSubview(messageLabel)
        return panel.container
    }

    @objc private func promptSettings() {
        NSApp.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        configureNeoAlert(alert)

        let panel = makeNeoPanel(
            width: 444,
            height: 238,
            title: tr("settingsTitle"),
            subtitle: tr("settingsSubtitle"),
            accent: neoColor(0x8be9fd)
        )
        let view = panel.container
        let card = panel.card
        let languageLabel = NSTextField(labelWithString: tr("language"))
        languageLabel.frame = NSRect(x: 18, y: 138, width: 130, height: 20)
        languageLabel.font = NSFont.systemFont(ofSize: 12, weight: .bold)
        card.addSubview(languageLabel)

        let languagePopup = NSPopUpButton(frame: NSRect(x: 184, y: 134, width: 220, height: 28))
        let languages = languageOptions()
        var selectedLanguageIndex = 0
        for option in languages {
            languagePopup.addItem(withTitle: option.title)
            languagePopup.lastItem?.representedObject = option.code
            if option.code == uiLanguage {
                selectedLanguageIndex = max(languagePopup.numberOfItems - 1, 0)
            }
        }
        languagePopup.selectItem(at: selectedLanguageIndex)
        styleNeoPopup(languagePopup)
        card.addSubview(languagePopup)

        let terminalLabel = NSTextField(labelWithString: tr("terminalLauncher"))
        terminalLabel.frame = NSRect(x: 18, y: 100, width: 130, height: 20)
        terminalLabel.font = NSFont.systemFont(ofSize: 12, weight: .bold)
        card.addSubview(terminalLabel)

        let terminalPopup = NSPopUpButton(frame: NSRect(x: 184, y: 96, width: 220, height: 28))
        var selectedTerminalIndex = 0
        for option in terminalOptions {
            let available = option.available ?? false
            let unavailableReason = option.reason ?? "not installed"
            let title = available ? option.label : "\(option.label) (\(unavailableReason))"
            terminalPopup.addItem(withTitle: title)
            if option.id == terminalLauncher {
                selectedTerminalIndex = max(terminalPopup.numberOfItems - 1, 0)
            }
            terminalPopup.lastItem?.representedObject = option.id
            terminalPopup.lastItem?.isEnabled = available || option.id == terminalLauncher
        }
        if terminalPopup.numberOfItems == 0 {
            terminalPopup.addItem(withTitle: "macOS Terminal")
            terminalPopup.lastItem?.representedObject = "macos"
        }
        terminalPopup.selectItem(at: min(selectedTerminalIndex, max(terminalPopup.numberOfItems - 1, 0)))
        styleNeoPopup(terminalPopup)
        card.addSubview(terminalPopup)

        let clickCheckbox = NSButton(checkboxWithTitle: tr("leftClickTerminal"), target: nil, action: nil)
        clickCheckbox.frame = NSRect(x: 18, y: 58, width: 386, height: 24)
        clickCheckbox.font = NSFont.systemFont(ofSize: 12, weight: .semibold)
        clickCheckbox.state = leftClickOpensTerminal ? .on : .off
        card.addSubview(clickCheckbox)

        let countLabel = NSTextField(labelWithString: tr("sessionListLimit"))
        countLabel.frame = NSRect(x: 18, y: 22, width: 150, height: 20)
        countLabel.font = NSFont.systemFont(ofSize: 12, weight: .bold)
        card.addSubview(countLabel)

        let countField = NSTextField(frame: NSRect(x: 184, y: 18, width: 64, height: 26))
        countField.stringValue = "\(sessionListLimit)"
        countField.alignment = .right
        styleNeoTextField(countField)
        card.addSubview(countField)

        alert.accessoryView = view
        alert.addButton(withTitle: tr("save"))
        alert.addButton(withTitle: tr("cancel"))
        if alert.runModal() == .alertFirstButtonReturn {
            let language = languagePopup.selectedItem?.representedObject as? String ?? "ko"
            let launcher = terminalPopup.selectedItem?.representedObject as? String ?? terminalLauncher
            let requestedLimit = Int(countField.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)) ?? sessionListLimit
            let cleanLimit = max(1, min(requestedLimit, 50))
            uiLanguage = language
            leftClickOpensTerminal = clickCheckbox.state == .on
            sessionListLimit = cleanLimit
            terminalLauncher = launcher
            emitJSONAction([
                "action": "set_preferences",
                "language": language,
                "left_click_opens_terminal": leftClickOpensTerminal ? "true" : "false",
                "session_list_limit": "\(cleanLimit)",
                "terminal_launcher": launcher,
            ])
        }
    }

    @objc private func promptPetSearch() {
        NSApp.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        configureNeoAlert(alert)
        let panel = makeNeoPanel(
            width: 430,
            height: 168,
            title: tr("searchPetShareTitle"),
            subtitle: tr("searchPetShareInfo"),
            accent: neoColor(0xffc857)
        )
        let input = NSTextField(frame: NSRect(x: 18, y: 22, width: 386, height: 30))
        input.placeholderString = "mimi, robot, pixel..."
        styleNeoTextField(input)
        panel.card.addSubview(input)
        alert.accessoryView = panel.container
        alert.addButton(withTitle: tr("search"))
        alert.addButton(withTitle: tr("cancel"))
        let response = alert.runModal()
        if response == .alertFirstButtonReturn {
            emitJSONAction([
                "action": "search_pet_share",
                "query": input.stringValue,
            ])
        }
    }

    @objc private func clearPetArtwork() {
        emitJSONAction(["action": "clear_pet_artwork"])
    }

    @objc private func openPetShareSite() {
        if let url = URL(string: "https://codex-pet-share.pages.dev/") {
            NSWorkspace.shared.open(url)
        }
    }

    @objc private func listNewestPets() {
        emitPetShareList(sort: "new")
    }

    @objc private func listPopularPets() {
        emitPetShareList(sort: "popular")
    }

    @objc private func listViewedPets() {
        emitPetShareList(sort: "views")
    }

    @objc private func applyInstalledPetArtwork(_ sender: NSMenuItem) {
        guard let assetID = sender.representedObject as? String else { return }
        emitJSONAction([
            "action": "apply_installed_pet",
            "asset_id": assetID,
        ])
    }

    private func emitPetShareList(sort: String) {
        emitJSONAction([
            "action": "search_pet_share",
            "query": "",
            "sort": sort,
        ])
    }

    @objc private func openSessionCLI(_ sender: NSMenuItem) {
        emitSessionAction("open_session_cli", sessionID: sender.representedObject as? String)
    }

    @objc private func openSessionTUI(_ sender: NSMenuItem) {
        emitSessionAction("open_session_tui", sessionID: sender.representedObject as? String)
    }

    @objc private func focusSession(_ sender: NSMenuItem) {
        emitSessionAction(
            "focus_session",
            sessionID: sender.representedObject as? String,
            allowResume: leftClickOpensTerminal
        )
    }

    private func emitAction(_ action: String) {
        emitJSONAction(["action": action])
    }

    private func emitJSONAction(_ payload: [String: String]) {
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let line = String(data: data, encoding: .utf8)?.appending("\n"),
              let lineData = line.data(using: .utf8)
        else {
            return
        }
        FileHandle.standardOutput.write(lineData)
    }

    private func emitActionLine(_ line: String) {
        if let data = (line + "\n").data(using: .utf8) {
            FileHandle.standardOutput.write(data)
        }
    }

    private func emitSessionAction(_ action: String, sessionID: String?, allowResume: Bool? = nil) {
        guard let sessionID else { return }
        var payload = [
            "action": action,
            "session_id": sessionID,
        ]
        if let allowResume {
            payload["allow_resume"] = allowResume ? "true" : "false"
        }
        emitJSONAction(payload)
    }

    private func showPetShareResponse(_ response: PetShareResponse) {
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            switch response.status {
            case "results":
                self.showPetShareResults(response)
            case "applied", "cleared":
                self.showPetShareMessage(title: "Hermes Pet", message: response.message)
            case "error":
                self.showPetShareMessage(title: "Codex Pet Share", message: response.message)
            default:
                break
            }
        }
    }

    private func showPetShareResults(_ response: PetShareResponse) {
        NSApp.activate(ignoringOtherApps: true)
        if response.pets.isEmpty {
            let alert = NSAlert()
            configureNeoAlert(alert)
            let message = response.query.isEmpty ? tr("noNewestPets") : "\(tr("noSearchResults")) \"\(response.query)\"."
            alert.accessoryView = makeNeoMessageView(title: tr("noPetsFound"), message: message)
            alert.addButton(withTitle: tr("searchAgain"))
            alert.addButton(withTitle: tr("cancel"))
            if alert.runModal() == .alertFirstButtonReturn {
                promptPetSearch()
            }
            return
        }

        pendingPetSelectionID = response.pets[0].id
        petShareSelectionButtons = []
        let grid = makePetShareGrid(response.pets)
        let panel = makeNeoPanel(
            width: 506,
            height: grid.frame.height + 112,
            title: tr("changePet"),
            subtitle: "\(response.message). \(tr("chooseApply"))",
            accent: neoColor(0xb9ff66)
        )
        grid.frame.origin = NSPoint(x: 18, y: 18)
        panel.card.addSubview(grid)

        let alert = NSAlert()
        configureNeoAlert(alert)
        alert.accessoryView = panel.container
        alert.addButton(withTitle: tr("apply"))
        alert.addButton(withTitle: tr("searchAgain"))
        alert.addButton(withTitle: tr("cancel"))
        let choice = alert.runModal()
        if choice == .alertFirstButtonReturn {
            let selectedID = pendingPetSelectionID ?? response.pets[0].id
            emitJSONAction([
                "action": "apply_share_pet",
                "pet_id": selectedID,
            ])
        } else if choice == .alertSecondButtonReturn {
            promptPetSearch()
        }
        petShareSelectionButtons = []
        pendingPetSelectionID = nil
    }

    private func makePetShareGrid(_ pets: [PetShareResult]) -> NSView {
        let columns = 4
        let cellWidth: CGFloat = 112
        let cellHeight: CGFloat = 112
        let rows = max(1, Int(ceil(Double(pets.count) / Double(columns))))
        let contentWidth = CGFloat(columns) * cellWidth
        let contentHeight = CGFloat(rows) * cellHeight
        let document = NSView(frame: NSRect(x: 0, y: 0, width: contentWidth, height: contentHeight))

        for (index, pet) in pets.enumerated() {
            let column = index % columns
            let row = index / columns
            let x = CGFloat(column) * cellWidth + 6
            let y = contentHeight - CGFloat(row + 1) * cellHeight + 6
            let button = NSButton(frame: NSRect(x: x, y: y, width: cellWidth - 12, height: cellHeight - 12))
            button.setButtonType(.toggle)
            button.bezelStyle = .regularSquare
            button.title = petGridTitle(pet)
            button.font = NSFont.systemFont(ofSize: 11, weight: .medium)
            button.alignment = .center
            button.imagePosition = .imageAbove
            button.imageScaling = .scaleProportionallyUpOrDown
            button.identifier = NSUserInterfaceItemIdentifier(pet.id)
            button.target = self
            button.action = #selector(selectPetShareResult(_:))
            button.state = index == 0 ? .on : .off
            if let thumbnailPath = pet.thumbnail_path,
               !thumbnailPath.isEmpty,
               let image = NSImage(contentsOfFile: thumbnailPath) {
                image.size = NSSize(width: 54, height: 54)
                button.image = image
            }
            styleNeoPetButton(button)
            document.addSubview(button)
            petShareSelectionButtons.append(button)
        }

        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 460, height: min(contentHeight, 260)))
        scroll.hasVerticalScroller = rows > 2
        scroll.hasHorizontalScroller = false
        scroll.borderType = .noBorder
        scroll.documentView = document
        return scroll
    }

    private func petGridTitle(_ pet: PetShareResult) -> String {
        let title = pet.display_name.isEmpty ? pet.id : pet.display_name
        let owner = pet.owner_name.isEmpty ? "" : "\n\(pet.owner_name)"
        return "\(String(title.prefix(18)))\(owner)"
    }

    @objc private func selectPetShareResult(_ sender: NSButton) {
        guard let selectedID = sender.identifier?.rawValue else { return }
        pendingPetSelectionID = selectedID
        for button in petShareSelectionButtons {
            button.state = button === sender ? .on : .off
        }
        updatePetShareButtonStyles()
    }

    private func showPetShareMessage(title: String, message: String) {
        NSApp.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        configureNeoAlert(alert)
        alert.accessoryView = makeNeoMessageView(title: title, message: message)
        alert.addButton(withTitle: tr("ok"))
        alert.runModal()
    }

    override func draw(_ dirtyRect: NSRect) {
        NSColor.clear.setFill()
        dirtyRect.fill()

        if pets.isEmpty {
            drawPet(
                PetState(
                    source_id: "local-hermes",
                    label: "Hermes",
                    state: "idle",
                    message: "ready",
                    animation: nil,
                    direction: nil,
                    pet_action: nil,
                    emotion: nil,
                    asset_id: nil,
                    asset_dir: nil,
                    asset_version: nil,
                    notification_count: nil,
                    notification_kind: nil,
                    notification_label: nil
                ),
                index: 0
            )
            return
        }

        for (index, pet) in pets.enumerated() {
            drawPet(pet, index: index)
        }
    }

    private func drawPet(_ pet: PetState, index: Int) {
        let x = CGFloat(index) * slotWidth + 8
        let now = Date().timeIntervalSinceReferenceDate
        let offset = motionOffset(for: pet, now: now)
        let imageRect = NSRect(
            x: x + offset.x,
            y: bounds.height - petSize - 6 + offset.y,
            width: petSize,
            height: petSize
        )
        frameImage(for: pet)?.draw(in: imageRect, from: .zero, operation: .sourceOver, fraction: 1.0)
        drawBadge(for: pet, at: NSPoint(x: x + petSize - 18 + offset.x, y: imageRect.maxY - 22))
    }

    private func frameImage(for pet: PetState) -> NSImage? {
        let now = Date().timeIntervalSinceReferenceDate
        let bundle = imageBundle(for: pet)
        let framesByKey = bundle?.animationFrames ?? animationFrames
        let durationsByKey = bundle?.animationDurations ?? animationDurations
        let frameDurationsByKey = bundle?.animationFrameDurations ?? animationFrameDurations
        let loopStartIndexesByKey = bundle?.animationLoopStartIndexes ?? animationLoopStartIndexes
        let imagesByKey = bundle?.images ?? images
        let animation = effectiveAnimationKey(for: pet, frames: framesByKey)
        if let frames = framesByKey[animation], !frames.isEmpty {
            let duration = max(durationsByKey[animation] ?? 1.0, 0.2)
            let playback = animationPlayback[pet.source_id]
            let startedAt: TimeInterval
            if let playback, playback.key == animation {
                startedAt = playback.startedAt
            } else {
                startedAt = now
                animationPlayback[pet.source_id] = AnimationPlayback(key: animation, startedAt: now)
            }
            let index = animationFrameIndex(
                frameCount: frames.count,
                fallbackDuration: duration,
                frameDurations: frameDurationsByKey[animation],
                loopStartIndex: loopStartIndexesByKey[animation],
                startedAt: startedAt,
                now: now
            )
            return frames[index]
        }

        let state = pet.state
        if state == "running" {
            return imagesByKey["working"] ?? imagesByKey["idle"]
        }
        if state == "waiting" || state == "review" {
            return imagesByKey["review"] ?? imagesByKey["idle"]
        }
        if state == "failed" {
            return imagesByKey["blink"] ?? imagesByKey["idle"]
        }
        if [0, 1].contains(Int(now * 10) % 36) {
            return imagesByKey["blink"] ?? imagesByKey["idle"]
        }
        return imagesByKey["idle"]
    }

    private func animationFrameIndex(
        frameCount: Int,
        fallbackDuration: TimeInterval,
        frameDurations: [TimeInterval]?,
        loopStartIndex: Int?,
        startedAt: TimeInterval,
        now: TimeInterval
    ) -> Int {
        guard frameCount > 1 else { return 0 }
        let durations: [TimeInterval]
        if let frameDurations, frameDurations.count == frameCount {
            durations = frameDurations
        } else {
            durations = Array(repeating: max(fallbackDuration, 0.2) / TimeInterval(frameCount), count: frameCount)
        }
        let totalDuration = durations.reduce(0.0, +)
        guard totalDuration > 0 else { return 0 }

        var elapsed = max(0.0, now - startedAt)
        if let loopStartIndex,
           loopStartIndex >= 0,
           loopStartIndex < frameCount {
            let introDuration = durations.prefix(loopStartIndex).reduce(0.0, +)
            let loopDuration = durations.suffix(frameCount - loopStartIndex).reduce(0.0, +)
            if elapsed >= introDuration, loopDuration > 0 {
                elapsed = introDuration + (elapsed - introDuration).truncatingRemainder(dividingBy: loopDuration)
            }
        } else {
            elapsed = elapsed.truncatingRemainder(dividingBy: totalDuration)
        }

        var cursor = 0.0
        for (index, duration) in durations.enumerated() {
            cursor += duration
            if elapsed < cursor {
                return index
            }
        }
        return frameCount - 1
    }

    private func motionOffset(for pet: PetState, now: TimeInterval) -> NSPoint {
        let framesByKey = imageBundle(for: pet)?.animationFrames ?? animationFrames
        let key = effectiveAnimationKey(for: pet, frames: framesByKey)
        if framesByKey[key] != nil {
            return .zero
        }
        switch key {
        case "running-left":
            return NSPoint(x: CGFloat(-2.0 - abs(sin(now * 9.0)) * 3.0), y: CGFloat(sin(now * 18.0) * 1.2))
        case "running-right", "running":
            return NSPoint(x: CGFloat(2.0 + abs(sin(now * 9.0)) * 3.0), y: CGFloat(sin(now * 18.0) * 1.2))
        case "jumping":
            return NSPoint(x: 0, y: CGFloat(abs(sin(now * 5.5)) * 8.0))
        case "failed":
            return NSPoint(x: CGFloat((Int(now * 18.0) % 2 == 0) ? -2.0 : 2.0), y: 0)
        case "waiting":
            return NSPoint(x: 0, y: CGFloat(sin(now * 3.2) * 2.0))
        case "waving":
            return NSPoint(x: 0, y: CGFloat(sin(now * 6.0) * 1.4))
        default:
            return .zero
        }
    }

    private func imageBundle(for pet: PetState) -> PetImageBundle? {
        guard let assetDirPath = pet.asset_dir, !assetDirPath.isEmpty else {
            return nil
        }
        let key = pet.asset_version ?? assetDirPath
        if let bundle = petImageBundles[key] {
            return bundle
        }
        let bundle = loadImageBundle(from: URL(fileURLWithPath: assetDirPath, isDirectory: true))
        if !bundle.images.isEmpty || !bundle.animationFrames.isEmpty {
            petImageBundles[key] = bundle
            return bundle
        }
        return nil
    }

    private func effectiveAnimationKey(for pet: PetState, frames: [String: [NSImage]]) -> String {
        if let dragAnimationKey, frames[dragAnimationKey] != nil {
            return dragAnimationKey
        }
        if hoverAnimationEnabled && dragStartMouse == nil && frames["jumping"] != nil {
            return "jumping"
        }
        return animationKey(for: pet, frames: frames)
    }

    private func animationKey(for pet: PetState, frames: [String: [NSImage]]) -> String {
        if let animation = normalizedToken(pet.animation), frames[animation] != nil {
            return animation
        }

        if let action = normalizedToken(pet.pet_action) {
            if ["run", "running", "move", "working"].contains(action) {
                return directionalRunningKey(pet.direction, frames: frames)
            }
            if ["wave", "waving"].contains(action) {
                return "waving"
            }
            if ["jump", "jumping"].contains(action) {
                return "jumping"
            }
            if ["wait", "waiting", "think", "thinking"].contains(action) {
                return "waiting"
            }
            if ["review", "done", "complete", "success", "celebrate", "celebrating", "launch", "hello"].contains(action) {
                return "review"
            }
            if ["fail", "failed", "error"].contains(action) {
                return "failed"
            }
        }

        if let emotion = normalizedToken(pet.emotion) {
            if ["happy", "done", "ready", "success", "excited", "celebrating"].contains(emotion) {
                return "review"
            }
            if ["waiting", "patient", "thinking", "focused"].contains(emotion) {
                return pet.state == "running" ? directionalRunningKey(pet.direction, frames: frames) : "waiting"
            }
            if ["sad", "angry", "error", "failed"].contains(emotion) {
                return "failed"
            }
        }

        switch pet.state {
        case "running":
            return directionalRunningKey(pet.direction, frames: frames)
        case "waiting":
            return "waiting"
        case "failed":
            return "failed"
        case "review":
            return "review"
        default:
            return "idle"
        }
    }

    private func directionalRunningKey(_ direction: String?, frames: [String: [NSImage]]) -> String {
        if let direction = normalizedToken(direction) {
            if ["left", "west", "back"].contains(direction) {
                return "running-left"
            }
            if ["right", "east", "forward"].contains(direction) {
                return "running-right"
            }
        }
        return frames["running"] != nil ? "running" : "running-right"
    }

    private func normalizedToken(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if trimmed.isEmpty {
            return nil
        }
        return trimmed.replacingOccurrences(of: "_", with: "-")
    }

    private func drawBadge(for pet: PetState, at point: NSPoint) {
        let count = pet.notification_count ?? fallbackNotificationCount(for: pet)
        if count <= 0 {
            return
        }
        let color: NSColor
        switch normalizedToken(pet.notification_kind) ?? pet.state {
        case "choice", "attention", "waiting":
            color = NSColor(calibratedRed: 0.96, green: 0.62, blue: 0.04, alpha: 0.92)
        case "failed", "error":
            color = NSColor(calibratedRed: 0.94, green: 0.27, blue: 0.27, alpha: 0.92)
        case "done", "review":
            color = NSColor(calibratedRed: 0.14, green: 0.82, blue: 0.73, alpha: 0.92)
        default:
            color = NSColor(calibratedWhite: 0.32, alpha: 0.86)
        }
        let text = badgeText(for: pet, count: count)

        let badgeRect = NSRect(x: point.x, y: point.y, width: 22, height: 22)
        let path = NSBezierPath(ovalIn: badgeRect)
        color.setFill()
        path.fill()
        NSColor(calibratedWhite: 0.0, alpha: 0.14).setStroke()
        path.lineWidth = 1
        path.stroke()

        if !text.isEmpty {
            let paragraph = NSMutableParagraphStyle()
            paragraph.alignment = .center
            let fontSize: CGFloat = text.count >= 3 ? 10 : 13
            let attributes: [NSAttributedString.Key: Any] = [
                .font: NSFont.systemFont(ofSize: fontSize, weight: .semibold),
                .foregroundColor: NSColor.black,
                .paragraphStyle: paragraph,
            ]
            let string = NSAttributedString(string: text, attributes: attributes)
            let textSize = string.size()
            let textRect = NSRect(
                x: badgeRect.midX - textSize.width / 2.0,
                y: badgeRect.midY - textSize.height / 2.0 - 1.0,
                width: textSize.width,
                height: textSize.height
            )
            string.draw(in: textRect)
        }
    }

    private func fallbackNotificationCount(for pet: PetState) -> Int {
        switch pet.state {
        case "waiting", "failed", "review":
            return 1
        default:
            return 0
        }
    }

    private func badgeText(for pet: PetState, count: Int) -> String {
        if let label = pet.notification_label?.trimmingCharacters(in: .whitespacesAndNewlines), !label.isEmpty {
            return String(label.prefix(4))
        }
        let kind = normalizedToken(pet.notification_kind)
        if kind == "choice" || kind == "attention" || kind == "failed" || pet.state == "waiting" || pet.state == "failed" {
            return "!"
        }
        if count > 99 {
            return "99+"
        }
        return String(max(1, count))
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var panel: NSPanel?
    private var petView: PetOverlayView?
    private var assetDir: URL
    private var petSize: CGFloat
    private var initialX: CGFloat?
    private var initialY: CGFloat?

    init(assetDir: URL, petSize: CGFloat, initialX: CGFloat?, initialY: CGFloat?) {
        self.assetDir = assetDir
        self.petSize = petSize
        self.initialX = initialX
        self.initialY = initialY
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)

        let size = NSSize(width: petSize + 26, height: petSize + 30)
        let screenFrame = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let origin = NSPoint(
            x: initialX ?? (screenFrame.maxX - size.width - 96),
            y: initialY ?? (screenFrame.minY + 120)
        )

        let panel = NSPanel(
            contentRect: NSRect(origin: origin, size: size),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.level = .statusBar
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        panel.hidesOnDeactivate = false
        panel.isMovableByWindowBackground = false

        let view = PetOverlayView(
            frame: NSRect(origin: .zero, size: size),
            petSize: petSize,
            assetDir: assetDir,
            initialPets: []
        )
        view.attach(panel: panel)
        view.startAnimation()
        panel.contentView = view
        panel.orderFrontRegardless()

        self.panel = panel
        self.petView = view

        readSnapshots()
    }

    private func readSnapshots() {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            while let line = readLine() {
                guard let data = line.data(using: .utf8) else { continue }
                guard let snapshot = try? JSONDecoder().decode(PetSnapshot.self, from: data) else { continue }
                DispatchQueue.main.async {
                    self?.petView?.setSnapshot(snapshot)
                }
            }
            DispatchQueue.main.async {
                NSApp.terminate(nil)
            }
        }
    }
}

func parseArguments() -> (URL, CGFloat, CGFloat?, CGFloat?) {
    let args = CommandLine.arguments.dropFirst()
    var assetDir = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
    var size: CGFloat = 84
    var x: CGFloat?
    var y: CGFloat?
    var iterator = args.makeIterator()

    while let arg = iterator.next() {
        switch arg {
        case "--asset-dir":
            if let value = iterator.next() {
                assetDir = URL(fileURLWithPath: value)
            }
        case "--size":
            if let value = iterator.next(), let parsed = Double(value) {
                size = CGFloat(max(56, min(parsed, 160)))
            }
        case "--x":
            if let value = iterator.next(), let parsed = Double(value) {
                x = CGFloat(parsed)
            }
        case "--y":
            if let value = iterator.next(), let parsed = Double(value) {
                y = CGFloat(parsed)
            }
        default:
            continue
        }
    }

    return (assetDir, size, x, y)
}

let (assetDir, petSize, x, y) = parseArguments()
let app = NSApplication.shared
let delegate = AppDelegate(assetDir: assetDir, petSize: petSize, initialX: x, initialY: y)
app.delegate = delegate
app.run()
