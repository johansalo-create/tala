#!/bin/bash
# ============================================================
# Transcription App — Uninstaller
# ============================================================
set -e

INSTALL_DIR="$HOME/Applications/Transcription"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/com.transcription.menubar.plist"
APP_DATA="$HOME/Library/Application Support/Transcription"
LOG_DIR="$HOME/Library/Logs/Transcription"

echo "Transcription App Uninstaller"
echo ""

# Stop the app if running
if launchctl list | grep -q "com.transcription.menubar" 2>/dev/null; then
    echo "Stopping app..."
    launchctl unload "$LAUNCH_AGENT" 2>/dev/null || true
fi

# Kill any running processes
pkill -f "transcription_app.py" 2>/dev/null || true
pkill -f "watcher.py" 2>/dev/null || true

# Remove LaunchAgent
if [ -f "$LAUNCH_AGENT" ]; then
    rm "$LAUNCH_AGENT"
    echo "  Removed LaunchAgent"
fi

# Remove app files
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    echo "  Removed app: $INSTALL_DIR"
fi

# Remove logs
if [ -d "$LOG_DIR" ]; then
    rm -rf "$LOG_DIR"
    echo "  Removed logs"
fi

# Ask about data
echo ""
read -p "Remove transcription data and models? (y/n) [n]: " REMOVE_DATA
REMOVE_DATA=${REMOVE_DATA:-n}

if [[ "$REMOVE_DATA" =~ ^[Yy] ]]; then
    if [ -d "$APP_DATA" ]; then
        rm -rf "$APP_DATA"
        echo "  Removed app data: $APP_DATA"
    fi
else
    echo "  Kept app data at: $APP_DATA"
fi

echo ""
echo "Uninstall complete."
echo "Note: Homebrew packages (ffmpeg, whisper-cpp) were not removed."
echo "      Run 'brew uninstall ffmpeg whisper-cpp' to remove them."
