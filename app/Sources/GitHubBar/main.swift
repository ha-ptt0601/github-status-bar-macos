import AppKit
import GitHubBarCore
import ServiceManagement
import UserNotifications

/// GitHubBar: shows `chip swiftbar` as a menu bar menu, runs the menu's actions and posts chip's notifications.
final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate, UNUserNotificationCenterDelegate {
    private let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    private var timer: Timer?
    private var menuIsOpen = false
    private var pending: ParsedMenu?
    private var refreshing = false
    private var lastParsed: ParsedMenu?

    /// A project was dragged or ticked in the Projects list: save the order and hidden projects, then
    /// rebuild the rest of the menu so the PR lists follow at once (the open Projects submenu stays).
    private func projectListChanged(_ view: ProjectListView) {
        let open = view.enclosingMenuItem?.menu
        let args = ["project", "arrange", "--order"] + view.order + ["--hidden"] + view.hiddenNames
        queue.async { [weak self] in
            guard let self else { return }
            _ = Self.run(self.chip, args)
            let parsed = MenuParser.parse(Self.run(self.chip, Self.render))
            self.onMainDuringMenu {
                if self.menuIsOpen {
                    self.pending = parsed
                    self.updateInPlace(parsed, open: open)
                } else {
                    self.apply(parsed)
                }
            }
        }
    }
    private var iconBase: NSImage?
    private var iconAttention = false
    private var spinTimer: Timer?
    private var spinAngle: CGFloat = 90
    private var reopenWith: ParsedMenu?
    private let queue = DispatchQueue(label: "githubbar.chip")

    /// `CHIP_PLUGIN` comes from the bundle's LSEnvironment (written by `chip install`).
    private var chip: String {
        ProcessInfo.processInfo.environment["CHIP_PLUGIN"]
            ?? (NSHomeDirectory() as NSString).appendingPathComponent(".local/bin/chip")
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusItem.button?.title = "…"
        // chip queues notifications for us instead of using osascript; `--deliver` hands them over.
        setenv("GITHUBBAR_NOTIFY", "1", 1)
        Self.restorePath()
        MenuBuilder.keepOpenHandler = { [weak self] view in self?.keepOpen(view) }
        ProjectListView.onChange = { [weak self] view in self?.projectListChanged(view) }
        SearchFieldView.onChange = { [weak self] text in
            MenuBuilder.query = text
            if let menu = self?.statusItem.menu { MenuBuilder.updateVisibility(menu) }
        }
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        center.requestAuthorization(options: [.alert, .sound]) { _, _ in }
        // Open at login unless the user turned it off in the menu. Checked on every launch, because
        // reinstalling the app (or moving it) drops its login item.
        if !UserDefaults.standard.bool(forKey: "loginItemOff"), SMAppService.mainApp.status != .enabled {
            try? SMAppService.mainApp.register()
        }
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in self?.refresh() }
        // After sleep, refresh once the network is back instead of waiting for the next minute.
        NSWorkspace.shared.notificationCenter.addObserver(forName: NSWorkspace.didWakeNotification, object: nil,
                                                          queue: .main) { [weak self] _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 5) { self?.refresh() }
        }
    }

    func refresh() {
        queue.async { [weak self] in
            guard let self else { return }
            let output = Self.run(self.chip, Self.render)
            let menu = MenuParser.parse(output)
            menu.notifications.forEach(Self.post)
            DispatchQueue.main.async {
                if self.menuIsOpen {
                    self.pending = menu  // never rebuild under the pointer
                } else {
                    self.apply(menu)
                }
            }
        }
    }

    private func apply(_ parsed: ParsedMenu) {
        let menu = NSMenu()
        menu.delegate = self
        fill(menu, parsed)
        statusItem.menu = menu
    }

    /// Sets the menu bar title and (re)fills `menu`, which may be open.
    private func fill(_ menu: NSMenu, _ parsed: ParsedMenu) {
        lastParsed = parsed
        setTitle(parsed.title)
        menu.removeAllItems()
        MenuBuilder.hiddenProjects = []
        MenuBuilder.meta = [:]
        build(into: menu, parsed)
    }

    /// The menu's items for `parsed` (tabs, lists, settings) plus Open at Login and Quit.
    private func build(into menu: NSMenu, _ parsed: ParsedMenu) {
        MenuBuilder.fill(menu, parsed.items, target: self, action: #selector(runEntry(_:)),
                         tabAction: #selector(switchTab(_:)))
        menu.addItem(NSMenuItem.separator())
        let login = NSMenuItem(title: "Open at Login", action: #selector(toggleLoginItem(_:)), keyEquivalent: "")
        login.target = self
        login.state = SMAppService.mainApp.status == .enabled ? .on : .off
        menu.addItem(login)
        menu.addItem(NSMenuItem(title: "Quit GitHubBar", action: #selector(NSApplication.terminate(_:)),
                                keyEquivalent: "q"))
    }

    /// Switches the tab inside the open menu by hiding the other tab's items; `chip view` remembers it.
    @objc func switchTab(_ sender: TabControl) {
        guard sender.selectedSegment >= 0, sender.selectedSegment < sender.names.count else { return }
        let name = sender.names[sender.selectedSegment]
        MenuBuilder.activePane = name
        if let menu = statusItem.menu {
            // Both tabs carry their own tab bar; keep the newly shown one in sync.
            for case let control as TabControl in menu.items.compactMap({ $0.view?.subviews.first }) {
                control.selectedSegment = control.names.firstIndex(of: name) ?? control.selectedSegment
            }
            MenuBuilder.updateVisibility(menu)
        }
        queue.async { [weak self] in
            guard let self else { return }
            _ = Self.run(self.chip, ["view", name])
        }
    }

    /// A `keep=` row was clicked: update its checkmarks at once, run its command, then refresh.
    /// `keep=refresh` and `keep=radio` (status style) refill the open menu at once; project toggles are
    /// already applied in place, so the rest of their changes (counts) wait until the menu closes.
    func keepOpen(_ view: KeepOpenView) {
        let kind = view.entry.params["keep"] ?? ""
        let siblings = view.enclosingMenuItem?.menu?.items.compactMap { $0.view as? KeepOpenView } ?? []
        switch kind {
        case "toggle":
            view.checked.toggle()
            if let proj = view.entry.params["param3"] {  // `chip project toggle <proj>`
                if view.checked { MenuBuilder.hiddenProjects.remove(proj) } else { MenuBuilder.hiddenProjects.insert(proj) }
            }
        case "radio": siblings.forEach { $0.checked = $0 === view }
        case "setting": view.checked.toggle()
        case "all":
            siblings.filter { $0.entry.params["keep"] == "toggle" }.forEach { $0.checked = true }
            view.enclosingMenuItem?.menu?.items.compactMap { $0.view as? ProjectListView }.forEach { $0.showAll() }
            MenuBuilder.hiddenProjects = []
        default: break
        }
        if let menu = statusItem.menu { MenuBuilder.updateVisibility(menu) }
        if kind == "refresh" {
            guard !refreshing else { return }  // one refresh at a time
            refreshing = true
            view.setBusy(true, text: "Refreshing…")
        }
        if kind == "run" {
            guard view.statusText == nil else { return }  // already running
            view.setBusy(true, text: view.entry.params["busy"] ?? view.entry.text)
        }
        guard let bash = view.entry.params["bash"] else { return }
        let args = (1...20).compactMap { view.entry.params["param\($0)"] }
        queue.async { [weak self] in
            guard let self else { return }
            let (_, status) = Self.runWithStatus(bash, args)
            if kind == "refresh" {
                self.refillOpenMenu()
                return
            }
            // Every other row sits in a submenu (a PR, Projects, Settings…): say how it went on that row,
            // rebuild the rest of the menu from the new state now, and the open branch when it closes.
            let parsed = MenuParser.parse(Self.run(self.chip, Self.render))
            parsed.notifications.forEach(Self.post)
            self.onMainDuringMenu {
                if kind == "run" {
                    view.setBusy(false, text: status == 0 ? (view.entry.params["done"] ?? "✓ Done")
                                                          : "Failed: see the notification")
                }
                if self.menuIsOpen {
                    self.pending = parsed
                    self.updateInPlace(parsed, open: view.enclosingMenuItem?.menu)
                } else {
                    self.apply(parsed)
                }
            }
        }
    }

    /// After an action inside a submenu: rebuild the whole menu from the new state, except the one
    /// top-level item whose submenu is open (removing that item while its submenu is open is unsafe).
    /// That item only gets its new title and icon; its submenu is refreshed when the menu closes
    /// (`pending`). Everything else (PR rows, the review list, counts, other tabs) shows the new state now.
    private func updateInPlace(_ parsed: ParsedMenu, open: NSMenu?) {
        lastParsed = parsed
        setTitle(parsed.title)
        guard let menu = statusItem.menu, let open,
              let keep = menu.items.first(where: { $0.submenu === open || ($0.submenu.map { Self.contains($0, open) } ?? false) })
        else { return }
        let keepIndex = menu.items.firstIndex(of: keep) ?? 0
        let keepKey = Self.identity(keep)
        let fresh = NSMenu()
        let savedMeta = MenuBuilder.meta[keep]
        MenuBuilder.hiddenProjects = []
        MenuBuilder.meta = [:]
        build(into: fresh, parsed)
        let counterpart = fresh.items.first { Self.identity($0) == keepKey }
        for item in menu.items where item !== keep { menu.removeItem(item) }
        // Rebuild around `keep`: new items go before it until its counterpart (or its old position, if it
        // has none) is reached, then after it, in the new menu's order.
        var insertAt = 0
        var placed = false
        for (index, item) in fresh.items.enumerated() {
            fresh.removeItem(item)  // an item can belong to one menu only
            if !placed && (item === counterpart || (counterpart == nil && index == keepIndex)) {
                placed = true
                insertAt = (menu.items.firstIndex(of: keep) ?? 0) + 1
                if item === counterpart {
                    keep.attributedTitle = item.attributedTitle
                    keep.image = item.image
                    keep.toolTip = item.toolTip
                    keep.representedObject = item.representedObject
                    MenuBuilder.meta[keep] = MenuBuilder.meta[item] ?? savedMeta
                    continue
                }
            }
            menu.insertItem(item, at: min(insertAt, menu.items.count))
            insertAt += 1
        }
        if counterpart == nil { MenuBuilder.meta[keep] = savedMeta }
        if counterpart == nil, keepKey.contains("|run|") {
            // A removed review: grey it out until the menu closes.
            let text = Self.runKey(keep.title).map { $0 + "removed" } ?? keep.title
            keep.attributedTitle = NSAttributedString(string: text, attributes: [
                .font: NSFont.menuFont(ofSize: 0), .foregroundColor: NSColor.secondaryLabelColor])
        }
        MenuBuilder.updateVisibility(menu)
    }

    /// Whether `menu` is `target` or contains it in a nested submenu.
    static func contains(_ menu: NSMenu, _ target: NSMenu) -> Bool {
        menu === target || menu.items.contains { $0.submenu.map { contains($0, target) } ?? false }
    }

    /// What identifies a top-level item across rebuilds: its tab, plus the PR label its submenu starts
    /// with, or the review key of a "Reviews by GitHubBar" row, or else its text.
    static func identity(_ item: NSMenuItem) -> String {
        let pane = MenuBuilder.meta[item]?.pane ?? ""
        if let first = item.submenu?.items.first?.title,
           first.range(of: #"^[\w.-]+#\d+$"#, options: .regularExpression) != nil {
            return pane + "|pr|" + first + "|" + (MenuBuilder.meta[item]?.searchOnly == true ? "s" : "")
        }
        if let entry = item.representedObject as? MenuEntry, let key = runKey(entry.text) { return pane + "|run|" + key }
        return pane + "|text|" + item.title
    }

    /// "api#2123 · Full review · " from a "Reviews by GitHubBar" row text.
    static func runKey(_ text: String) -> String? {
        guard let match = text.range(of: #"[\w.-]+#\d+ · [^·]+ · "#, options: .regularExpression) else { return nil }
        return String(text[match])
    }

    private func setTitle(_ title: MenuEntry) {
        guard let button = statusItem.button else { return }
        button.imagePosition = .imageLeft
        button.title = title.text.isEmpty ? "" : " " + title.text
        button.toolTip = title.params["tooltip"]
        iconBase = MenuBuilder.image(title, height: 18)
        iconAttention = title.params["attention"] == "true"
        let animate = title.params["animate"] == "true"
        if animate, spinTimer == nil {
            let timer = Timer(timeInterval: 0.08, repeats: true) { [weak self] _ in
                guard let self else { return }
                self.spinAngle = (self.spinAngle - 24).truncatingRemainder(dividingBy: 360)
                self.drawIcon()
            }
            RunLoop.main.add(timer, forMode: .common)  // keeps spinning while the menu is open
            spinTimer = timer
        } else if !animate {
            spinTimer?.invalidate()
            spinTimer = nil
        }
        drawIcon()
    }

    /// The GitHub mark, plus a spinning ring while a review runs and a yellow dot when one needs the user.
    /// A plain template image when neither, so macOS tints it like any menu bar icon.
    private func drawIcon() {
        guard let button = statusItem.button, let base = iconBase else { return }
        let spinning = spinTimer != nil, attention = iconAttention
        guard spinning || attention else {
            button.image = base
            return
        }
        let angle = spinAngle
        let size = NSSize(width: 20, height: 20)
        let image = NSImage(size: size, flipped: false) { rect in
            let mark = NSRect(x: 3, y: 3, width: 14, height: 14)
            // Tint the template mark with the menu bar's text colour (resolved when drawn).
            let tinted = NSImage(size: mark.size, flipped: false) { r in
                base.draw(in: r)
                NSColor.labelColor.set()
                r.fill(using: .sourceAtop)
                return true
            }
            tinted.draw(in: mark)
            if spinning {
                let ring = NSBezierPath()
                ring.appendArc(withCenter: NSPoint(x: rect.midX, y: rect.midY), radius: 9.2,
                               startAngle: angle, endAngle: angle + 110)
                ring.lineWidth = 1.6
                ring.lineCapStyle = .round
                NSColor.labelColor.setStroke()
                ring.stroke()
            }
            if attention {
                NSColor.systemYellow.setFill()
                NSBezierPath(ovalIn: NSRect(x: 13.5, y: 13.5, width: 6.5, height: 6.5)).fill()
            }
            return true
        }
        image.isTemplate = false
        button.image = image
    }

    /// Runs `block` on the main thread, also while a menu is open (event-tracking run loop mode).
    private func onMainDuringMenu(_ block: @escaping () -> Void) {
        performSelector(onMainThread: #selector(runBlock(_:)), with: BlockBox(block), waitUntilDone: false,
                        modes: [RunLoop.Mode.common.rawValue, RunLoop.Mode.eventTracking.rawValue])
    }

    @objc private func runBlock(_ box: BlockBox) { box.block() }

    /// Off the main thread: render the menu, then refill the (open) menu on the main thread. Uses
    /// performSelector with the event-tracking mode, which runs while a menu is open.
    private func refillOpenMenu(reopen: Bool = false) {
        let parsed = MenuParser.parse(Self.run(chip, Self.render))
        parsed.notifications.forEach(Self.post)
        performSelector(onMainThread: #selector(refillNow(_:)), with: ParsedBox(parsed, reopen: reopen), waitUntilDone: false,
                        modes: [RunLoop.Mode.common.rawValue, RunLoop.Mode.eventTracking.rawValue])
    }

    /// Shows the new menu, refilling it in place when it is open; a finished "Refresh now" row then
    /// says "✓ Up to date" for two seconds.
    @objc private func refillNow(_ box: ParsedBox) {
        if box.reopen && menuIsOpen, let menu = statusItem.menu {
            reopenWith = box.menu
            menu.cancelTrackingWithoutAnimation()
            return
        }
        pending = nil
        let wasRefreshing = refreshing
        refreshing = false
        guard menuIsOpen, let menu = statusItem.menu else { return apply(box.menu) }
        fill(menu, box.menu)
        menu.update()
        guard wasRefreshing,
              let row = menu.items.compactMap({ $0.view as? KeepOpenView })
                  .first(where: { $0.entry.params["keep"] == "refresh" && !($0.enclosingMenuItem?.isHidden ?? true) })
        else { return }
        row.statusText = "✓ Up to date"
        let timer = Timer(timeInterval: 2, repeats: false) { [weak row] _ in row?.statusText = nil }
        RunLoop.main.add(timer, forMode: .common)
    }

    func menuWillOpen(_ menu: NSMenu) {
        menuIsOpen = true
        // Ready to type: focus the visible search field once the menu window exists.
        let timer = Timer(timeInterval: 0.05, repeats: false) { _ in
            menu.items.first { !$0.isHidden && $0.view is SearchFieldView }.flatMap { $0.view as? SearchFieldView }?.focus()
        }
        RunLoop.main.add(timer, forMode: .common)
    }

    func menuDidClose(_ menu: NSMenu) {
        menuIsOpen = false
        if let parsed = reopenWith {
            reopenWith = nil
            pending = nil
            apply(parsed)
            DispatchQueue.main.async { self.statusItem.button?.performClick(nil) }
            return
        }
        if let menu = pending {
            pending = nil
            apply(menu)
        }
    }

    @objc func toggleLoginItem(_ sender: NSMenuItem) {
        if SMAppService.mainApp.status == .enabled {
            try? SMAppService.mainApp.unregister()
        } else {
            try? SMAppService.mainApp.register()
        }
        UserDefaults.standard.set(SMAppService.mainApp.status != .enabled, forKey: "loginItemOff")
        sender.state = SMAppService.mainApp.status == .enabled ? .on : .off
    }

    /// Posts a notification; its params (href, or bash + paramN) say what a click does.
    static func post(_ entry: MenuEntry) {
        let content = UNMutableNotificationContent()
        content.title = "GitHubBar"
        content.body = entry.text
        content.sound = .default
        content.userInfo = entry.params
        UNUserNotificationCenter.current().add(
            UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil))
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound, .list])
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        let params = response.notification.request.content.userInfo as? [String: String] ?? [:]
        DispatchQueue.main.async { self.handle(MenuEntry(params: params)) }
        completionHandler()
    }

    @objc func runEntry(_ sender: NSMenuItem) {
        guard let entry = sender.representedObject as? MenuEntry else { return }
        handle(entry)
    }

    /// Opens `href` and/or runs `bash` with `paramN` (refreshing afterwards when `refresh=true`).
    private func handle(_ entry: MenuEntry) {
        if let href = entry.params["href"], let url = URL(string: href) {
            NSWorkspace.shared.open(url)
        }
        guard let bash = entry.params["bash"] else { return }
        let args = (1...20).compactMap { entry.params["param\($0)"] }
        let refreshAfter = entry.params["refresh"] == "true"
        queue.async { [weak self] in
            _ = Self.run(bash, args)
            if refreshAfter {
                DispatchQueue.main.async { self?.refresh() }
            }
        }
    }

    /// launchd starts login items with PATH=/usr/bin:/bin:/usr/sbin:/sbin and ignores LSEnvironment's PATH,
    /// so gh, git and claude would not be found. Put the PATH `chip install` wrote back in front.
    static func restorePath() {
        let env = Bundle.main.object(forInfoDictionaryKey: "LSEnvironment") as? [String: String]
        let current = ProcessInfo.processInfo.environment["PATH"] ?? ""
        let wanted = (env?["PATH"] ?? "/opt/homebrew/bin:/usr/local/bin").split(separator: ":").map(String.init)
        var seen = Set<String>()
        let merged = (wanted + current.split(separator: ":").map(String.init)).filter { seen.insert($0).inserted }
        setenv("PATH", merged.joined(separator: ":"), 1)
    }

    /// Both tabs (switched in place) plus queued notifications.
    static let render = ["swiftbar", "--deliver", "--panes"]

    /// Runs a command and returns its stdout ("" on failure). Inherits the app's environment.
    static func run(_ executable: String, _ arguments: [String]) -> String {
        runWithStatus(executable, arguments).0
    }

    /// Runs a command and returns its stdout and exit status (-1 if it could not start).
    static func runWithStatus(_ executable: String, _ arguments: [String]) -> (String, Int32) {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        let stdout = Pipe()
        process.standardOutput = stdout
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
        } catch {
            return ("! | color=#FF3B30\n---\nCould not run \(executable): \(error.localizedDescription)", -1)
        }
        let data = stdout.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return (String(decoding: data, as: UTF8.self), process.terminationStatus)
    }
}

/// Carries a closure through performSelector (which takes an object).
final class BlockBox: NSObject {
    let block: () -> Void
    init(_ block: @escaping () -> Void) { self.block = block }
}

/// Carries a ParsedMenu through performSelector (which takes an object).
final class ParsedBox: NSObject {
    let menu: ParsedMenu
    let reopen: Bool
    init(_ menu: ParsedMenu, reopen: Bool = false) {
        self.menu = menu
        self.reopen = reopen
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)  // menu bar only, no Dock icon
app.run()
