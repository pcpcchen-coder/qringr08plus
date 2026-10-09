import Cocoa
import WebKit

final class Studio: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var webView: WKWebView!
    var backend: Process?
    var base: URL?
    var terminating = false
    let selfTest = CommandLine.arguments.contains("--self-test")
    let port = CommandLine.arguments.contains("--self-test") ? 18767 : 18765
    var startupTimer: Timer?

    func applicationDidFinishLaunching(_ notification: Notification) {
        if !selfTest {
            let menu = NSMenu()
            let appMenu = NSMenu()
            appMenu.addItem(withTitle: "結束 QRing Studio", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
            let root = NSMenuItem(); root.submenu = appMenu; menu.addItem(root)
            let edit = NSMenu(title: "編輯")
            edit.addItem(withTitle: "複製", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
            edit.addItem(withTitle: "貼上", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
            edit.addItem(withTitle: "全選", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
            let editItem = NSMenuItem(title: "編輯", action: nil, keyEquivalent: ""); editItem.submenu = edit; menu.addItem(editItem)
            NSApp.mainMenu = menu
            let config = WKWebViewConfiguration()
            config.userContentController.add(self, name: "nativeExport")
            webView = WKWebView(frame: .zero, configuration: config)
            webView.navigationDelegate = self
            window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1180, height: 860), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
            window.title = "QRing Studio · 戒指開發與滑鼠控制"
            window.minSize = NSSize(width: 850, height: 650)
            window.contentView = webView; window.center(); window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            webView.loadHTMLString("<html><body style='background:#0a101c;color:#42dfb7;font:24px system-ui;padding:60px'>QRing Studio 正在啟動…</body></html>", baseURL: nil)
        }
        launchBackend()
    }
    func launchBackend() {
        let bundle = Bundle.main.bundleURL
        let resources = bundle.appendingPathComponent("Contents/Resources")
        let version = bundle.appendingPathComponent("Contents/Frameworks/Python3.framework/Versions/3.9")
        let process = Process()
        process.executableURL = version.appendingPathComponent("bin/python3.9")
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent(selfTest ? "QRing Studio SelfTest" : "QRing Studio")
        process.arguments = ["-u", resources.appendingPathComponent("app/server.py").path, "--port", String(port), "--data-dir", support.path]
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONHOME"] = version.path
        environment["PYTHONPATH"] = resources.appendingPathComponent("app").path + ":" + resources.appendingPathComponent("site-packages").path
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment.removeValue(forKey: "VIRTUAL_ENV")
        process.environment = environment
        let output = Pipe(); process.standardOutput = output
        let error = Pipe(); process.standardError = error
        output.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            let string = String(data: data, encoding: .utf8) ?? ""
            if self.selfTest { FileHandle.standardOutput.write(data) }
            if string.contains("READY http://127.0.0.1:") {
                DispatchQueue.main.async { self.ready() }
            }
        }
        error.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            if self.selfTest { FileHandle.standardError.write(data) }
        }
        process.terminationHandler = { p in
            DispatchQueue.main.async {
                if self.terminating { return }
                self.startupTimer?.invalidate()
                if self.selfTest { exit(2) }
                self.webView.loadHTMLString("<html><body style='background:#0a101c;color:#edf2fa;font:18px system-ui;padding:40px'>服務無法啟動或已結束。請關閉另一個 QRing Studio，再重新開啟。系統代碼 \(p.terminationStatus)。</body></html>", baseURL: nil)
            }
        }
        backend = process
        do { try process.run() }
        catch { if selfTest { print(error); exit(2) }; showError("無法啟動內建服務：\(error.localizedDescription)") }
        startupTimer = Timer.scheduledTimer(withTimeInterval: 20, repeats: false) { _ in
            if self.base == nil {
                if self.selfTest { print("STARTUP_TIMEOUT"); self.backend?.terminate(); exit(2) }
                self.showError("服務啟動逾時。請確認沒有另一個 QRing Studio 正在執行。")
            }
        }
    }
    func ready() {
        guard base == nil else { return }
        startupTimer?.invalidate()
        base = URL(string: "http://127.0.0.1:\(port)/")!
        if selfTest {
            URLSession.shared.dataTask(with: base!.appendingPathComponent("api/state")) { data, _, error in
                guard error == nil, let data = data, let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any], json["options"] != nil else { print("SELF_TEST_FAILED"); exit(2) }
                print("BUNDLED_APP_SELF_TEST_OK")
                self.shutdown { exit(0) }
            }.resume()
        } else { webView.load(URLRequest(url: base!)) }
    }
    func showError(_ text: String) { let alert = NSAlert(); alert.messageText = "QRing Studio"; alert.informativeText = text; alert.runModal() }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "nativeExport", let base = base else { return }
        let panel = NSSavePanel(); panel.nameFieldStringValue = "qring-session.jsonl"
        panel.beginSheetModal(for: window) { response in
            guard response == .OK, let destination = panel.url else { return }
            URLSession.shared.dataTask(with: base.appendingPathComponent("api/export")) { data, _, error in
                guard let data = data, error == nil else { return }
                do { try data.write(to: destination, options: .atomic) }
                catch { DispatchQueue.main.async { self.showError(error.localizedDescription) } }
            }.resume()
        }
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if url.scheme == "about" || (url.host == "127.0.0.1" && url.port == port) { decisionHandler(.allow) }
        else { decisionHandler(.cancel) }
    }
    func shutdown(_ completion: @escaping () -> Void) {
        terminating = true
        guard let base = base else { backend?.terminate(); completion(); return }
        var request = URLRequest(url: base.appendingPathComponent("api/shutdown"))
        request.httpMethod = "POST"; request.setValue("application/json", forHTTPHeaderField: "Content-Type"); request.httpBody = Data("{}".utf8); request.timeoutInterval = 60
        URLSession.shared.dataTask(with: request) { _, _, _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                if self.backend?.isRunning == true { self.backend?.terminate() }
                completion()
            }
        }.resume()
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if terminating { return .terminateNow }
        shutdown { NSApp.reply(toApplicationShouldTerminate: true) }
        return .terminateLater
    }
}

let app = NSApplication.shared
let studio = Studio()
app.delegate = studio
app.setActivationPolicy(studio.selfTest ? .prohibited : .regular)
app.run()
