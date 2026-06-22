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
// THREE ways to dismiss (so you can NEVER get locked out):
//   1. Local password (break-glass): type it into the on-screen field. Works
//      even if Telegram / network is down. Hash is salted SHA-256, passed via
//      env (MAC_VEIL_PWHASH + MAC_VEIL_SALT), never in argv.
//   2. Telegram `/veil off` → SIGTERM.
//   3. --timeout N auto-dismiss (optional max-duration backstop).
// Last-resort: SSH in and `kill` the process, or Force-Quit.
//
// It is a PRIVACY screen, not a security lock: Force-Quit, SSH kill, or reboot
// all dismiss it. Good against shoulder-surfing, not a determined attacker.
//
// Usage:  mac-veil [--timeout SECONDS] [--message TEXT]
import Cocoa
import CryptoKit

func sha256Hex(_ s: String) -> String {
    SHA256.hash(data: Data(s.utf8)).map { String(format: "%02x", $0) }.joined()
}

let env = ProcessInfo.processInfo.environment
let expectedHash = env["MAC_VEIL_PWHASH"] ?? ""
let salt = env["MAC_VEIL_SALT"] ?? ""

var timeout: Double = 0
var message = "🔒 屏幕已遮挡"

var args = Array(CommandLine.arguments.dropFirst())
var ai = 0
while ai < args.count {
    switch args[ai] {
    case "--timeout":
        if ai + 1 < args.count { timeout = Double(args[ai + 1]) ?? 0; ai += 1 }
    case "--message":
        if ai + 1 < args.count { message = args[ai + 1]; ai += 1 }
    default:
        break
    }
    ai += 1
}

// Handles the local password field: hashes the attempt (salt + input) and
// dismisses on match. Wrong input clears the field and shows a hint.
final class UnlockController: NSObject, NSTextFieldDelegate {
    let expected: String
    let salt: String
    weak var hint: NSTextField?

    init(expected: String, salt: String) {
        self.expected = expected
        self.salt = salt
    }

    func control(_ control: NSControl, textView: NSTextView,
                 doCommandBy commandSelector: Selector) -> Bool {
        guard commandSelector == #selector(NSResponder.insertNewline(_:)),
              let field = control as? NSTextField else { return false }
        if !expected.isEmpty, sha256Hex(salt + field.stringValue) == expected {
            exit(0)
        }
        field.stringValue = ""
        hint?.stringValue = "密码错误，请重试"
        return true
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)  // no Dock icon

let unlock = UnlockController(expected: expectedHash, salt: salt)
let hasPassword = !expectedHash.isEmpty

var windows: [NSWindow] = []
let mainScreen = NSScreen.main
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
    win.ignoresMouseEvents = false
    win.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]

    guard let content = win.contentView else { continue }
    let cx = content.bounds.width / 2
    let cy = content.bounds.height / 2

    let label = NSTextField(labelWithString: message)
    label.textColor = NSColor(white: 0.35, alpha: 1.0)
    label.font = NSFont.systemFont(ofSize: 26)
    label.backgroundColor = .clear
    label.isBezeled = false
    label.isEditable = false
    label.sizeToFit()
    label.frame.origin = NSPoint(x: cx - label.frame.width / 2, y: cy + 40)
    label.autoresizingMask = [.minXMargin, .maxXMargin, .minYMargin, .maxYMargin]
    content.addSubview(label)

    // Password field only on the main screen, only when a password is set.
    if hasPassword, screen == mainScreen {
        let field = NSSecureTextField(frame: NSRect(x: cx - 120, y: cy - 10, width: 240, height: 28))
        field.placeholderString = "输入密码解除"
        field.alignment = .center
        field.delegate = unlock
        field.autoresizingMask = [.minXMargin, .maxXMargin, .minYMargin, .maxYMargin]
        content.addSubview(field)

        let hint = NSTextField(labelWithString: "解除遮挡：输入密码并回车，或在 Telegram 发 /veil off")
        hint.textColor = NSColor(white: 0.3, alpha: 1.0)
        hint.font = NSFont.systemFont(ofSize: 13)
        hint.backgroundColor = .clear
        hint.isBezeled = false
        hint.isEditable = false
        hint.sizeToFit()
        hint.frame.origin = NSPoint(x: cx - hint.frame.width / 2, y: cy - 50)
        hint.autoresizingMask = [.minXMargin, .maxXMargin, .minYMargin, .maxYMargin]
        content.addSubview(hint)
        unlock.hint = hint

        win.makeFirstResponder(field)
    }

    win.makeKeyAndOrderFront(nil)
    windows.append(win)
}
app.activate(ignoringOtherApps: true)

// Telegram `/veil off` sends SIGTERM. Clean exit.
signal(SIGTERM) { _ in exit(0) }
signal(SIGINT) { _ in exit(0) }

// Optional max-duration backstop (also used for safe testing).
if timeout > 0 {
    Timer.scheduledTimer(withTimeInterval: timeout, repeats: false) { _ in exit(0) }
}

app.run()
