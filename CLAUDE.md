# Tala™ — Röstmemo till text

## Version
- **Nuvarande:** 1.2.8 (2026-04-01)
- **Producent:** Johan Salo, johan.salo@aiempowerlabs.com
- **Powered by:** AI Empower Labs © 2026

## Stack
- Python 3 / Flask (port 5051)
- SQLite3
- whisper-cli (lokal STT via whisper-cpp)
- rumps (macOS menubar-app)
- Swift/Cocoa (native installer)

## Arkitektur
- **app.py** — Flask web UI, batch-transkribering, paginering, input-mapp-stöd
- **watcher.py** — Bevakar Voice Memos + input-mapp, transkriberar nya filer
- **transcription_app.py** — macOS menubar-app (rumps), tooltips, "Om Tala™"
- **config.py** — Sökvägar, inställningar, språk (Auto/Svenska/English/Deutsch)
- **setup_wizard.py** — Kontrollerar beroenden vid första start
- **system_recorder.py** — Spelar in systemljud via BlackHole
- **install.sh** — Installationsskript (brew deps, venv, modeller, LaunchAgent)
- **uninstall.sh** — Avinstallationsskript
- **build_dmg.sh** — Bygger distribuerbar DMG med native Swift-installer
- **installer/TranscriptionInstaller.swift** — Native Cocoa installer-app med ikon + copyright
- **tray_icon.png** — Menubar-ikon (36x36 svart mikrofon, template image)

## Sökvägar
- **Projektkod:** `~/dev/tala/`
- **Installation:** `~/Applications/Tala/` (ändrat från Transcription i v1.2.7)
- **DB:** `~/Library/Application Support/Transcription/db/transcripts.db`
- **Transkriptioner:** `~/Library/Application Support/Transcription/transcripts/`
- **Voice Memos:** `~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings/`
- **Input-mapp:** `~/Library/Application Support/Transcription/input/`
- **Modeller:** `~/Library/Application Support/Transcription/models/`
- **Loggar:** `~/Library/Logs/Transcription/`
- **LaunchAgent:** `~/Library/LaunchAgents/com.transcription.menubar.plist`

## Whisper-modell
- **whisper-cpp version:** 1.8.3 (brew)
- **Modell:** ggml-large-v3-turbo-q5_0.bin (~547 MB)
- **VAD-modell:** ggml-silero-vad.bin (~885 KB)
- m4a stöds INTE direkt, watcher.py konverterar till WAV via ffmpeg

## Hela flödet
1. Användaren spelar in Voice Memo på iPhone
2. iCloud synkar till Mac
3. watcher.py upptäcker ny .m4a-fil
4. whisper-cli transkriberar lokalt
5. Resultat sparas i SQLite-DB + textfil
6. Visas i Flask UI (localhost:5051) och menyrads-ikon

## Web UI (index.html)
- **Flikar:** Voice Memos | Transkriberade | Nya | Inmatade filer
- **Voice Memos** = filer från iCloud (source='voice')
- **Inmatade filer** = filer från input-mappen (source='input'), visas bara om det finns filer
- **Batch-knapp:** "Transkribera 10 till" visas om det finns otranskriberade memon
- **Paginering:** Visar 50 memon åt gången, "Visa fler"-knapp
- **Sökning:** Debounced sökning i transkriptioner och filnamn

## API-endpoints
- `POST /api/transcribe` — transkribera enskild fil i bakgrunden
- `GET /api/status/<filename>` — status för enskild fil
- `POST /api/transcribe_batch` — batch-transkribera N filer (default 10, max 50)
- `GET /api/batch_status` — progress: `{running, total, done, current}`
- `GET /api/transcripts` — lista alla transkriptioner (sökbar med ?q=)
- `DELETE /api/transcript/<id>` — radera transkription
- `GET /audio/<id>` — servera ljud via transcript-ID
- `GET /audio/file/<filename>` — servera ljud direkt från Voice Memos-mappen

## Bygga DMG
```bash
cd ~/dev/tala && bash build_dmg.sh
# -> build/Tala-1.2.8.dmg
```
Version ändras på 3 ställen i `build_dmg.sh` (VERSION, CFBundleVersion, CFBundleShortVersionString) + i `transcription_app.py` (Om-dialogen).

DMG-innehåll:
- **ÖPPNA FÖRST.command** — Tar bort macOS-quarantine (xattr -cr), öppnar installern
- **Installera Tala.app** — Native Swift-installer med ikon, progressbar, copyright
- **Tala.app** — AppleScript-launcher för post-install
- **LÄS MIG.txt** — Installationsinstruktioner
- Båda appar ad-hoc codesignade (`codesign --force --deep --sign -`)

## Kända fallgropar
- **rumps.MenuItem är INTE hashbar.** Använd lista av tupler, inte dict.
- **Appen MÅSTE köras via venv** (Python 3.12). Brew:s Python 3.14 saknar beroenden. Starta alltid via `start.command` eller `source venv/bin/activate`.
- **Voice Memos-appen** heter `VoiceMemos` (utan mellanslag) på macOS.
- **Tray-ikon:** Skapas med `rsvg-convert` från SVG. qlmanage ger vit fyrkant. CoreGraphics/Quartz saknas i venv.
- **Rescan avstängd:** Automatisk rescan var 5 min transkriberar inte längre gamla filer (dödade datorn med 1100+ filer). Batch-transkribering sköts via UI.
- **Kopiera efter ändring:** Ändrade filer i `~/dev/tala/` måste kopieras till `~/Applications/Tala/`.
- **venv går sönder vid mappbyte:** pyvenv.cfg har hårdkodad sökväg. Måste återskapas + Info.plist fixas med PlistBuddy.
- **Zombieprocesser:** Vid omstart kan gamla watcher/app.py-processer överleva. start.command dödar bara transcription_app.py, inte dess subprocess. Använd `pkill -f watcher.py && pkill -f "python.*app.py"` vid behov.
- **Gatekeeper:** macOS blockerar osignerade appar. Lösning: ÖPPNA FÖRST.command (xattr -cr) eller högerklicka > Öppna.

## Distribution
- Michael: kollega
- Kompis i Hamburg: tysk användare (Deutsch tillagt v1.2.3)

## Ändringslogg
- **v1.2.8** (2026-04-01): Embedded source files i installer-bundle (undviker App Translocation). Ad-hoc codesigning, "ÖPPNA FÖRST.command" i DMG, launcher pekar på ~/Applications/Tala.
- **v1.2.7** (2026-03-22): Installationsmapp omdöpt till ~/Applications/Tala. Alla referenser uppdaterade (install.sh, uninstall.sh, build_dmg.sh, LaunchAgent). Input-filer visas i web UI som separat "Inmatade filer"-flik med source-tagging.
- **v1.2.6** (2026-03-20): Installer-UI: app-ikon, TM-symbol, "Powered by AI Empower Labs © 2026"
- **v1.2.5** (2026-03-20): "ÖPPNA FÖRST.command" i DMG för att kringgå Gatekeeper
- **v1.2.4** (2026-03-20): Ad-hoc codesigning av .app-bundles i DMG
- **v1.2.3** (2026-03-18): Lade till Deutsch som språkval
- **v1.2.2** (2026-03-18): Tooltips, Om Tala™, tray-ikon, VoiceMemos-fix, trademark
- **v1.2.0** (2026-03-18): Batch-transkribering, stoppat auto-rescan, paginering
- **v1.1.0**: Tidigare version

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
