// lockmac overlay — a privacy veil: a black, top-most overlay covering every
// display so onlookers can't see the screen, WITHOUT locking the Mac.
//
// Dismiss (so you can NEVER get locked out):
//   1. Local password (salted SHA-256, via env LOCKMAC_PWHASH/LOCKMAC_SALT).
//      If LOCKMAC_TOTP_SECRET is set, a second factor (6-digit TOTP) is ALSO
//      required — two-step unlock. TOTP matches the Python side (RFC 6238).
//   2. SIGTERM (`lockmac unveil` / Telegram).
//   3. --timeout N auto-dismiss.
// Last resort: ssh in and `kill`, or Force-Quit.
//
// Privacy screen, not a security lock: Force-Quit / ssh kill / reboot dismiss it.
import Cocoa
import CryptoKit

func sha256Hex(_ s: String) -> String {
    SHA256.hash(data: Data(s.utf8)).map { String(format: "%02x", $0) }.joined()
}

// ── TOTP (RFC 6238, HMAC-SHA1, 30s, 6 digits) — must match lockmac/totp.py ──
func base32Decode(_ s: String) -> Data? {
    let alphabet = Array("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
    var bits = 0, value = 0
    var out = [UInt8]()
    for ch in s.uppercased() where ch != "=" {
        guard let idx = alphabet.firstIndex(of: ch) else { return nil }
        value = (value << 5) | idx
        bits += 5
        if bits >= 8 { out.append(UInt8((value >> (bits - 8)) & 0xFF)); bits -= 8 }
    }
    return Data(out)
}

func hotp(_ key: Data, _ counter: UInt64) -> String {
    var be = counter.bigEndian
    let msg = withUnsafeBytes(of: &be) { Data($0) }
    let mac = HMAC<Insecure.SHA1>.authenticationCode(for: msg, using: SymmetricKey(data: key))
    let h = Array(mac)
    let o = Int(h[h.count - 1] & 0x0F)
    let bin = (UInt32(h[o] & 0x7F) << 24) | (UInt32(h[o + 1]) << 16)
            | (UInt32(h[o + 2]) << 8) | UInt32(h[o + 3])
    return String(format: "%06u", bin % 1_000_000)
}

func verifyTOTP(_ secretB32: String, _ code: String, window: Int = 1) -> Bool {
    let trimmed = code.trimmingCharacters(in: .whitespaces)
    if secretB32.isEmpty || trimmed.isEmpty { return false }
    guard let key = base32Decode(secretB32) else { return false }
    let now = Int64(Date().timeIntervalSince1970) / 30
    for w in -window...window where hotp(key, UInt64(now + Int64(w))) == trimmed {
        return true
    }
    return false
}

let env = ProcessInfo.processInfo.environment
let expectedHash = env["LOCKMAC_PWHASH"] ?? ""
let salt = env["LOCKMAC_SALT"] ?? ""
let totpSecret = env["LOCKMAC_TOTP_SECRET"] ?? ""

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

// Verifies password (+ TOTP if configured). Both fields' Return triggers a try.
final class UnlockController: NSObject, NSTextFieldDelegate {
    let expected: String
    let salt: String
    let totpSecret: String
    weak var pwField: NSSecureTextField?
    weak var codeField: NSTextField?
    weak var hint: NSTextField?

    init(expected: String, salt: String, totpSecret: String) {
        self.expected = expected
        self.salt = salt
        self.totpSecret = totpSecret
    }

    func tryUnlock() {
        let pw = pwField?.stringValue ?? ""
        let pwOK = !expected.isEmpty && sha256Hex(salt + pw) == expected
        let codeOK = totpSecret.isEmpty || verifyTOTP(totpSecret, codeField?.stringValue ?? "")
        if pwOK && codeOK { exit(0) }
        if !pwOK {
            hint?.stringValue = "密码错误，请重试"
        } else {
            hint?.stringValue = "验证码错误，请重试"
        }
        pwField?.stringValue = ""
        codeField?.stringValue = ""
    }

    func control(_ control: NSControl, textView: NSTextView,
                 doCommandBy commandSelector: Selector) -> Bool {
        guard commandSelector == #selector(NSResponder.insertNewline(_:)) else { return false }
        tryUnlock()
        return true
    }
}

// Borderless windows are canBecomeKey=false by default → no keystrokes. Override.
final class VeilWindow: NSWindow {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)  // reliable keyboard focus for the unlock fields

let hasPassword = !expectedHash.isEmpty
let hasTotp = !totpSecret.isEmpty
let unlock = UnlockController(expected: expectedHash, salt: salt, totpSecret: totpSecret)

var windows: [NSWindow] = []
var mainWin: VeilWindow?
var firstField: NSTextField?
let mainScreen = NSScreen.main
for screen in NSScreen.screens {
    let win = VeilWindow(
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
    label.frame.origin = NSPoint(x: cx - label.frame.width / 2, y: cy + 60)
    label.autoresizingMask = [.minXMargin, .maxXMargin, .minYMargin, .maxYMargin]
    content.addSubview(label)

    // Unlock fields only on the main screen, only when a password is set.
    if hasPassword, screen == mainScreen {
        let pw = NSSecureTextField(frame: NSRect(x: cx - 120, y: cy + 16, width: 240, height: 28))
        pw.placeholderString = "输入密码"
        pw.alignment = .center
        pw.delegate = unlock
        pw.autoresizingMask = [.minXMargin, .maxXMargin, .minYMargin, .maxYMargin]
        content.addSubview(pw)
        unlock.pwField = pw
        firstField = pw

        if hasTotp {
            let code = NSTextField(frame: NSRect(x: cx - 120, y: cy - 20, width: 240, height: 28))
            code.placeholderString = "6 位验证码"
            code.alignment = .center
            code.delegate = unlock
            code.autoresizingMask = [.minXMargin, .maxXMargin, .minYMargin, .maxYMargin]
            content.addSubview(code)
            unlock.codeField = code
        }

        let tip = hasTotp ? "解除：输入密码 + 6位验证码并回车，或 Telegram /unveil <码>"
                          : "解除：输入密码并回车，或 Telegram /unveil"
        let hint = NSTextField(labelWithString: tip)
        hint.textColor = NSColor(white: 0.3, alpha: 1.0)
        hint.font = NSFont.systemFont(ofSize: 13)
        hint.backgroundColor = .clear
        hint.isBezeled = false
        hint.isEditable = false
        hint.sizeToFit()
        hint.frame.origin = NSPoint(x: cx - hint.frame.width / 2, y: cy - 64)
        hint.autoresizingMask = [.minXMargin, .maxXMargin, .minYMargin, .maxYMargin]
        content.addSubview(hint)
        unlock.hint = hint

        win.initialFirstResponder = pw
        mainWin = win
    }

    win.makeKeyAndOrderFront(nil)
    windows.append(win)
}
app.activate(ignoringOtherApps: true)

if let w = mainWin {
    w.makeKeyAndOrderFront(nil)
    if let f = firstField { w.makeFirstResponder(f) }
}

signal(SIGTERM) { _ in exit(0) }
signal(SIGINT) { _ in exit(0) }

if timeout > 0 {
    Timer.scheduledTimer(withTimeInterval: timeout, repeats: false) { _ in exit(0) }
}

app.run()
