import AppKit
import GitHubBarCore
import ServiceManagement

/// GitHubBar: shows `chip swiftbar` as a menu bar menu and runs the menu's actions.
final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    private var timer: Timer?
    private var menuIsOpen = false
    private var pending: ParsedMenu?
    private let queue = DispatchQueue(label: "githubbar.chip")

    /// `CHIP_PLUGIN` comes from the bundle's LSEnvironment (written by `chip install`).
    private var chip: String {
        ProcessInfo.processInfo.environment["CHIP_PLUGIN"]
            ?? (NSHomeDirectory() as NSString).appendingPathComponent(".local/bin/chip")
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        statusItem.button?.title = "…"
        // Open at login by default, once; afterwards the menu toggle decides.
        if !UserDefaults.standard.bool(forKey: "loginItemConfigured") {
            try? SMAppService.mainApp.register()
            UserDefaults.standard.set(true, forKey: "loginItemConfigured")
        }
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in self?.refresh() }
    }

    func refresh() {
        queue.async { [weak self] in
            guard let self else { return }
            let output = Self.run(self.chip, ["swiftbar"])
            let menu = MenuParser.parse(output)
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
        if let button = statusItem.button {
            button.image = MenuBuilder.image(parsed.title, height: 18)
            button.imagePosition = .imageLeft
            button.title = parsed.title.text.isEmpty ? "" : " " + parsed.title.text
        }
        let menu = MenuBuilder.menu(parsed.items, target: self, action: #selector(runEntry(_:)))
        menu.addItem(NSMenuItem.separator())
        let login = NSMenuItem(title: "Open at Login", action: #selector(toggleLoginItem(_:)), keyEquivalent: "")
        login.target = self
        login.state = SMAppService.mainApp.status == .enabled ? .on : .off
        menu.addItem(login)
        menu.addItem(NSMenuItem(title: "Quit GitHubBar", action: #selector(NSApplication.terminate(_:)),
                                keyEquivalent: "q"))
        menu.delegate = self
        statusItem.menu = menu
    }

    func menuWillOpen(_ menu: NSMenu) { menuIsOpen = true }

    func menuDidClose(_ menu: NSMenu) {
        menuIsOpen = false
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
        sender.state = SMAppService.mainApp.status == .enabled ? .on : .off
    }

    @objc func runEntry(_ sender: NSMenuItem) {
        guard let entry = sender.representedObject as? MenuEntry else { return }
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

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)  // menu bar only, no Dock icon
app.run()
