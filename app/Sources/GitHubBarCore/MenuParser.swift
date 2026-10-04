import Foundation

/// One line of SwiftBar-format menu text: an item (text + params + submenu) or a separator.
public struct MenuEntry: Equatable {
    public var text: String
    public var params: [String: String]
    public var children: [MenuEntry]
    public var isSeparator: Bool

    public init(text: String = "", params: [String: String] = [:], children: [MenuEntry] = [],
                isSeparator: Bool = false) {
        self.text = text
        self.params = params
        self.children = children
        self.isSeparator = isSeparator
    }
}

/// The whole menu: the menu bar title and the dropdown items.
public struct ParsedMenu: Equatable {
    public var title: MenuEntry
    public var items: [MenuEntry]
    /// Number of input lines consumed (title block + items), used to check nothing is dropped.
    public var lineCount: Int
    /// Title-block lines marked `notify=true`: notifications for GitHubBar to post (text + click action).
    public var notifications: [MenuEntry] = []
}

/// Parses the subset of the SwiftBar plugin format that `chip swiftbar` prints:
/// the first line is the title; `---` ends the title block and separates items;
/// a `--` prefix per level nests items; `text | key=value key="value with spaces"`.
/// Later title-block lines with `notify=true` are notifications, not titles.
public enum MenuParser {
    public static func parse(_ text: String) -> ParsedMenu {
        let lines = text.split(separator: "\n", omittingEmptySubsequences: true).map(String.init)
        var title = MenuEntry()
        var index = 0
        var titleSeen = false
        var notifications: [MenuEntry] = []
        while index < lines.count, lines[index] != "---" {
            let line = entry(from: lines[index])
            if line.params["notify"] == "true" {
                notifications.append(line)
            } else if !titleSeen {
                title = line
                titleSeen = true
            }
            index += 1
        }
        index += 1  // the `---` that ends the title block

        // Build the tree with a stack of open parents, one per depth.
        var root: [MenuEntry] = []
        var stack: [[MenuEntry]] = []  // stack[d] = children collected so far at depth d+1
        var consumed = min(index, lines.count)

        func closeLevels(to depth: Int) {
            while stack.count > depth {
                let children = stack.removeLast()
                if stack.isEmpty {
                    root[root.count - 1].children = children
                } else {
                    stack[stack.count - 1][stack[stack.count - 1].count - 1].children = children
                }
            }
        }

        func append(_ item: MenuEntry, depth: Int) {
            if depth == 0 {
                root.append(item)
            } else {
                stack[depth - 1].append(item)
            }
        }

        while index < lines.count {
            let (depth, rest) = splitDepth(lines[index])
            index += 1
            consumed += 1
            // A deeper item needs a parent at the previous depth; ignore impossible jumps.
            let allowed = depth == 0 ? 0 : min(depth, stack.count + 1)
            if allowed > stack.count {
                if allowed == 1 && root.isEmpty { continue }
                if allowed > 1 && (stack.last?.isEmpty ?? true) { continue }
                stack.append([])
            }
            closeLevels(to: allowed)
            append(rest == "---" ? MenuEntry(isSeparator: true) : entry(from: rest), depth: allowed)
        }
        closeLevels(to: 0)
        return ParsedMenu(title: title, items: root, lineCount: consumed, notifications: notifications)
    }

    /// `----x` → (2, "x"); `-----` → (1, "---"); a line that is exactly `---` stays a top separator.
    static func splitDepth(_ line: String) -> (Int, String) {
        var rest = Substring(line)
        var depth = 0
        while rest.hasPrefix("--") && rest != "---" {
            rest = rest.dropFirst(2)
            depth += 1
        }
        return (depth, String(rest))
    }

    static func entry(from line: String) -> MenuEntry {
        guard let bar = line.range(of: " | ") else {
            return MenuEntry(text: line)
        }
        return MenuEntry(text: String(line[..<bar.lowerBound]), params: parseParams(String(line[bar.upperBound...])))
    }

    /// `a=1 b="x y" c=z==` → ["a": "1", "b": "x y", "c": "z=="]; only the first `=` splits key and value.
    public static func parseParams(_ text: String) -> [String: String] {
        var params: [String: String] = [:]
        var chars = Array(text)
        var i = 0
        while i < chars.count {
            while i < chars.count && chars[i] == " " { i += 1 }
            let keyStart = i
            while i < chars.count && chars[i] != "=" && chars[i] != " " { i += 1 }
            let key = String(chars[keyStart..<i])
            guard i < chars.count, chars[i] == "=" else { continue }
            i += 1
            var value = ""
            if i < chars.count && chars[i] == "\"" {
                i += 1
                while i < chars.count && chars[i] != "\"" { value.append(chars[i]); i += 1 }
                i += 1
            } else {
                while i < chars.count && chars[i] != " " { value.append(chars[i]); i += 1 }
            }
            if !key.isEmpty { params[key] = value }
        }
        chars.removeAll()
        return params
    }
}
