import AppKit

/// Projects › Arrange…: drag projects into the order the menu uses (both tabs) and tick the ones to show.
/// Menus cannot be reordered by dragging, so this is a small window.
final class ArrangeWindowController: NSWindowController, NSTableViewDataSource, NSTableViewDelegate {
    private static let rowType = NSPasteboard.PasteboardType("com.ha-ptt0601.githubbar.project-row")
    private var projects: [(name: String, shown: Bool)]
    private let table = NSTableView()
    /// (order, hidden) on Save; (nil, nil) on Reset order.
    var onSave: (([String]?, [String]?) -> Void)?

    init(projects: [(name: String, shown: Bool)]) {
        self.projects = projects
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 360, height: 420),
                              styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Arrange projects"
        window.isReleasedWhenClosed = false
        super.init(window: window)
        build(in: window)
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    private func build(in window: NSWindow) {
        let content = NSView(frame: window.contentRect(forFrameRect: window.frame))
        let hint = NSTextField(labelWithString: "Drag to reorder (both tabs). Untick to hide a project.")
        hint.font = .systemFont(ofSize: 12)
        hint.textColor = .secondaryLabelColor
        hint.frame = NSRect(x: 16, y: 388, width: 328, height: 18)

        let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("project"))
        column.width = 300
        table.addTableColumn(column)
        table.headerView = nil
        table.rowHeight = 24
        table.dataSource = self
        table.delegate = self
        table.registerForDraggedTypes([Self.rowType])
        table.draggingDestinationFeedbackStyle = .gap
        let scroll = NSScrollView(frame: NSRect(x: 16, y: 56, width: 328, height: 324))
        scroll.documentView = table
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder

        let reset = NSButton(title: "Reset order", target: self, action: #selector(resetOrder))
        reset.frame = NSRect(x: 12, y: 12, width: 110, height: 32)
        let cancel = NSButton(title: "Cancel", target: self, action: #selector(cancel))
        cancel.frame = NSRect(x: 172, y: 12, width: 84, height: 32)
        cancel.keyEquivalent = "\u{1b}"
        let save = NSButton(title: "Save", target: self, action: #selector(save))
        save.frame = NSRect(x: 260, y: 12, width: 88, height: 32)
        save.keyEquivalent = "\r"
        [hint, scroll, reset, cancel, save].forEach(content.addSubview)
        window.contentView = content
    }

    func numberOfRows(in tableView: NSTableView) -> Int { projects.count }

    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        let check = NSButton(checkboxWithTitle: "≡   " + projects[row].name, target: self, action: #selector(toggle(_:)))
        check.state = projects[row].shown ? .on : .off
        check.tag = row
        return check
    }

    @objc private func toggle(_ sender: NSButton) {
        guard sender.tag < projects.count else { return }
        projects[sender.tag].shown = sender.state == .on
    }

    func tableView(_ tableView: NSTableView, pasteboardWriterForRow row: Int) -> NSPasteboardWriting? {
        let item = NSPasteboardItem()
        item.setString(String(row), forType: Self.rowType)
        return item
    }

    func tableView(_ tableView: NSTableView, validateDrop info: NSDraggingInfo, proposedRow row: Int,
                   proposedDropOperation dropOperation: NSTableView.DropOperation) -> NSDragOperation {
        dropOperation == .above ? .move : []
    }

    func tableView(_ tableView: NSTableView, acceptDrop info: NSDraggingInfo, row: Int,
                   dropOperation: NSTableView.DropOperation) -> Bool {
        guard let text = info.draggingPasteboard.pasteboardItems?.first?.string(forType: Self.rowType),
              let from = Int(text), from < projects.count else { return false }
        let moved = projects.remove(at: from)
        let to = from < row ? row - 1 : row
        projects.insert(moved, at: to)
        tableView.reloadData()
        tableView.selectRowIndexes(IndexSet(integer: to), byExtendingSelection: false)
        return true
    }

    @objc private func save() {
        onSave?(projects.map(\.name), projects.filter { !$0.shown }.map(\.name))
        close()
    }

    @objc private func resetOrder() {
        onSave?(nil, projects.filter { !$0.shown }.map(\.name))
        close()
    }

    @objc private func cancel() { close() }
}
