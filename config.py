"""
Configuration for the transcription server.
"""
import os
import subprocess
import multiprocessing
from pathlib import Path

# App data stored in user's Application Support
APP_NAME = "Transcription"
APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)

# Base paths - use Application Support for user data
TRANSCRIPTS_DIR = APP_SUPPORT_DIR / "transcripts"
DB_PATH = APP_SUPPORT_DIR / "db" / "transcripts.db"
MODEL_DIR = APP_SUPPORT_DIR / "models"
MODEL_PATH = MODEL_DIR / "ggml-large-v3-turbo-q5_0.bin"  # Smaller quantized model
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin"

# Voice Memos location (macOS)
VOICE_MEMOS_DIR = Path.home() / "Library" / "Group Containers" / "group.com.apple.VoiceMemos.shared" / "Recordings"

# Input folder for manually added audio files
INPUT_DIR = APP_SUPPORT_DIR / "input"

# Whisper settings - try to find whisper-cli
def find_whisper_cmd():
    """Find whisper-cli in common locations."""
    locations = [
        "/opt/homebrew/bin/whisper-cli",
        "/usr/local/bin/whisper-cli",
        Path.home() / ".local" / "bin" / "whisper-cli",
    ]
    for loc in locations:
        if Path(loc).exists():
            return str(loc)
    # Try to find in PATH
    result = subprocess.run(["which", "whisper-cli"], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return None

WHISPER_CMD = find_whisper_cmd()
WHISPER_THREADS = min(8, multiprocessing.cpu_count())

def find_ffmpeg_cmd():
    """Find ffmpeg in common locations."""
    for loc in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
        if Path(loc).exists():
            return loc
    result = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return "ffmpeg"  # fallback to PATH

FFMPEG_CMD = find_ffmpeg_cmd()

# Language settings
LANGUAGE_OPTIONS = {
    "Auto": "auto",
    "Svenska": "sv",
    "English": "en"
}
DEFAULT_LANGUAGE = "auto"

# Settings file for persistent preferences
SETTINGS_PATH = APP_SUPPORT_DIR / "settings.json"

# Flask settings
FLASK_HOST = "127.0.0.1"  # Localhost only for security
FLASK_PORT = 5051
FLASK_DEBUG = False

# Ensure directories exist
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
INPUT_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
