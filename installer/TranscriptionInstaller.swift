#!/usr/bin/env swift
// TranscriptionInstaller — Native macOS installer with progress UI
// Compiles with: swiftc -o TranscriptionInstaller TranscriptionInstaller.swift -framework Cocoa

import Cocoa

class InstallerWindow: NSWindow {
    let statusLabel = NSTextField(labelWithString: "Redo att installera")
    let detailLabel = NSTextField(labelWithString: "Klicka Installera för att börja.")
    let progressBar = NSProgressIndicator()
    let installButton = NSButton(title: "Installera", target: nil, action: nil)
    let quitButton = NSButton(title: "Avbryt", target: nil, action: nil)
    var installTask: Process?
    var scriptPath: String = ""
    var pendingLines: [String] = []
    var displayTimer: Timer?
    var isProcessComplete = false
    var processExitStatus: Int32 = 0

    init() {
        let rect = NSRect(x: 0, y: 0, width: 520, height: 340)
        super.init(contentRect: rect, styleMask: [.titled, .closable], backing: .buffered, defer: false)
        self.title = "Tala™ — Installation"
        self.center()
        self.isReleasedWhenClosed = false

        let contentView = NSView(frame: rect)
        self.contentView = contentView

        // Icon/title area
        // App icon
        let iconView = NSImageView(frame: NSRect(x: 30, y: 255, width: 50, height: 50))
        if let iconPath = Bundle.main.path(forResource: "AppIcon", ofType: "icns") {
            iconView.image = NSImage(contentsOfFile: iconPath)
        }
        contentView.addSubview(iconView)

        let titleLabel = NSTextField(labelWithString: "Tala™")
        titleLabel.font = NSFont.boldSystemFont(ofSize: 26)
        titleLabel.frame = NSRect(x: 88, y: 270, width: 400, height: 30)
        contentView.addSubview(titleLabel)

        let subtitleLabel = NSTextField(labelWithString: "Automatisk transkribering av dina Voice Memos")
        subtitleLabel.font = NSFont.systemFont(ofSize: 13)
        subtitleLabel.textColor = .secondaryLabelColor
        subtitleLabel.frame = NSRect(x: 88, y: 248, width: 400, height: 20)
        contentView.addSubview(subtitleLabel)

        // Status
        statusLabel.font = NSFont.systemFont(ofSize: 14, weight: .medium)
        statusLabel.frame = NSRect(x: 30, y: 200, width: 460, height: 20)
        contentView.addSubview(statusLabel)

        detailLabel.font = NSFont.systemFont(ofSize: 12)
        detailLabel.textColor = .secondaryLabelColor
        detailLabel.frame = NSRect(x: 30, y: 170, width: 460, height: 25)
        detailLabel.maximumNumberOfLines = 2
        detailLabel.lineBreakMode = .byTruncatingMiddle
        detailLabel.cell?.truncatesLastVisibleLine = true
        contentView.addSubview(detailLabel)

        // Progress bar
        progressBar.frame = NSRect(x: 30, y: 140, width: 460, height: 20)
        progressBar.isIndeterminate = false
        progressBar.minValue = 0
        progressBar.maxValue = 100
        progressBar.doubleValue = 0
        progressBar.isHidden = true
        contentView.addSubview(progressBar)

        // Buttons
        installButton.frame = NSRect(x: 390, y: 20, width: 100, height: 32)
        installButton.bezelStyle = .rounded
        installButton.keyEquivalent = "\r"
        installButton.target = self
        installButton.action = #selector(startInstall)
        contentView.addSubview(installButton)

        quitButton.frame = NSRect(x: 280, y: 20, width: 100, height: 32)
        quitButton.bezelStyle = .rounded
        quitButton.target = self
        quitButton.action = #selector(quitApp)
        contentView.addSubview(quitButton)

        // Steps info
        let stepsText = """
        Installationen gör följande:
        • Installerar Homebrew (pakethanterare)
        • Installerar ffmpeg och whisper (AI-motor)
        • Laddar ner AI-modell (~547 MB)
        • Ställer in autostart
        """
        let stepsLabel = NSTextField(labelWithString: stepsText)
        stepsLabel.font = NSFont.systemFont(ofSize: 11)
        stepsLabel.textColor = .tertiaryLabelColor
        stepsLabel.frame = NSRect(x: 30, y: 60, width: 460, height: 65)
        stepsLabel.maximumNumberOfLines = 5
        contentView.addSubview(stepsLabel)

        let copyrightLabel = NSTextField(labelWithString: "Powered by AI Empower Labs \u{00A9} 2026")
        copyrightLabel.font = NSFont.systemFont(ofSize: 10)
        copyrightLabel.textColor = .quaternaryLabelColor
        copyrightLabel.frame = NSRect(x: 30, y: 28, width: 240, height: 16)
        contentView.addSubview(copyrightLabel)
    }

    @objc func quitApp() {
        installTask?.terminate()
        NSApp.terminate(nil)
    }

    @objc func startInstall() {
        installButton.isEnabled = false
        progressBar.isHidden = false
        progressBar.isIndeterminate = true
        progressBar.startAnimation(nil)

        // Find install.sh inside app bundle Resources (immune to App Translocation)
        if let resourcePath = Bundle.main.resourcePath {
            scriptPath = "\(resourcePath)/Tala/install.sh"
        } else {
            // Fallback: relative to app bundle (for DMG without embedding)
            let appPath = Bundle.main.bundlePath
            let dmgRoot = (appPath as NSString).deletingLastPathComponent
            scriptPath = "\(dmgRoot)/Tala/install.sh"
        }

        // Check script exists
        if !FileManager.default.fileExists(atPath: scriptPath) {
            statusLabel.stringValue = "Fel: Kunde inte hitta installationsfilen"
            detailLabel.stringValue = "Se till att du kör installern från DMG-filen."
            progressBar.isHidden = true
            installButton.isEnabled = true
            return
        }

        statusLabel.stringValue = "Installerar..."
        detailLabel.stringValue = "Detta kan ta några minuter. Stäng inte det här fönstret."

        // Run install.sh in background
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            self?.runInstallScript()
        }
    }

    func runInstallScript() {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/bin/bash")
        task.arguments = [scriptPath]

        // Set up environment with Homebrew paths
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + (env["PATH"] ?? "/usr/bin:/bin")
        env["HOMEBREW_NO_AUTO_UPDATE"] = "1"
        task.environment = env

        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = pipe
        installTask = task

        let handle = pipe.fileHandleForReading
        handle.readabilityHandler = { [weak self] fileHandle in
            let data = fileHandle.availableData
            if data.isEmpty { return }
            if let text = String(data: data, encoding: .utf8) {
                let lines = text.components(separatedBy: .newlines).filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
                DispatchQueue.main.async {
                    self?.pendingLines.append(contentsOf: lines)
                    self?.startDisplayTimerIfNeeded()
                }
            }
        }

        do {
            try task.run()
            task.waitUntilExit()

            DispatchQueue.main.async { [weak self] in
                self?.isProcessComplete = true
                self?.processExitStatus = task.terminationStatus
                // If no pending lines, finish now; otherwise timer will finish
                if self?.pendingLines.isEmpty == true && self?.displayTimer == nil {
                    if task.terminationStatus == 0 {
                        self?.installComplete()
                    } else {
                        self?.installFailed()
                    }
                }
            }
        } catch {
            DispatchQueue.main.async { [weak self] in
                self?.statusLabel.stringValue = "Fel vid installation"
                self?.detailLabel.stringValue = error.localizedDescription
                self?.progressBar.isHidden = true
                self?.installButton.isEnabled = true
            }
        }
    }

    func startDisplayTimerIfNeeded() {
        guard displayTimer == nil else { return }
        displayTimer = Timer.scheduledTimer(withTimeInterval: 0.4, repeats: true) { [weak self] timer in
            guard let self = self else { timer.invalidate(); return }
            if !self.pendingLines.isEmpty {
                let line = self.pendingLines.removeFirst()
                self.processLine(line)
            }
            if self.pendingLines.isEmpty && self.isProcessComplete {
                timer.invalidate()
                self.displayTimer = nil
                if self.processExitStatus == 0 {
                    // Small delay before showing completion
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                        self.installComplete()
                    }
                } else {
                    self.installFailed()
                }
            }
        }
    }

    func processLine(_ line: String) {
            let lower = line.lowercased().trimmingCharacters(in: .whitespaces)
            if lower.isEmpty { return }

            progressBar.isIndeterminate = false

            // Homebrew
            if lower.contains("homebrew") || (lower.contains("brew") && !lower.contains("whisper")) {
                if lower.contains("[ok]") {
                    statusLabel.stringValue = "Homebrew redan installerat"
                } else {
                    statusLabel.stringValue = "Installerar Homebrew..."
                }
                detailLabel.stringValue = "Pakethanterare för macOS"
                progressBar.doubleValue = max(progressBar.doubleValue, 10)
            }
            // ffmpeg
            else if lower.contains("ffmpeg") {
                if lower.contains("[ok]") {
                    statusLabel.stringValue = "ffmpeg redan installerat"
                } else {
                    statusLabel.stringValue = "Installerar ffmpeg..."
                }
                detailLabel.stringValue = "Ljudkonverteringsverktyg"
                progressBar.doubleValue = max(progressBar.doubleValue, 25)
            }
            // whisper-cli install
            else if lower.contains("whisper") && (lower.contains("install") || lower.contains("[ok]")) && !lower.contains("model") {
                if lower.contains("[ok]") {
                    statusLabel.stringValue = "whisper-cli redan installerat"
                } else {
                    statusLabel.stringValue = "Installerar whisper-cpp..."
                }
                detailLabel.stringValue = "AI-motor för tal-till-text"
                progressBar.doubleValue = max(progressBar.doubleValue, 35)
            }
            // Python venv
            else if lower.contains("virtual environment") || lower.contains("venv") {
                if lower.contains("[ok]") {
                    statusLabel.stringValue = "Python-miljö finns redan"
                } else {
                    statusLabel.stringValue = "Skapar Python-miljö..."
                }
                detailLabel.stringValue = "Isolerad körmiljö för appen"
                progressBar.doubleValue = max(progressBar.doubleValue, 45)
            }
            // pip / dependencies
            else if lower.contains("pip") || lower.contains("dependencies") || lower.contains("requirements") {
                statusLabel.stringValue = "Installerar Python-paket..."
                detailLabel.stringValue = "Beroenden för transkribering"
                progressBar.doubleValue = max(progressBar.doubleValue, 55)
            }
            // Whisper model download
            else if lower.contains("whisper model") || lower.contains("547 mb") || (lower.contains("[ok]") && lower.contains("model") && !lower.contains("vad")) {
                let modelPath = NSHomeDirectory() + "/Library/Application Support/Transcription/models/ggml-large-v3-turbo-q5_0.bin"
                if lower.contains("[ok]") || lower.contains("already") {
                    statusLabel.stringValue = "AI-modell redan nedladdad"
                    detailLabel.stringValue = "→ \(modelPath)"
                    progressBar.doubleValue = max(progressBar.doubleValue, 88)
                } else {
                    statusLabel.stringValue = "Laddar ner AI-modell (~547 MB)..."
                    detailLabel.stringValue = "→ \(modelPath)"
                    progressBar.doubleValue = max(progressBar.doubleValue, 65)
                    progressBar.isIndeterminate = true
                    progressBar.startAnimation(nil)
                }
            }
            // VAD model
            else if lower.contains("vad model") || lower.contains("885 kb") || (lower.contains("[ok]") && lower.contains("vad")) {
                let vadPath = NSHomeDirectory() + "/Library/Application Support/Transcription/models/ggml-silero-vad.bin"
                if lower.contains("[ok]") || lower.contains("already") {
                    statusLabel.stringValue = "VAD-modell redan nedladdad"
                } else {
                    statusLabel.stringValue = "Laddar ner VAD-modell (~885 KB)..."
                }
                detailLabel.stringValue = "→ \(vadPath)"
                progressBar.doubleValue = max(progressBar.doubleValue, 90)
            }
            // Installing to directory
            else if lower.contains("installing app to") {
                statusLabel.stringValue = "Kopierar appfiler..."
                detailLabel.stringValue = line.trimmingCharacters(in: .whitespaces)
                progressBar.doubleValue = max(progressBar.doubleValue, 42)
            }
            // LaunchAgent
            else if lower.contains("launchagent") || lower.contains("auto-start") {
                statusLabel.stringValue = "Ställer in autostart..."
                detailLabel.stringValue = "Appen startar automatiskt vid inloggning"
                progressBar.doubleValue = max(progressBar.doubleValue, 95)
            }
            // Installation complete
            else if lower.contains("installation complete") {
                progressBar.doubleValue = 100
            }
            // Starting app
            else if lower.contains("starting transcription") || lower.contains("starting tala") {
                statusLabel.stringValue = "Startar appen..."
                detailLabel.stringValue = "Appen visas snart i menyraden"
                progressBar.doubleValue = max(progressBar.doubleValue, 98)
            }

            // Try to parse curl download progress (e.g. "##  5.2%")
            if let range = line.range(of: #"(\d+\.?\d*)\s*%"#, options: .regularExpression) {
                let pctStr = line[range].replacingOccurrences(of: "%", with: "").trimmingCharacters(in: .whitespaces)
                if let pct = Double(pctStr), progressBar.isIndeterminate {
                    progressBar.isIndeterminate = false
                    progressBar.stopAnimation(nil)
                    // Map download percent (0-100) to our progress range (65-88)
                    progressBar.doubleValue = 65 + (pct * 0.23)
                    statusLabel.stringValue = "Laddar ner AI-modell... \(Int(pct))%"
                }
            }
    }

    func installComplete() {
        progressBar.isIndeterminate = false
        progressBar.doubleValue = 100
        statusLabel.stringValue = "Installationen är klar!"
        detailLabel.stringValue = "Appen startar automatiskt. Den syns som en mikrofon-ikon i menyraden."
        installButton.title = "Klar"
        installButton.isEnabled = true
        installButton.target = self
        installButton.action = #selector(quitApp)
        quitButton.isHidden = true
    }

    func installFailed() {
        progressBar.isHidden = true
        statusLabel.stringValue = "Installationen misslyckades"
        detailLabel.stringValue = "Kontrollera din internetanslutning och försök igen."
        installButton.title = "Försök igen"
        installButton.isEnabled = true
        installButton.target = self
        installButton.action = #selector(startInstall)
    }
}

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: InstallerWindow!

    func applicationDidFinishLaunching(_ notification: Notification) {
        window = InstallerWindow()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }
}

// --- Main ---
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
