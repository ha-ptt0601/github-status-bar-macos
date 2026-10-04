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
        if let button = statusItem.button {
            button.image = MenuBuilder.image(parsed.title, height: 18)
            button.imagePosition = .imageLeft
            button.title = parsed.title.text.isEmpty ? "" : " " + parsed.title.text
            button.toolTip = parsed.title.params["tooltip"]
        }
        menu.removeAllItems()
        MenuBuilder.hiddenProjects = []
        MenuBuilder.meta = [:]
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
        case "all":
            siblings.filter { $0.entry.params["keep"] == "toggle" }.forEach { $0.checked = true }
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
            guard view.statusText == nil else { return }  // already starting
            view.setBusy(true, text: "Starting review…")
        }
        guard let bash = view.entry.params["bash"] else { return }
        let args = (1...20).compactMap { view.entry.params["param\($0)"] }
        queue.async { [weak self] in
            guard let self else { return }
            let output = Self.run(bash, args)
            if kind == "run" {
                // The click came from a PR submenu: say how it went on that row, and show the new state
                // (🔵 Reviewing) when the menu closes rather than rebuilding it under the open submenu.
                let started = output.contains("started ")
                let parsed = MenuParser.parse(Self.run(self.chip, Self.render))
                parsed.notifications.forEach(Self.post)
                self.onMainDuringMenu {
                    view.setBusy(false, text: started ? "✓ Review started" : "Could not start: see the notification")
                    if self.menuIsOpen { self.pending = parsed } else { self.apply(parsed) }
                }
            } else if kind == "refresh" {
                self.refillOpenMenu()
            } else if kind == "radio" {
                // A new status style redraws every row. The click came from an open submenu, and replacing
                // items under an open submenu is unsafe, so close the menu, swap it and open it again.
                self.refillOpenMenu(reopen: true)
            } else {
                let parsed = MenuParser.parse(Self.run(self.chip, Self.render))
                parsed.notifications.forEach(Self.post)
                DispatchQueue.main.async { if self.menuIsOpen { self.pending = parsed } else { self.apply(parsed) } }
            }
        }
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
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        let stdout = Pipe()
        process.standardOutput = stdout
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
        } catch {
            return "! | color=#FF3B30\n---\nCould not run \(executable): \(error.localizedDescription)"
        }
        let data = stdout.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return String(decoding: data, as: UTF8.self)
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
