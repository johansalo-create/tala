#!/bin/bash
# ============================================================
# Transcription App — Installer
# One-command setup for macOS. Run:
#   bash install.sh
# ============================================================
set -e

APP_NAME="Transcription"
INSTALL_DIR="$HOME/Applications/Transcription"
VENV_DIR="$INSTALL_DIR/venv"
LAUNCH_AGENT_LABEL="com.transcription.menubar"
LAUNCH_AGENT_PLIST="$HOME/Library/LaunchAgents/${LAUNCH_AGENT_LABEL}.plist"

echo "============================================"
echo "  $APP_NAME Installer"
echo "============================================"
echo ""

# --- 1. Check for Homebrew ---
if ! command -v brew &>/dev/null; then
    echo "Homebrew not found. Installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add Homebrew to PATH for Apple Silicon
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
else
    echo "[OK] Homebrew installed"
fi

# --- 2. Install system dependencies ---
echo ""
echo "Installing system dependencies..."

if ! command -v ffmpeg &>/dev/null; then
    echo "  Installing ffmpeg..."
    brew install ffmpeg
else
    echo "  [OK] ffmpeg"
fi

if ! command -v whisper-cli &>/dev/null; then
    # Also check Homebrew paths directly
    if [ -f /opt/homebrew/bin/whisper-cli ] || [ -f /usr/local/bin/whisper-cli ]; then
        echo "  [OK] whisper-cli"
    else
        echo "  Installing whisper-cpp (speech-to-text engine)..."
        brew install whisper-cpp
    fi
else
    echo "  [OK] whisper-cli"
fi

# --- 3. Copy app files ---
echo ""
echo "Installing app to $INSTALL_DIR..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "$SCRIPT_DIR" = "$INSTALL_DIR" ]; then
    echo "  Already in install location."
else
    mkdir -p "$INSTALL_DIR"
    # Copy all Python files, templates, and config
    cp "$SCRIPT_DIR"/*.py "$INSTALL_DIR/"
    cp "$SCRIPT_DIR"/requirements.txt "$INSTALL_DIR/"
    if [ -d "$SCRIPT_DIR/templates" ]; then
        cp -r "$SCRIPT_DIR/templates" "$INSTALL_DIR/"
    fi
    if [ -f "$SCRIPT_DIR/icon.icns" ]; then
        cp "$SCRIPT_DIR/icon.icns" "$INSTALL_DIR/"
    fi
    # Copy launcher scripts
    if [ -f "$SCRIPT_DIR/start.command" ]; then
        cp "$SCRIPT_DIR/start.command" "$INSTALL_DIR/"
        chmod +x "$INSTALL_DIR/start.command"
    fi
fi

# --- 4. Create Python virtual environment ---
echo ""
if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python3" ]; then
    echo "[OK] Python virtual environment exists"
else
    echo "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

echo "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

# --- 5. Download models (non-interactive) ---
echo ""
MODEL_DIR="$HOME/Library/Application Support/Transcription/models"
mkdir -p "$MODEL_DIR"

WHISPER_MODEL="$MODEL_DIR/ggml-large-v3-turbo-q5_0.bin"
VAD_MODEL="$MODEL_DIR/ggml-silero-vad.bin"

if [ -f "$WHISPER_MODEL" ] && [ "$(stat -f%z "$WHISPER_MODEL" 2>/dev/null || echo 0)" -gt 100000000 ]; then
    echo "[OK] Whisper model already downloaded"
else
    echo "Downloading Whisper model (~547 MB)... this may take a few minutes."
    curl -L --progress-bar -o "$WHISPER_MODEL" \
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin"
    echo "  Done."
fi

if [ -f "$VAD_MODEL" ] && [ "$(stat -f%z "$VAD_MODEL" 2>/dev/null || echo 0)" -gt 100000 ]; then
    echo "[OK] VAD model already downloaded"
else
    echo "Downloading VAD model (~885 KB)..."
    curl -L --progress-bar -o "$VAD_MODEL" \
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-silero-vad.bin"
    echo "  Done."
fi

# --- 6. Create start.command (double-clickable launcher) ---
cat > "$INSTALL_DIR/start.command" << 'LAUNCHER'
#!/bin/bash
# Ensure Homebrew is in PATH (Apple Silicon + Intel)
if [ -f /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -f /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
fi

# Ensure log directory exists
mkdir -p "$HOME/Library/Logs/Transcription"

cd "$(dirname "$0")"
source venv/bin/activate

# Kill any existing instance to avoid duplicates
pkill -f "python3 transcription_app.py" 2>/dev/null || true
sleep 1

python3 transcription_app.py >> "$HOME/Library/Logs/Transcription/app.log" 2>&1
LAUNCHER
chmod +x "$INSTALL_DIR/start.command"

# --- 7. Create LaunchAgent for auto-start ---
echo ""
echo "Setting up auto-start on login..."
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$LAUNCH_AGENT_PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LAUNCH_AGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${INSTALL_DIR}/start.command</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${INSTALL_DIR}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>${HOME}/Library/Logs/Transcription/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${HOME}/Library/Logs/Transcription/stderr.log</string>
</dict>
</plist>
PLIST
mkdir -p "$HOME/Library/Logs/Transcription"
echo "  LaunchAgent created. App will start on login."

# --- 8. Done ---
echo ""
echo "============================================"
echo "  Installation complete!"
echo "============================================"
echo ""
echo "How it works:"
echo "  1. Record a Voice Memo on your iPhone"
echo "  2. It syncs via iCloud to your Mac"
echo "  3. The app automatically transcribes it"
echo "  4. View transcripts at http://localhost:5051"
echo ""
echo "To start now:"
echo "  open $INSTALL_DIR/start.command"
echo ""
echo "To drop audio files manually:"
echo "  open ~/Library/Application\\ Support/Transcription/input/"
echo ""

# Start the app via LaunchAgent (no Terminal window)
echo "Starting Tala app..."
launchctl unload "$LAUNCH_AGENT_PLIST" 2>/dev/null || true
launchctl load "$LAUNCH_AGENT_PLIST"
