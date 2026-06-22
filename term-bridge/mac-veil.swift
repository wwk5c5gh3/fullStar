// mac-veil.swift — a privacy veil: a black, top-most overlay covering every
// display so onlookers can't see the screen, WITHOUT locking the Mac.
//
// Why this works with the rest of mob-remote:
//   • Remote injection uses iTerm `write text` (no keyboard focus / no display
//     dependency), so it keeps working while the veil is up.
//   • Screenshots use `screencapture -l <windowID>` which grabs a specific
//     window's buffer regardless of what covers it — so you still see the real
//     content on your phone.
//   • The veil uses CGShieldingWindowLevel (above normal windows), so even when
//     iTerm is activated by an inject it never rises above the veil locally.
//
// It is a PRIVACY screen, not a security lock: Force-Quit (Cmd-Opt-Esc), SSH
// `kill`, or a reboot all dismiss it. Good against shoulder-surfing, not a
// determined person at the keyboard.
//
// Usage:  mac-veil [--timeout SECONDS] [--message TEXT]
//   --timeout 0  = stay until killed (SIGTERM); /mac veil off kills it.
//   --timeout N  = auto-dismiss after N seconds (used for safe testing).
import Cocoa

var timeout: Double = 0
var message = "🔒 屏幕已遮挡 · 通过 Telegram 解除（/mac veil off）"

var args = Array(CommandLine.arguments.dropFirst())
var i = 0
while i < args.count {
    switch args[i] {
    case "--timeout":
        if i + 1 < args.count { timeout = Double(args[i + 1]) ?? 0; i += 1 }
    case "--message":
        if i + 1 < args.count { message = args[i + 1]; i += 1 }
    default:
        break
    }
    i += 1
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)  // no Dock icon

var windows: [NSWindow] = []
for screen in NSScreen.screens {
    let win = NSWindow(
        contentRect: screen.frame,
        styleMask: .borderless,
        backing: .buffered,
        defer: false,
        screen: screen
    )
    win.level = NSWindow.Level(rawValue: Int(CGShieldingWindowLevel()))
    win.backgroundColor = .black
    win.isOpaque = true
    win.hasShadow = false
    win.ignoresMouseEvents = false  // swallow clicks so nothing leaks through
    win.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]

    let label = NSTextField(labelWithString: message)
    label.textColor = NSColor(white: 0.35, alpha: 1.0)
    label.font = NSFont.systemFont(ofSize: 26)
    label.backgroundColor = .clear
    label.isBezeled = false
    label.isEditable = false
    label.sizeToFit()
    if let content = win.contentView {
        var f = label.frame
        f.origin = NSPoint(
            x: (content.bounds.width - f.width) / 2,
            y: (content.bounds.height - f.height) / 2
        )
        label.frame = f
        label.autoresizingMask = [.minXMargin, .maxXMargin, .minYMargin, .maxYMargin]
        content.addSubview(label)
    }
    win.makeKeyAndOrderFront(nil)
    windows.append(win)
}
app.activate(ignoringOtherApps: true)

// Clean exit on SIGTERM (/mac veil off sends this).
signal(SIGTERM) { _ in exit(0) }
signal(SIGINT) { _ in exit(0) }

// Timer is serviced by NSApplication's runloop (asyncAfter is not, reliably).
if timeout > 0 {
    Timer.scheduledTimer(withTimeInterval: timeout, repeats: false) { _ in exit(0) }
}

app.run()
