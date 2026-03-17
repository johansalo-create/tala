# Tala — Röstmemo till text

## Stack
- Python 3 / Flask (port 5051)
- SQLite3
- whisper-cli (lokal STT via whisper-cpp)
- rumps (macOS menubar-app)
- Swift/Cocoa (native installer)

## Arkitektur
- **app.py** — Flask web UI för att visa/söka transkriptioner
- **watcher.py** — Bevakar Voice Memos + input-mapp, transkriberar nya filer
- **transcription_app.py** — macOS menubar-app (rumps) som startar/stoppar watcher + webapp
- **config.py** — Alla sökvägar och inställningar
- **setup_wizard.py** — Kontrollerar beroenden vid första start
- **system_recorder.py** — Spelar in systemljud via BlackHole
- **install.sh** — Installationsskript (brew deps, venv, modeller, LaunchAgent)
- **build_dmg.sh** — Bygger distribuerbar DMG med native Swift-installer
- **installer/TranscriptionInstaller.swift** — Native Cocoa installer-app

## Sökvägar
- **Projektkod:** `~/dev/tala/`
- **DB:** `~/Library/Application Support/Transcription/db/transcripts.db`
- **Transkriptioner:** `~/Library/Application Support/Transcription/transcripts/`
- **Voice Memos:** `~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings/`
- **Input-mapp:** `~/Library/Application Support/Transcription/input/`
- **Modeller:** `~/Library/Application Support/Transcription/models/`
- **Loggar:** `~/Library/Logs/Transcription/`

## Whisper-modell
- **whisper-cpp version:** 1.8.3 (brew)
- **Modell:** ggml-large-v3-turbo-q5_0.bin (~547 MB)
- **VAD-modell:** ggml-silero-vad.bin (~885 KB)
- m4a stöds INTE direkt — watcher.py konverterar till WAV via ffmpeg

## Hela flödet
1. Johan spelar in Voice Memo på iPhone
2. iCloud synkar till Mac
3. watcher.py upptäcker ny .m4a-fil
4. whisper-cli transkriberar lokalt
5. Resultat sparas i SQLite-DB + textfil
6. Visas i Flask UI (localhost:5051) och menyrads-ikon

## Bygga DMG
```bash
bash build_dmg.sh
# → build/Tala-1.0.0.dmg
```

## DB-schema
```sql
CREATE TABLE transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    original_path TEXT NOT NULL,
    file_hash TEXT UNIQUE NOT NULL,
    transcript TEXT,
    duration_seconds REAL,
    language TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    transcribed_at TIMESTAMP
);
```
