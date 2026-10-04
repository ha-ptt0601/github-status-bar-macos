import AppKit
import GitHubBarCore

/// Turns parsed SwiftBar-format entries into AppKit menu items.
enum MenuBuilder {
    static func menu(_ entries: [MenuEntry], target: AnyObject, action: Selector) -> NSMenu {
        let menu = NSMenu()
        menu.autoenablesItems = false  // keep header lines in their own colour instead of greyed out
        for entry in entries {
            menu.addItem(item(entry, target: target, action: action))
        }
        return menu
    }

    static func item(_ entry: MenuEntry, target: AnyObject, action: Selector) -> NSMenuItem {
        if entry.isSeparator {
            return .separator()
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
