import Cocoa
import WebKit

struct ControlStatus: Decodable {
    let connected, mouse, click, paused, access, calibrated, calibration: Bool
    let active_measurement: Int?
    let mode, label: String
}

final class Studio: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var webView: WKWebView!
    var backend: Process?
    var base: URL?
    var terminating = false
    let selfTest = CommandLine.arguments.contains("--self-test")
    let port = CommandLine.arguments.contains("--self-test") ? 18767 : 18765
    var startupTimer: Timer?
    var statusItem: NSStatusItem?
    var statusTimer: Timer?
    var controlStatus: ControlStatus?
    var statusRequestInFlight = false
    var commandInFlight = false
    let statusMenu = NSMenu()
    var statusLine: NSMenuItem!
    var connectionItem: NSMenuItem!
    var mouseItem: NSMenuItem!
    var pauseItem: NSMenuItem!
    var resumeItem: NSMenuItem!
    var clickItem: NSMenuItem!
    var calibrationItem: NSMenuItem!

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
            installStatusMenu()
            let config = WKWebViewConfiguration()
            config.userContentController.add(self, name: "nativeExport")
            webView = WKWebView(frame: .zero, configuration: config)
            webView.navigationDelegate = self
            window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1180, height: 860), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
            window.title = "QRing Studio · 戒指開發與滑鼠控制"
            window.delegate = self
            window.isReleasedWhenClosed = false
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
                self.controlStatus = nil
                self.updateStatusMenu()
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
                URLSession.shared.dataTask(with: self.base!.appendingPathComponent("api/control-status")) { data, response, error in
                    guard error == nil, (response as? HTTPURLResponse)?.statusCode == 200, let data = data,
                          let status = try? JSONDecoder().decode(ControlStatus.self, from: data),
                          !status.connected, !status.mouse, !status.click, status.mode == "disconnected" else { print("STATUS_SELF_TEST_FAILED"); exit(2) }
                    print("BUNDLED_APP_SELF_TEST_OK")
                    self.shutdown { exit(0) }
                }.resume()
            }.resume()
        } else {
            webView.load(URLRequest(url: base!))
            refreshControlStatus()
            let timer = Timer(timeInterval: 0.5, repeats: true) { [weak self] _ in self?.refreshControlStatus() }
            RunLoop.main.add(timer, forMode: .common)
            statusTimer = timer
        }
    }
    func menuItem(_ title: String, action: Selector) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
        item.target = self
        statusMenu.addItem(item)
        return item
    }
    func installStatusMenu() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusMenu.autoenablesItems = false
        statusLine = NSMenuItem(title: "QRing Studio 正在啟動…", action: nil, keyEquivalent: "")
        statusLine.isEnabled = false
        statusMenu.addItem(statusLine)
        statusMenu.addItem(.separator())
        _ = menuItem("顯示 QRing Studio", action: #selector(showWindow))
        calibrationItem = menuItem("開啟五步校正", action: #selector(showCalibration))
        statusMenu.addItem(.separator())
        mouseItem = menuItem("啟用 Mac 游標控制", action: #selector(toggleMouse))
        resumeItem = menuItem("開始／繼續控制", action: #selector(resumeMouse))
        pauseItem = menuItem("立即暫停", action: #selector(pauseMouse))
        clickItem = menuItem("啟用單擊左鍵", action: #selector(toggleClick))
        statusMenu.addItem(.separator())
        connectionItem = menuItem("連接戒指", action: #selector(toggleConnection))
        statusMenu.addItem(.separator())
        _ = menuItem("結束 QRing Studio", action: #selector(quitApp))
        statusItem?.menu = statusMenu
        updateStatusMenu()
    }
    func updateStatusMenu() {
        guard let button = statusItem?.button else { return }
        let s = controlStatus
        let label = s?.label ?? (base == nil ? "啟動中" : "服務離線")
        let symbol: String
        switch s?.mode {
        case "moving", "holding": symbol = "cursorarrow.motionlines"
        case "ready": symbol = "cursorarrow"
        case "paused", "measuring": symbol = "pause.circle"
        case "permission", "stale": symbol = "exclamationmark.triangle"
        case "off": symbol = "cursorarrow.slash"
        default: symbol = "circle.dashed"
        }
        let image = NSImage(systemSymbolName: symbol, accessibilityDescription: "QRing 游標：\(label)") ?? NSImage(systemSymbolName: "cursorarrow", accessibilityDescription: "QRing")
        image?.isTemplate = true
        button.image = image
        button.imagePosition = .imageLeading
        button.title = " \(label)"
        button.toolTip = "QRing Studio · 游標\(label)"
        button.setAccessibilityLabel("QRing Studio · 游標\(label)")
        statusLine.title = "游標狀態：\(label)"
        mouseItem.state = s?.mouse == true ? .on : .off
        clickItem.state = s?.click == true ? .on : .off
        let available = s != nil && !terminating && !commandInFlight
        connectionItem.title = s?.connected == true ? "中斷戒指連線" : "連接戒指"
        connectionItem.isEnabled = available
        mouseItem.isEnabled = available && s?.connected == true && (s?.mouse == true || (s?.access == true && s?.calibrated == true && s?.calibration == false))
        resumeItem.isEnabled = available && s?.mouse == true && s?.connected == true && s?.access == true && s?.paused == true && s?.active_measurement == nil
        pauseItem.isEnabled = available && s?.mouse == true
        clickItem.isEnabled = available && s?.mouse == true && s?.access == true
        calibrationItem.isEnabled = available
        if s?.connected == true && s?.access == false { mouseItem.toolTip = "請在主視窗授權；剛完成授權時請完整重啟 App。" }
        else if s?.calibrated == false { mouseItem.toolTip = "請先完成五步校正並儲存。" }
        else { mouseItem.toolTip = nil }
    }
    func refreshControlStatus() {
        guard let base = base, !terminating, !statusRequestInFlight else { return }
        statusRequestInFlight = true
        var request = URLRequest(url: base.appendingPathComponent("api/control-status"))
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 1
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            let status: ControlStatus?
            if error == nil, (response as? HTTPURLResponse)?.statusCode == 200, let data = data { status = try? JSONDecoder().decode(ControlStatus.self, from: data) }
            else { status = nil }
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.statusRequestInFlight = false
                guard !self.terminating else { return }
                self.controlStatus = status
                self.updateStatusMenu()
            }
        }.resume()
    }
    func command(_ path: String, body: [String: Any] = [:]) {
        guard let base = base, !terminating, !commandInFlight else { return }
        commandInFlight = true
        updateStatusMenu()
        var request = URLRequest(url: base.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        request.timeoutInterval = 60
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            var message = error?.localizedDescription
            if error == nil && (response as? HTTPURLResponse)?.statusCode != 200 {
                let json = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
                message = json?["error"] as? String ?? "操作失敗，請在主視窗查看狀態。"
            }
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.commandInFlight = false
                guard !self.terminating else { return }
                self.updateStatusMenu()
                self.refreshControlStatus()
                if let message = message { self.showWindow(); self.showError(message) }
            }
        }.resume()
    }
    @objc func showWindow() { window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
    @objc func showCalibration() { showWindow(); webView.evaluateJavaScript("switchTab('calibration')", completionHandler: nil) }
    @objc func toggleMouse() { guard let s = controlStatus else { return }; command("api/options", body: ["mouse": !s.mouse]) }
    @objc func toggleClick() { guard let s = controlStatus else { return }; command("api/options", body: ["click": !s.click]) }
    @objc func pauseMouse() { command("api/pause") }
    @objc func resumeMouse() { command("api/resume") }
    @objc func toggleConnection() { guard let s = controlStatus else { return }; command(s.connected ? "api/disconnect" : "api/connect") }
    @objc func quitApp() { NSApp.terminate(nil) }
    func windowShouldClose(_ sender: NSWindow) -> Bool { sender.orderOut(nil); return false }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { showWindow(); return true }
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
        statusTimer?.invalidate()
        updateStatusMenu()
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
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
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
