#!/usr/bin/env python3
"""
Transcription Menu Bar App
A simple macOS menu bar app to control the transcription service.
"""
import os
import sys
import subprocess
import threading
import time
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

import json
import rumps
from AppKit import NSPasteboard, NSStringPboardType

# Import config
from config import (
    DB_PATH, SETTINGS_PATH, LANGUAGE_OPTIONS, VOICE_MEMOS_DIR,
    INPUT_DIR, FLASK_PORT
)
from system_recorder import (
    SystemRecorder, check_blackhole_installed,
    show_blackhole_setup_instructions
)

# Script paths - relative to this file
BASE_DIR = Path(__file__).parent
WATCHER_SCRIPT = BASE_DIR / "watcher.py"
WEBAPP_SCRIPT = BASE_DIR / "app.py"
TRAY_ICON = BASE_DIR / "tray_icon.png"


class TranscriptionApp(rumps.App):
    def __init__(self):
        icon_path = str(TRAY_ICON) if TRAY_ICON.exists() else None
        super().__init__(
            "Tala™",
            icon=icon_path,
            template=False,
            quit_button=None
        )
        self.watcher_process = None
        self.webapp_process = None
        self.is_running = False

        # System audio recorder
        self.system_recorder = SystemRecorder()
        self.recording_timer = None

        # Menu items — svenska namn
        self.toggle_item = rumps.MenuItem("Pausa", callback=self.toggle_service)
        self.status_item = rumps.MenuItem("Aktiv", callback=None)
        self.status_item.set_callback(None)

        # System recording menu item
        self.record_system_item = rumps.MenuItem("Spela in datorljud", callback=self.toggle_system_recording)

        self.recent_menu = rumps.MenuItem("Senaste")
        self.language_menu = rumps.MenuItem("Språk")
        self._build_language_menu()

        self.record_voice_item = rumps.MenuItem("Spela in röstmemo", callback=self.start_voice_memo)
        self.transcribe_recent_item = rumps.MenuItem("Transkribera senaste", callback=self.process_recent)
        self.webui_item = rumps.MenuItem("Visa transkriptioner", callback=self.open_webui)
        self.voice_memos_item = rumps.MenuItem("Röstmemon i Finder", callback=self.open_voice_memos)
        self.input_folder_item = rumps.MenuItem("Inmatning i Finder", callback=self.open_input_folder)
        self.about_item = rumps.MenuItem("Om Tala™", callback=self.show_about)
        self.quit_item = rumps.MenuItem("Avsluta", callback=self.quit_app)

        menu_items = [
            self.toggle_item,
            self.status_item,
            None,  # Separator
            self.record_voice_item,
            self.record_system_item,
            self.transcribe_recent_item,
            self.webui_item,
            self.voice_memos_item,
            self.input_folder_item,
            None,  # Separator
            self.language_menu,
            self.recent_menu,
            None,  # Separator
            self.about_item,
            self.quit_item,
        ]

        # Tooltips
        tooltips = [
            (self.record_voice_item, "Öppnar Apples Voice Memos-app"),
            (self.record_system_item, "Spelar in ljud från datorn (kräver BlackHole)"),
            (self.transcribe_recent_item, "Transkribera senaste röstmemot manuellt"),
            (self.webui_item, f"Öppnar webbgränssnittet (localhost:{FLASK_PORT})"),
            (self.voice_memos_item, "Öppnar mappen med synkade iPhone-memon"),
            (self.input_folder_item, "Öppnar mappen dit du kan dra egna ljudfiler"),
        ]
        for item, tip in tooltips:
            item._menuitem.setToolTip_(tip)
        self.menu = menu_items

        self.update_recent_transcripts()

        # Start a thread to periodically update recent transcripts
        self.update_thread = threading.Thread(target=self.periodic_update, daemon=True)
        self.update_thread.start()

        # Autostart service
        self.start_service()
        self.update_title()

    def _get_settings(self):
        """Load settings from file."""
        if SETTINGS_PATH.exists():
            try:
                with open(SETTINGS_PATH, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"language": "auto"}

    def _save_settings(self, settings):
        """Save settings to file."""
        with open(SETTINGS_PATH, 'w') as f:
            json.dump(settings, f)

    def _build_language_menu(self):
        """Build the language selection submenu."""
        current_lang = self._get_settings().get("language", "auto")

        for label, code in LANGUAGE_OPTIONS.items():
            item = rumps.MenuItem(
                label,
                callback=lambda sender, c=code: self._set_language(c)
            )
            if code == current_lang:
                item.state = 1  # Checkmark
            self.language_menu[label] = item

    def _set_language(self, language_code):
        """Set the transcription language."""
        settings = self._get_settings()
        settings["language"] = language_code
        self._save_settings(settings)

        # Update checkmarks
        for label, code in LANGUAGE_OPTIONS.items():
            if label in self.language_menu:
                self.language_menu[label].state = 1 if code == language_code else 0

        # Find the label for notification
        lang_label = next((k for k, v in LANGUAGE_OPTIONS.items() if v == language_code), language_code)
        rumps.notification(
            "Language Changed",
            f"Set to: {lang_label}",
            "New transcriptions will use this language."
        )

    def update_title(self):
        """Update the menu bar icon/title based on status."""
        if self.is_running:
            self.title = ""
            self.toggle_item.title = "Pausa"
            self.status_item.title = "Aktiv"
        else:
            self.title = ""
            self.toggle_item.title = "Återuppta"
            self.status_item.title = "Av"

    def toggle_service(self, sender):
        """Toggle the transcription service on/off."""
        if self.is_running:
            self.stop_service()
        else:
            self.start_service()
        self.update_title()

    def start_service(self):
        """Start the watcher and web app."""
        try:
            # Use the same Python that's running this script
            python_exe = sys.executable

            # Start watcher
            self.watcher_process = subprocess.Popen(
                [python_exe, str(WATCHER_SCRIPT)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(BASE_DIR)
            )

            # Start web app
            self.webapp_process = subprocess.Popen(
                [python_exe, str(WEBAPP_SCRIPT)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(BASE_DIR)
            )

            self.is_running = True
            rumps.notification(
                "Tala™",
                "Startad",
                "Bevakar nya röstmemon..."
            )
        except Exception as e:
            rumps.alert(f"Kunde inte starta: {e}")

    def stop_service(self):
        """Stop the watcher and web app."""
        try:
            if self.watcher_process:
                self.watcher_process.terminate()
                self.watcher_process = None
            if self.webapp_process:
                self.webapp_process.terminate()
                self.webapp_process = None
            self.is_running = False
            rumps.notification(
                "Tala™",
                "Pausad",
                "Tjänsten är pausad."
            )
        except Exception as e:
            rumps.alert(f"Kunde inte stoppa: {e}")

    def process_recent(self, sender):
        """Manually trigger processing of recent files."""
        if not self.is_running:
            rumps.alert("Starta tjänsten först")
            return

        rumps.notification(
            "Tala™",
            "Bearbetar",
            "Letar efter nya filer..."
        )

    def start_voice_memo(self, sender):
        """Open Voice Memos app to start recording."""
        subprocess.run(["open", "-a", "VoiceMemos"])

    def toggle_system_recording(self, sender):
        """Start or stop system audio recording."""
        if self.system_recorder.is_recording:
            # Stop recording
            output_file, message = self.system_recorder.stop_recording()
            self.record_system_item.title = "Spela in datorljud"
            self.title = ""

            if self.recording_timer:
                self.recording_timer.stop()
                self.recording_timer = None

            if output_file and output_file.exists():
                rumps.notification(
                    "Recording Saved",
                    message,
                    f"File: {output_file.name}\nWill be transcribed automatically."
                )
            else:
                rumps.notification(
                    "Recording Stopped",
                    message,
                    ""
                )
        else:
            # Check if BlackHole is installed
            if not check_blackhole_installed():
                response = rumps.alert(
                    title="BlackHole Required",
                    message="To record system audio, you need BlackHole installed.\n\nWould you like to see setup instructions?",
                    ok="Show Instructions",
                    cancel="Cancel"
                )
                if response == 1:
                    rumps.alert(
                        title="BlackHole Setup",
                        message=show_blackhole_setup_instructions(),
                        ok="OK"
                    )
                return

            # Start recording
            success, message = self.system_recorder.start_recording()
            if success:
                self.record_system_item.title = "Stoppa inspelning"
                self.title = " REC"
                rumps.notification(
                    "Recording Started",
                    "System Audio",
                    "Click 'Stop Recording' when done."
                )

                # Start timer to update duration
                self.recording_timer = rumps.Timer(self.update_recording_duration, 1)
                self.recording_timer.start()
            else:
                rumps.alert(f"Failed to start recording: {message}")

    def update_recording_duration(self, sender):
        """Update the menu item with recording duration."""
        if self.system_recorder.is_recording:
            duration = int(self.system_recorder.get_duration())
            mins = duration // 60
            secs = duration % 60
            self.record_system_item.title = f"Stoppa inspelning ({mins}:{secs:02d})"

    def open_webui(self, sender):
        """Open the web UI in browser."""
        subprocess.run(["open", f"http://localhost:{FLASK_PORT}"])

    def open_voice_memos(self, sender):
        """Open the Voice Memos folder in Finder."""
        subprocess.run(["open", str(VOICE_MEMOS_DIR)])

    def show_about(self, sender):
        """Show about dialog."""
        rumps.alert(
            title="Om Tala™ v1.2.8",
            message=(
                "Tala™ transkriberar dina röstmemon automatiskt med lokal AI. "
                "Allt sker på din Mac, inget skickas till molnet.\n\n"
                "Så fungerar det:\n"
                "1. Spela in ett röstmemo på din iPhone\n"
                "2. iCloud synkar filen till din Mac\n"
                "3. Tala™ transkriberar automatiskt med whisper\n"
                "4. Läs, sök och kopiera texten i webbgränssnittet\n\n"
                "10 sätt att använda Tala™:\n\n"
                "1. Spela in säljmöten och skapa offerter från samtalet\n"
                "2. Diktera idéer och tankar när du är ute och går\n"
                "3. Dokumentera kundsamtal och följa upp löften\n"
                "4. Spela in föreläsningar och få sökbara anteckningar\n"
                "5. Röstdagbok, kom ihåg vad du tänkte och kände\n"
                "6. Brainstorma i grupp och få allt nedskrivet\n"
                "7. Spela in telefonsamtal (med samtycke) som referens\n"
                "8. Dokumentera byggarbetsplatser och besiktningar\n"
                "9. Skapa mötesprotokoll utan att anteckna för hand\n"
                "10. Samla feedback från kunder i fält\n\n"
                "Producerat av Johan Salo\n"
                "johan.salo@aiempowerlabs.com"
            ),
            ok="Stäng"
        )

    def open_input_folder(self, sender):
        """Open the input folder in Finder for dropping audio files."""
        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(INPUT_DIR)])

    def get_recent_transcripts(self, limit=5):
        """Get recent transcripts from database."""
        if not DB_PATH.exists():
            return []

        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, filename, transcript, transcribed_at
                FROM transcripts
                ORDER BY transcribed_at DESC
                LIMIT ?
            """, (limit,))
            results = cursor.fetchall()
            conn.close()
            return results
        except Exception:
            return []

    def update_recent_transcripts(self):
        """Update the recent transcripts submenu."""
        transcripts = self.get_recent_transcripts(5)

        # Clear existing submenu items (only if menu is initialized)
        try:
            for key in list(self.recent_menu.keys()):
                del self.recent_menu[key]
        except Exception:
            pass

        if not transcripts:
            self.recent_menu["No transcripts yet"] = None
            return

        for t in transcripts:
            # Create a submenu item for each transcript
            filename = t['filename'][:30] + "..." if len(t['filename']) > 30 else t['filename']

            item = rumps.MenuItem(
                f"{filename}",
                callback=lambda sender, tid=t['id']: self.show_transcript_menu(tid)
            )
            self.recent_menu[filename] = item

    def show_transcript_menu(self, transcript_id):
        """Show options for a transcript."""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM transcripts WHERE id = ?", (transcript_id,))
            t = cursor.fetchone()
            conn.close()

            if not t:
                return

            # Create a window with the transcript
            transcript_text = t['transcript'] or ""

            # Copy to clipboard
            pb = NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.setString_forType_(transcript_text, NSStringPboardType)

            rumps.notification(
                "Copied to Clipboard",
                t['filename'],
                f"Transcript copied ({len(transcript_text)} chars)"
            )
        except Exception as e:
            rumps.alert(f"Error: {e}")

    def periodic_update(self):
        """Periodically update the recent transcripts."""
        while True:
            time.sleep(30)
            try:
                self.update_recent_transcripts()
            except Exception:
                pass

    def quit_app(self, sender):
        """Quit the application."""
        self.stop_service()
        rumps.quit_application()


if __name__ == "__main__":
    print(f"Tala starting at {datetime.now()}", flush=True)

    # Run setup wizard on first launch
    from setup_wizard import run_setup
    if not run_setup():
        print("Setup wizard returned False, exiting", flush=True)
        sys.exit(0)

    print("Setup OK, launching menubar app", flush=True)
    app = TranscriptionApp()
    app.run()
