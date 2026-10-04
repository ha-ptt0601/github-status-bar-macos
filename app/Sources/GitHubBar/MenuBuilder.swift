import AppKit
import GitHubBarCore

/// The menu's tab bar; `names` holds each segment's `tab` value.
final class TabControl: NSSegmentedControl {
    var names: [String] = []
}

/// Turns parsed SwiftBar-format entries into AppKit menu items.
enum MenuBuilder {
    /// Called when a `keep=` row is clicked; set by the app.
    static var keepOpenHandler: ((KeepOpenView) -> Void)?

    static func menu(_ entries: [MenuEntry], target: AnyObject, action: Selector,
                     tabAction: Selector? = nil) -> NSMenu {
        let menu = NSMenu()
        fill(menu, entries, target: target, action: action, tabAction: tabAction)
        return menu
    }

    /// Adds the entries to `menu`. Consecutive `tab=` entries become one segmented control, so
    /// switching tabs does not close the menu (a click on a plain item always would).
    static func fill(_ menu: NSMenu, _ entries: [MenuEntry], target: AnyObject, action: Selector,
                     tabAction: Selector? = nil) {
        menu.autoenablesItems = false  // keep header lines in their own colour instead of greyed out
        let topLevel = tabAction != nil
        var pane = ""
        var index = 0
        while index < entries.count {
            let entry = entries[index]
            // `pane=` marker: the following top-level items belong to that tab (see `chip swiftbar --panes`).
            if entry.text.isEmpty, let name = entry.params["pane"] {
                pane = name
                if entry.params["active"] == "true" { activePane = name }
                index += 1
                continue
            }
            let added: NSMenuItem
            if let tabAction, entry.params["tab"] != nil {
                var tabs: [MenuEntry] = []
                while index < entries.count, entries[index].params["tab"] != nil {
                    tabs.append(entries[index])
                    index += 1
                }
                added = tabItem(tabs, target: target, action: tabAction)
            } else if entry.params["searchfield"] == "true" {
                added = NSMenuItem()
                added.view = SearchFieldView(placeholder: entry.text, text: query)
                index += 1
            } else {
                added = item(entry, target: target, action: action)
                index += 1
                if let proj = entry.params["proj"], entry.params["hidden"] == "true" { hiddenProjects.insert(proj) }
            }
            if topLevel {
                meta[added] = ItemMeta(pane: pane, proj: entry.params["proj"] ?? "",
                                       body: entry.params["body"] == "true",
                                       searchOnly: entry.params["searchonly"] == "true",
                                       find: entry.params["find"] ?? "", noMatch: entry.params["nomatch"] == "true")
            }
            menu.addItem(added)
        }
        guard topLevel else { return }
        // Measure with every regular item shown, so both tabs share the widest one's width and
        // switching tabs never resizes (or truncates) the open menu.
        menu.items.forEach { $0.isHidden = meta[$0]?.searchOnly ?? false || meta[$0]?.noMatch ?? false }
        menu.minimumWidth = 0
        menu.minimumWidth = menu.size.width
        updateVisibility(menu)
    }

    /// What decides whether a top-level item is shown.
    struct ItemMeta {
        var pane = "", proj = "", body = false, searchOnly = false, find = "", noMatch = false
    }

    static var meta: [NSMenuItem: ItemMeta] = [:]
    /// The tab shown, the projects hidden and the search text; GitHubBar changes them in place while the menu is open.
    static var activePane = ""
    static var hiddenProjects: Set<String> = []
    static var query = ""
    static let searchLimit = 40

    /// Shows the active tab without hidden projects, or, while searching, the matching PRs instead of the lists.
    static func updateVisibility(_ menu: NSMenu) {
        let words = query.lowercased().split(separator: " ").map(String.init)
        let searching = !words.isEmpty
        var matches = 0
        for item in menu.items {
            guard let m = meta[item] else { continue }
            var hidden = !m.pane.isEmpty && m.pane != activePane
            if m.body && (searching || (!m.proj.isEmpty && hiddenProjects.contains(m.proj))) { hidden = true }
            if !m.body && !m.searchOnly && !m.proj.isEmpty && hiddenProjects.contains(m.proj) { hidden = true }
            if m.searchOnly {
                let match = searching && !hidden && matches < searchLimit && words.allSatisfy(m.find.contains)
                if match { matches += 1 }
                hidden = !match
            }
            if m.noMatch { hidden = true }
            item.isHidden = hidden
        }
        for item in menu.items where meta[item]?.noMatch == true && meta[item]?.pane == activePane {
            item.isHidden = !(searching && matches == 0)
        }
        for case let field as SearchFieldView in menu.items.compactMap(\.view) where field.text != query {
            field.text = query
        }
    }

    static func tabItem(_ tabs: [MenuEntry], target: AnyObject, action: Selector) -> NSMenuItem {
        let control = TabControl(labels: tabs.map(\.text), trackingMode: .selectOne, target: target, action: action)
        control.names = tabs.map { $0.params["tab"] ?? "" }
        control.selectedSegment = tabs.firstIndex { $0.params["checked"] == "true" } ?? 0
        control.segmentDistribution = .fillEqually
        control.controlSize = .regular
        control.sizeToFit()
        let width = max(control.frame.width + 28, 300)
        let view = NSView(frame: NSRect(x: 0, y: 0, width: width, height: control.frame.height + 10))
        control.frame = NSRect(x: 14, y: 5, width: width - 28, height: control.frame.height)
        control.autoresizingMask = [.width]
        view.autoresizingMask = [.width]
        view.addSubview(control)
        let item = NSMenuItem()
        item.view = view
        return item
    }

    static func item(_ entry: MenuEntry, target: AnyObject, action: Selector) -> NSMenuItem {
        if entry.isSeparator {
            return .separator()
        }
        if entry.params["keep"] != nil, entry.params["bash"] != nil, entry.children.isEmpty {
            let view = KeepOpenView(entry)
            view.onClick = keepOpenHandler
            let item = NSMenuItem()
            item.view = view
            item.representedObject = entry
            return item
        }
        let item = NSMenuItem(title: entry.text, action: nil, keyEquivalent: "")
        item.attributedTitle = attributedText(entry)
        item.image = image(entry, height: 16)
        item.toolTip = entry.params["tooltip"]
        item.state = entry.params["checked"] == "true" ? .on : .off
        item.isEnabled = entry.params["disabled"] != "true"
        item.representedObject = entry
        if !entry.children.isEmpty {
            item.submenu = menu(entry.children, target: target, action: action)
        } else if item.isEnabled && (entry.params["bash"] != nil || entry.params["href"] != nil) {
            item.target = target
            item.action = action
        }
        return item
    }

    static func attributedText(_ entry: MenuEntry) -> NSAttributedString {
        let size = entry.params["size"].flatMap(Double.init).map { CGFloat($0) } ?? NSFont.systemFontSize
        let font = entry.params["font"].flatMap { NSFont(name: $0, size: size) } ?? NSFont.menuFont(ofSize: size)
        var attributes: [NSAttributedString.Key: Any] = [.font: font]
        if let hex = entry.params["color"], let color = color(hex) {
            attributes[.foregroundColor] = color
        }
        return NSAttributedString(string: entry.text, attributes: attributes)
    }

    /// `templateImage` (base64 PNG, tinted by macOS) or `sfimage` (+ `sfconfig` palette colours).
    static func image(_ entry: MenuEntry, height: CGFloat) -> NSImage? {
        if let base64 = entry.params["templateImage"], let data = Data(base64Encoded: base64),
           let image = NSImage(data: data) {
            image.isTemplate = true
            let ratio = image.size.height > 0 ? image.size.width / image.size.height : 1
            image.size = NSSize(width: height * ratio, height: height)
            return image
        }
        guard let name = entry.params["sfimage"],
              var image = NSImage(systemSymbolName: name, accessibilityDescription: nil) else {
            return nil
        }
        if let config = entry.params["sfconfig"], let data = Data(base64Encoded: config),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let hexes = json["colors"] as? [String] {
            let colors = hexes.compactMap(color)
            if !colors.isEmpty, let tinted = image.withSymbolConfiguration(.init(paletteColors: colors)) {
                image = tinted
            }
        }
        return image
    }

    static func color(_ hex: String) -> NSColor? {
        var value = hex.trimmingCharacters(in: .whitespaces)
        if value.hasPrefix("#") { value.removeFirst() }
        guard value.count == 6, let rgb = UInt32(value, radix: 16) else { return nil }
        return NSColor(srgbRed: CGFloat((rgb >> 16) & 0xFF) / 255, green: CGFloat((rgb >> 8) & 0xFF) / 255,
                       blue: CGFloat(rgb & 0xFF) / 255, alpha: 1)
    }
}

/// The search field at the top of the menu: filters the open menu as you type.
final class SearchFieldView: NSView, NSSearchFieldDelegate {
    static var onChange: ((String) -> Void)?
    private let field = NSSearchField()

    var text: String {
        get { field.stringValue }
        set { field.stringValue = newValue }
    }

    init(placeholder: String, text: String) {
        super.init(frame: NSRect(x: 0, y: 0, width: 300, height: 32))
        autoresizingMask = [.width]
        field.placeholderString = placeholder
        field.stringValue = text
        field.sendsSearchStringImmediately = true
        field.delegate = self
        field.frame = NSRect(x: 14, y: 4, width: 272, height: 24)
        field.autoresizingMask = [.width]
        addSubview(field)
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    func controlTextDidChange(_ obj: Notification) {
        Self.onChange?(field.stringValue)
    }

    /// Put the cursor in the field (when the menu opens).
    func focus() {
        window?.makeFirstResponder(field)
    }
}

/// A menu row drawn like a normal item that runs its action without closing the menu
/// (AppKit closes the menu after a click on a plain item). Used for `keep=` entries.
final class KeepOpenView: NSView {
    let entry: MenuEntry
    var checked: Bool { didSet { needsDisplay = true } }
    var onClick: ((KeepOpenView) -> Void)?
    private let icon: NSImage?
    private var spinner: NSProgressIndicator?
    /// Shown instead of the entry's text while set (e.g. "Refreshing…", "✓ Up to date").
    var statusText: String? { didSet { needsDisplay = true } }

    /// Spinner in place of the icon plus `text`, or back to normal with `busy == false`.
    func setBusy(_ busy: Bool, text: String? = nil) {
        statusText = text
        if busy, spinner == nil {
            let indicator = NSProgressIndicator(frame: NSRect(x: 30, y: (bounds.height - 16) / 2, width: 16, height: 16))
            indicator.style = .spinning
            indicator.controlSize = .small
            indicator.usesThreadedAnimation = true  // keeps spinning while the menu tracks
            addSubview(indicator)
            indicator.startAnimation(nil)
            spinner = indicator
        } else if !busy {
            spinner?.stopAnimation(nil)
            spinner?.removeFromSuperview()
            spinner = nil
        }
        needsDisplay = true
    }

    init(_ entry: MenuEntry) {
        self.entry = entry
        checked = entry.params["checked"] == "true"
        icon = MenuBuilder.image(entry, height: 16)
        let width = MenuBuilder.attributedText(entry).size().width + 70
        super.init(frame: NSRect(x: 0, y: 0, width: width, height: 24))
        autoresizingMask = [.width]
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    override func updateTrackingAreas() {
        trackingAreas.forEach(removeTrackingArea)
        addTrackingArea(NSTrackingArea(rect: bounds, options: [.mouseEnteredAndExited, .activeAlways],
                                       owner: self))
    }

    override func mouseEntered(with event: NSEvent) { needsDisplay = true }
    override func mouseExited(with event: NSEvent) { needsDisplay = true }

    override func mouseUp(with event: NSEvent) {
        onClick?(self)
    }

    override func draw(_ dirtyRect: NSRect) {
        let highlighted = enclosingMenuItem?.isHighlighted ?? false
        if highlighted {
            NSColor.selectedContentBackgroundColor.setFill()
            NSBezierPath(roundedRect: bounds.insetBy(dx: 5, dy: 0), xRadius: 5, yRadius: 5).fill()
        }
        let color: NSColor = highlighted ? .selectedMenuItemTextColor : .labelColor
        let font = NSFont.menuFont(ofSize: 0)
        if checked {
            NSAttributedString(string: "✓", attributes: [.font: font, .foregroundColor: color])
                .draw(at: NSPoint(x: 12, y: (bounds.height - font.pointSize - 4) / 2))
        }
        var x: CGFloat = 30
        if spinner != nil { x += 24 }
        if let icon, spinner == nil {
            let size = NSSize(width: 16, height: 16)
            // Tint inside the image's own context, so only the symbol's pixels take the colour.
            let tinted = NSImage(size: size, flipped: false) { rect in
                icon.draw(in: rect)
                color.set()
                rect.fill(using: .sourceAtop)
                return true
            }
            tinted.draw(in: NSRect(origin: NSPoint(x: x, y: (bounds.height - 16) / 2), size: size))
            x += 24
        }
        let text = NSAttributedString(string: statusText ?? entry.text, attributes: [.font: font, .foregroundColor: color])
        text.draw(at: NSPoint(x: x, y: (bounds.height - text.size().height) / 2))
    }
}
