import Foundation
import GitHubBarCore

var failures = 0
var total = 0

func check(_ condition: Bool, _ message: String, line: Int = #line) {
    total += 1
    if !condition {
        failures += 1
        print("FAIL line \(line): \(message)")
    }
}

// Title, separators and params.
let basic = MenuParser.parse("""
11 🔴1 | templateImage=QUJD==
---
Refresh now | sfimage=arrow.clockwise bash=/a/chip terminal=false param1=swiftbar param2=--force refresh=true
---
API · 15 PRs | size=11 color=#8E8E93
""")
check(basic.title.text == "11 🔴1", "title text: \(basic.title.text)")
check(basic.title.params["templateImage"] == "QUJD==", "value keeps '=' padding")
check(basic.items.count == 3, "items incl. separators: \(basic.items.count)")
check(basic.items[0].isSeparator == false && basic.items[0].text == "Refresh now", "first item")
check(basic.items[0].params["param2"] == "--force" && basic.items[0].params["refresh"] == "true", "params")
check(basic.items[1].isSeparator, "separator")
check(basic.items[2].params["color"] == "#8E8E93", "color")

// Nesting, submenu separators and quoted values.
let nested = MenuParser.parse("""
x
---
#2079  Re-review  title | tooltip="Full review · running 3m" font=Menlo size=12
--api#2079 | disabled=true
-----
--Run "Full review" | bash="/Users/a b/chip.sh" param1=run param2=api#2079
--Next 12 ›  (13–24 of 25)
----#3 | href=https://github.com/o/r/pull/3?x=1
Settings
""")
check(nested.items.count == 2, "two top-level items: \(nested.items.count)")
let pr = nested.items[0]
check(pr.params["tooltip"] == "Full review · running 3m", "quoted tooltip: \(pr.params["tooltip"] ?? "nil")")
check(pr.children.count == 4, "pr children: \(pr.children.count)")
check(pr.children[1].isSeparator, "submenu separator")
check(pr.children[2].params["bash"] == "/Users/a b/chip.sh", "quoted path with space")
check(pr.children[2].text == "Run \"Full review\"", "text keeps quotes")
check(pr.children[3].children.first?.params["href"] == "https://github.com/o/r/pull/3?x=1", "href with '='")
check(nested.items[1].text == "Settings", "back to depth 0")

// Text without params and leading zero-width space.
let plain = MenuParser.parse("t\n---\n\u{200B}-1 thing\nno params here")
check(plain.items[0].text == "\u{200B}-1 thing", "zero-width escaped dash kept")
check(plain.items[1].params.isEmpty, "no params")

// Real chip output, if a fixture path is given.
if CommandLine.arguments.count > 1, let real = try? String(contentsOfFile: CommandLine.arguments[1]) {
    let menu = MenuParser.parse(real)
    check(!menu.items.isEmpty, "real menu has items")
    let lines = real.split(separator: "\n").count
    check(menu.lineCount == lines, "every real line consumed: \(menu.lineCount) of \(lines)")
}

print(failures == 0 ? "OK \(total) checks" : "FAILED \(failures) of \(total)")
exit(failures == 0 ? 0 : 1)
