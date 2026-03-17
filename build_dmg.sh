#!/bin/bash
# ============================================================
# Build a distributable DMG for Tala
# Creates double-clickable .app bundles — no Terminal needed.
# ============================================================
set -e

APP_NAME="Tala"
VERSION="1.0.0"
DMG_NAME="${APP_NAME}-${VERSION}"
BUILD_DIR="$(pwd)/build"
STAGE_DIR="$BUILD_DIR/dmg-stage"
DMG_PATH="$BUILD_DIR/${DMG_NAME}.dmg"
SRC_DIR="$STAGE_DIR/Tala"

echo "Building $DMG_NAME..."

# Clean
rm -rf "$STAGE_DIR"
mkdir -p "$SRC_DIR"

# Copy app source files (hidden inside the DMG, used by install.sh)
cp *.py "$SRC_DIR/"
cp requirements.txt "$SRC_DIR/"
cp install.sh "$SRC_DIR/"
chmod +x "$SRC_DIR/install.sh"

if [ -d templates ]; then
    cp -r templates "$SRC_DIR/"
fi
if [ -f icon.icns ]; then
    cp icon.icns "$SRC_DIR/"
fi

# --- Build "Installera Tala.app" (native Swift installer) ---
echo "Building native installer app..."
INSTALLER_APP="$STAGE_DIR/Installera Tala.app"
INSTALLER_MACOS="$INSTALLER_APP/Contents/MacOS"
INSTALLER_RES="$INSTALLER_APP/Contents/Resources"
mkdir -p "$INSTALLER_MACOS" "$INSTALLER_RES"

# Compile Swift installer
swiftc -O -o "$INSTALLER_MACOS/TalaInstaller" \
    installer/TranscriptionInstaller.swift \
    -framework Cocoa

# Copy icon into app bundle
if [ -f icon.icns ]; then
    cp icon.icns "$INSTALLER_RES/AppIcon.icns"
fi

# Create Info.plist
cat > "$INSTALLER_APP/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>TalaInstaller</string>
    <key>CFBundleIdentifier</key>
    <string>com.tala.installer</string>
    <key>CFBundleName</key>
    <string>Installera Tala</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
PLIST

# --- Build "Tala.app" (launcher for post-install use) ---
echo "Building Tala.app launcher..."
LAUNCHER_SCRIPT="$BUILD_DIR/launcher.applescript"
cat > "$LAUNCHER_SCRIPT" << 'APPLESCRIPT'
on run
    set installDir to (POSIX path of (path to home folder)) & "Applications/Transcription"
    set startCmd to installDir & "/start.command"

    try
        do shell script "test -f " & quoted form of startCmd
    on error
        display dialog "Tala är inte installerat ännu." & return & return & "Dubbelklicka på 'Installera Tala' först." buttons {"OK"} default button "OK" with icon stop
        return
    end try

    do shell script "open " & quoted form of startCmd
end run
APPLESCRIPT

osacompile -o "$STAGE_DIR/Tala.app" "$LAUNCHER_SCRIPT"
rm "$LAUNCHER_SCRIPT"

# --- Create README ---
cat > "$STAGE_DIR/LÄS MIG.txt" << 'README'
Tala — Röstmemo till text
=========================

Transkriberar dina Voice Memos automatiskt med lokal AI.

INSTALLATION:
1. Dubbelklicka på "Installera Tala"
2. Klicka "Installera" i fönstret som öppnas
3. Vänta tills progressbaren är klar (~5 min)
4. Klart! Appen startar automatiskt.

ANVÄNDNING:
1. Spela in ett Voice Memo på din iPhone
2. Memot synkas automatiskt till din Mac via iCloud
3. Tala transkriberar det automatiskt
4. Se resultat via menyrads-ikonen (🎙️)
   eller i webbläsaren: http://localhost:5051

Appen startar automatiskt när du loggar in.
Om den inte kör, dubbelklicka på "Tala".

KRAV:
- macOS (Apple Silicon eller Intel)
- iPhone med iCloud-synk för Voice Memos
- Internetanslutning (för att ladda ner modeller vid installation)
README

# Create DMG
echo "Creating DMG..."
rm -f "$DMG_PATH"
hdiutil create -volname "$APP_NAME" \
    -srcfolder "$STAGE_DIR" \
    -ov -format UDZO \
    "$DMG_PATH"

# Clean up
rm -rf "$STAGE_DIR"

echo ""
echo "DMG created: $DMG_PATH"
echo "Size: $(du -h "$DMG_PATH" | cut -f1)"
echo ""
echo "Send this file to your colleague."
echo "They just double-click 'Installera Tala' — no Terminal knowledge needed."
