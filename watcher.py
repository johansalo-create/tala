#!/usr/bin/env python3
"""
Voice Memo Watcher - monitors for new recordings and transcribes them.
"""
import os
import sys
import time
import sqlite3
import subprocess
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from config import (
    VOICE_MEMOS_DIR, TRANSCRIPTS_DIR, DB_PATH, MODEL_PATH, MODEL_DIR,
    WHISPER_CMD, WHISPER_THREADS, INPUT_DIR, SETTINGS_PATH, DEFAULT_LANGUAGE,
    FFMPEG_CMD
)


def get_language_setting():
    """Get the current language setting from settings file."""
    import json
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, 'r') as f:
                settings = json.load(f)
                return settings.get('language', DEFAULT_LANGUAGE)
        except Exception:
            pass
    return DEFAULT_LANGUAGE


def init_db():
    """Initialize the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transcripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            original_path TEXT NOT NULL,
            file_hash TEXT UNIQUE NOT NULL,
            transcript TEXT,
            duration_seconds REAL,
            language TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            transcribed_at TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def get_file_hash(filepath):
    """Get MD5 hash of file to detect duplicates."""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()


def is_already_transcribed(file_hash):
    """Check if file has already been transcribed."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM transcripts WHERE file_hash = ?", (file_hash,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def get_audio_duration(filepath):
    """Get audio duration using ffprobe."""
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', str(filepath)
        ], capture_output=True, text=True)
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def convert_to_wav(input_path, output_path):
    """Convert audio to WAV format for whisper.cpp."""
    subprocess.run([
        FFMPEG_CMD, '-y', '-i', str(input_path),
        '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le',
        str(output_path)
    ], capture_output=True)
    return output_path.exists()


def dedup_transcript(text, max_repeats=2):
    """Remove hallucination loops — consecutive repeated lines/phrases."""
    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue
        # Count how many times this exact line already appears at the tail
        repeat_count = 0
        for prev in reversed(result):
            if prev.strip() == stripped:
                repeat_count += 1
            else:
                break
        if repeat_count < max_repeats:
            result.append(line)
    return '\n'.join(result)


def transcribe_audio(wav_path):
    """Transcribe audio using whisper.cpp."""
    output_base = wav_path.with_suffix('')
    output_file = wav_path.with_suffix('.txt')

    language = get_language_setting()
    print(f"Using language: {language}")

    vad_model = MODEL_DIR / 'ggml-silero-vad.bin'

    result = subprocess.run([
        WHISPER_CMD,
        '-m', str(MODEL_PATH),
        '-t', str(WHISPER_THREADS),
        '-l', language,
        '--vad',
        '-vm', str(vad_model),
        '-otxt',
        '-of', str(output_base),
        str(wav_path)
    ], capture_output=True, text=True)

    # Read the generated transcript
    if output_file.exists():
        transcript = output_file.read_text().strip()
        output_file.unlink()  # Clean up temp file
        return dedup_transcript(transcript)

    # Fallback: parse from stdout if file wasn't created
    return dedup_transcript(result.stdout.strip())


def send_notification(title, message):
    """Send macOS notification."""
    subprocess.run([
        'osascript', '-e',
        f'display notification "{message}" with title "{title}"'
    ])


def process_audio_file(filepath):
    """Process a single audio file."""
    filepath = Path(filepath)

    if not filepath.exists():
        return

    if filepath.suffix.lower() not in ['.m4a', '.mp3', '.wav', '.aac', '.ogg']:
        return

    # Skip small files (likely still being written)
    if filepath.stat().st_size < 1000:
        return

    file_hash = get_file_hash(filepath)

    if is_already_transcribed(file_hash):
        print(f"Already transcribed: {filepath.name}")
        return

    print(f"Processing: {filepath.name}")

    # Get duration
    duration = get_audio_duration(filepath)

    # Convert to WAV
    wav_path = TRANSCRIPTS_DIR / f"{filepath.stem}.wav"
    if not convert_to_wav(filepath, wav_path):
        print(f"Failed to convert: {filepath.name}")
        return

    # Transcribe
    print(f"Transcribing (this may take a moment)...")
    transcript = transcribe_audio(wav_path)

    # Clean up WAV file
    if wav_path.exists():
        wav_path.unlink()

    if not transcript:
        print(f"No transcript generated for: {filepath.name}")
        return

    # Save transcript to file
    transcript_file = TRANSCRIPTS_DIR / f"{filepath.stem}.txt"
    transcript_file.write_text(transcript)

    # Save to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO transcripts (filename, original_path, file_hash, transcript, duration_seconds, transcribed_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        filepath.name,
        str(filepath),
        file_hash,
        transcript,
        duration,
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()

    # Send notification
    preview = transcript[:100] + "..." if len(transcript) > 100 else transcript
    send_notification("Transcription Complete", preview)

    print(f"Done: {filepath.name}")
    print(f"Transcript saved to: {transcript_file}")


class VoiceMemoHandler(FileSystemEventHandler):
    """Handler for new voice memo files."""

    def __init__(self):
        self.pending_files = {}

    def on_created(self, event):
        if event.is_directory:
            return
        # Wait a bit for file to be fully written
        self.pending_files[event.src_path] = time.time()

    def on_modified(self, event):
        if event.is_directory:
            return
        self.pending_files[event.src_path] = time.time()

    def process_pending(self):
        """Process files that haven't been modified recently."""
        now = time.time()
        to_process = []

        for filepath, last_modified in list(self.pending_files.items()):
            # Wait 3 seconds after last modification
            if now - last_modified > 3:
                to_process.append(filepath)
                del self.pending_files[filepath]

        for filepath in to_process:
            try:
                process_audio_file(filepath)
            except Exception as e:
                print(f"Error processing {filepath}: {e}")


def parse_date_from_filename(filename):
    """Parse date from filename like '20251212 013354-XXXX.m4a' -> datetime or None."""
    import re
    match = re.match(r'^(\d{8})\s*(\d{6})', filename)
    if match:
        try:
            date_str = match.group(1) + match.group(2)
            return datetime.strptime(date_str, "%Y%m%d%H%M%S")
        except ValueError:
            pass
    return None


def process_existing_files(days=14, limit=None):
    """Process existing unprocessed files from the last N days.

    Args:
        days: Only look at files from the last N days.
        limit: Max number of files to transcribe (newest first). None = no limit.
    """
    print(f"Checking for existing files in: {VOICE_MEMOS_DIR}")
    print(f"Looking at files from the last {days} days (limit={limit})...")

    if not VOICE_MEMOS_DIR.exists():
        print(f"Voice Memos directory not found: {VOICE_MEMOS_DIR}")
        return

    cutoff_date = datetime.now() - timedelta(days=days)
    files_checked = 0
    files_processed = 0

    # Collect and sort by date (newest first) so limit takes the most recent
    candidates = []
    for filepath in VOICE_MEMOS_DIR.glob("*.m4a"):
        file_date = parse_date_from_filename(filepath.name)
        if file_date and file_date < cutoff_date:
            continue
        candidates.append((filepath, file_date or datetime.min))

    candidates.sort(key=lambda x: x[1], reverse=True)

    for filepath, _ in candidates:
        try:
            files_checked += 1
            file_hash = get_file_hash(filepath)

            if not is_already_transcribed(file_hash):
                process_audio_file(filepath)
                files_processed += 1
                if limit and files_processed >= limit:
                    print(f"Reached limit of {limit} files")
                    break
        except Exception as e:
            print(f"Error processing {filepath}: {e}")

    print(f"Checked {files_checked} recent files, processed {files_processed} new files")


def process_input_folder():
    """Process all unprocessed files in the input folder."""
    print(f"Checking input folder: {INPUT_DIR}")

    if not INPUT_DIR.exists():
        return

    files_processed = 0

    for ext in ['*.m4a', '*.mp3', '*.wav', '*.aac', '*.ogg']:
        for filepath in INPUT_DIR.glob(ext):
            try:
                file_hash = get_file_hash(filepath)
                if not is_already_transcribed(file_hash):
                    process_audio_file(filepath)
                    files_processed += 1
            except Exception as e:
                print(f"Error processing {filepath}: {e}")

    print(f"Processed {files_processed} files from input folder")


def main():
    """Main entry point."""
    print("=" * 50)
    print("Voice Memo Transcription Watcher")
    print("=" * 50)
    print(f"Watching: {VOICE_MEMOS_DIR}")
    print(f"Input folder: {INPUT_DIR}")
    print(f"Transcripts: {TRANSCRIPTS_DIR}")
    print(f"Model: {MODEL_PATH}")
    print("=" * 50)

    # Initialize database
    init_db()

    # Process existing files first (only 10 newest to avoid long startup)
    process_existing_files(limit=10)
    process_input_folder()

    # Set up file watchers
    event_handler = VoiceMemoHandler()
    observer = Observer()

    # Watch Voice Memos folder if it exists
    if VOICE_MEMOS_DIR.exists():
        observer.schedule(event_handler, str(VOICE_MEMOS_DIR), recursive=False)

    # Watch input folder
    observer.schedule(event_handler, str(INPUT_DIR), recursive=False)

    observer.start()

    print("\nWatching for new recordings... (Ctrl+C to stop)")

    last_rescan = time.time()
    rescan_interval = 300  # Re-scan every 5 minutes to catch iCloud-synced files

    try:
        while True:
            time.sleep(1)
            event_handler.process_pending()

            # Periodic re-scan to catch iCloud-synced files missed by watchdog
            if time.time() - last_rescan > rescan_interval:
                process_existing_files(days=2, limit=5)
                process_input_folder()
                last_rescan = time.time()
    except KeyboardInterrupt:
        observer.stop()
        print("\nStopped.")

    observer.join()


if __name__ == "__main__":
    main()
