#!/usr/bin/env python3
"""
Flask web app for viewing and searching transcripts.
"""
import re
import sqlite3
import threading
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, abort

import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import DB_PATH, TRANSCRIPTS_DIR, VOICE_MEMOS_DIR, FLASK_HOST, FLASK_PORT, INPUT_DIR

app = Flask(__name__)

# Track background transcription jobs: filename -> status
_transcription_status = {}
_transcription_lock = threading.Lock()

# Batch transcription state
_batch_state = {
    'running': False,
    'total': 0,
    'done': 0,
    'current': '',
}

SWEDISH_MONTHS = {
    1: 'jan', 2: 'feb', 3: 'mar', 4: 'apr', 5: 'maj', 6: 'jun',
    7: 'jul', 8: 'aug', 9: 'sep', 10: 'okt', 11: 'nov', 12: 'dec'
}


def init_db():
    """Ensure database tables exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
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
    # Add index on filename for fast lookups
    conn.execute("CREATE INDEX IF NOT EXISTS idx_transcripts_filename ON transcripts(filename)")
    conn.commit()
    conn.close()


init_db()


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def format_duration(seconds):
    """Format duration as mm:ss or hh:mm:ss."""
    if not seconds:
        return "0:00"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_date(date_str):
    """Format ISO date string for display."""
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return date_str


def parse_filename_timestamp(filename):
    """Parse timestamp from filename like '20251212 013354-XXXX.m4a'."""
    match = re.match(r'^(\d{8})\s*(\d{6})', filename)
    if match:
        try:
            date_str = match.group(1) + match.group(2)
            return datetime.strptime(date_str, "%Y%m%d%H%M%S")
        except ValueError:
            pass
    return None


def format_swedish_date(dt):
    """Format datetime as '17 mar 2026, 09:44'."""
    if not dt:
        return ""
    month = SWEDISH_MONTHS.get(dt.month, str(dt.month))
    return f"{dt.day} {month} {dt.year}, {dt.hour:02d}:{dt.minute:02d}"


def list_all_voice_memos():
    """List all .m4a files in Voice Memos folder, matched against DB."""
    if not VOICE_MEMOS_DIR.exists():
        return []

    # Get all transcribed filenames from DB
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT filename, id, transcript, duration_seconds, transcribed_at FROM transcripts")
    db_rows = cursor.fetchall()
    conn.close()

    transcribed = {}
    for row in db_rows:
        transcribed[row['filename']] = {
            'id': row['id'],
            'transcript': row['transcript'],
            'duration': format_duration(row['duration_seconds']),
            'transcribed_at': row['transcribed_at'],
        }

    items = []
    seen_filenames = set()

    # Collect files with source tag
    tagged_files = [(f, 'voice') for f in VOICE_MEMOS_DIR.glob("*.m4a")]
    if INPUT_DIR.exists():
        for ext in ['*.m4a', '*.mp3', '*.wav', '*.aac', '*.ogg']:
            tagged_files.extend((f, 'input') for f in INPUT_DIR.glob(ext))

    for filepath, source in tagged_files:
        filename = filepath.name
        if filename in seen_filenames:
            continue
        seen_filenames.add(filename)
        file_date = parse_filename_timestamp(filename)
        db_info = transcribed.get(filename)

        # Check if currently being transcribed
        with _transcription_lock:
            bg_status = _transcription_status.get(filename)

        if db_info:
            status = 'transcribed'
        elif bg_status == 'processing':
            status = 'processing'
        elif bg_status == 'error':
            status = 'error'
        else:
            status = 'new'

        items.append({
            'filename': filename,
            'filepath': str(filepath),
            'date': file_date,
            'date_display': format_swedish_date(file_date),
            'status': status,
            'source': source,
            'id': db_info['id'] if db_info else None,
            'transcript': db_info['transcript'] if db_info else None,
            'preview': (db_info['transcript'][:200] + '...') if db_info and db_info['transcript'] and len(db_info['transcript']) > 200 else (db_info['transcript'] if db_info else None),
            'duration': db_info['duration'] if db_info else None,
            'transcribed_at': db_info['transcribed_at'] if db_info else None,
        })

    # Add DB-only entries (transcribed files no longer on disk)
    for filename, db_info in transcribed.items():
        if filename not in seen_filenames:
            file_date = parse_filename_timestamp(filename)
            # Guess source from file extension
            src = 'input' if not filename.endswith('.m4a') else 'voice'
            items.append({
                'filename': filename,
                'filepath': '',
                'date': file_date,
                'date_display': format_swedish_date(file_date),
                'status': 'transcribed',
                'source': src,
                'id': db_info['id'],
                'transcript': db_info['transcript'],
                'preview': (db_info['transcript'][:200] + '...') if db_info['transcript'] and len(db_info['transcript']) > 200 else db_info['transcript'],
                'duration': db_info['duration'],
                'transcribed_at': db_info['transcribed_at'],
            })

    items.sort(key=lambda x: x['date'] or datetime.min, reverse=True)
    return items


@app.route('/')
def index():
    """Main page - list all voice memos."""
    search = request.args.get('q', '').strip()
    filter_mode = request.args.get('filter', 'all')  # all, transcribed, new
    page_size = 50
    show = int(request.args.get('show', page_size))

    all_items = list_all_voice_memos()

    # Apply filter
    if filter_mode == 'transcribed':
        items = [i for i in all_items if i['status'] == 'transcribed' and i['source'] == 'voice']
    elif filter_mode == 'new':
        items = [i for i in all_items if i['status'] != 'transcribed' and i['source'] == 'voice']
    elif filter_mode == 'input':
        items = [i for i in all_items if i['source'] == 'input']
    else:
        items = [i for i in all_items if i['source'] == 'voice']

    # Apply search
    if search:
        search_lower = search.lower()
        items = [i for i in items if
                 search_lower in i['filename'].lower() or
                 (i['transcript'] and search_lower in i['transcript'].lower())]

    voice_items = [i for i in all_items if i['source'] == 'voice']
    input_items = [i for i in all_items if i['source'] == 'input']
    counts = {
        'all': len(voice_items),
        'transcribed': len([i for i in voice_items if i['status'] == 'transcribed']),
        'new': len([i for i in voice_items if i['status'] != 'transcribed']),
        'input': len(input_items),
    }

    total_items = len(items)
    has_more = total_items > show
    items = items[:show]

    return render_template('index.html',
                           items=items,
                           search=search,
                           filter_mode=filter_mode,
                           counts=counts,
                           has_more=has_more,
                           show=show,
                           page_size=page_size,
                           total_items=total_items)


@app.route('/transcript/<int:transcript_id>')
def view_transcript(transcript_id):
    """View a single transcript."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transcripts WHERE id = ?", (transcript_id,))
    t = cursor.fetchone()
    conn.close()

    if not t:
        abort(404)

    transcript = {
        'id': t['id'],
        'filename': t['filename'],
        'transcript': t['transcript'],
        'duration': format_duration(t['duration_seconds']),
        'date': format_date(t['transcribed_at']),
        'original_path': t['original_path']
    }

    return render_template('transcript.html', transcript=transcript)


@app.route('/audio/<int:transcript_id>')
def serve_audio(transcript_id):
    """Serve audio file by transcript ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT original_path FROM transcripts WHERE id = ?", (transcript_id,))
    result = cursor.fetchone()
    conn.close()

    if not result:
        abort(404)

    audio_path = Path(result['original_path'])
    if not audio_path.exists():
        abort(404)

    return send_file(audio_path, mimetype='audio/mp4')


@app.route('/audio/file/<path:filename>')
def serve_audio_by_filename(filename):
    """Serve audio file directly from Voice Memos folder."""
    audio_path = VOICE_MEMOS_DIR / filename
    if not audio_path.exists():
        abort(404)
    return send_file(audio_path, mimetype='audio/mp4')


@app.route('/api/transcribe', methods=['POST'])
def api_transcribe():
    """Start background transcription of a file."""
    data = request.get_json()
    filename = data.get('filename')
    if not filename:
        return jsonify({'error': 'filename required'}), 400

    filepath = VOICE_MEMOS_DIR / filename
    if not filepath.exists():
        return jsonify({'error': 'file not found'}), 404

    with _transcription_lock:
        if _transcription_status.get(filename) == 'processing':
            return jsonify({'status': 'already_processing'})
        _transcription_status[filename] = 'processing'

    thread = threading.Thread(target=_bg_transcribe, args=(filepath, filename), daemon=True)
    thread.start()

    return jsonify({'status': 'started'})


@app.route('/api/status/<path:filename>')
def api_status(filename):
    """Check transcription status for a file."""
    with _transcription_lock:
        status = _transcription_status.get(filename)

    if status:
        return jsonify({'status': status})

    # Check DB
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM transcripts WHERE filename = ?", (filename,))
    result = cursor.fetchone()
    conn.close()

    if result:
        return jsonify({'status': 'done', 'id': result['id']})

    return jsonify({'status': 'new'})


def _bg_transcribe(filepath, filename):
    """Run transcription in background thread."""
    try:
        from watcher import process_audio_file
        process_audio_file(filepath)
        with _transcription_lock:
            _transcription_status[filename] = 'done'
    except Exception as e:
        print(f"Background transcription error: {e}")
        with _transcription_lock:
            _transcription_status[filename] = 'error'


@app.route('/api/transcribe_batch', methods=['POST'])
def api_transcribe_batch():
    """Start batch transcription of oldest untranscribed memos."""
    data = request.get_json() or {}
    limit = min(int(data.get('limit', 10)), 50)

    if _batch_state['running']:
        return jsonify({'error': 'Batch redan igång'}), 409

    # Find untranscribed files (newest first among untranscribed)
    all_items = list_all_voice_memos()
    untranscribed = [i for i in all_items if i['status'] == 'new']
    # Take the newest N untranscribed
    to_process = untranscribed[:limit]

    if not to_process:
        return jsonify({'error': 'Inga otranskriberade memon'}), 404

    _batch_state['running'] = True
    _batch_state['total'] = len(to_process)
    _batch_state['done'] = 0
    _batch_state['current'] = ''

    filenames = [item['filename'] for item in to_process]
    thread = threading.Thread(target=_bg_batch_transcribe, args=(filenames,), daemon=True)
    thread.start()

    return jsonify({'status': 'started', 'total': len(to_process)})


@app.route('/api/batch_status')
def api_batch_status():
    """Check batch transcription progress."""
    return jsonify({
        'running': _batch_state['running'],
        'total': _batch_state['total'],
        'done': _batch_state['done'],
        'current': _batch_state['current'],
    })


def _bg_batch_transcribe(filenames):
    """Run batch transcription sequentially in background."""
    try:
        from watcher import process_audio_file
        for i, filename in enumerate(filenames):
            filepath = VOICE_MEMOS_DIR / filename
            if not filepath.exists():
                # Check input folder too
                filepath = INPUT_DIR / filename
            if not filepath.exists():
                continue
            _batch_state['current'] = filename
            try:
                process_audio_file(filepath)
            except Exception as e:
                print(f"Batch transcription error for {filename}: {e}")
            _batch_state['done'] = i + 1
    finally:
        _batch_state['running'] = False
        _batch_state['current'] = ''


@app.route('/api/transcripts')
def api_transcripts():
    """API endpoint for transcripts."""
    search = request.args.get('q', '').strip()

    conn = get_db()
    cursor = conn.cursor()

    if search:
        cursor.execute("""
            SELECT * FROM transcripts
            WHERE transcript LIKE ? OR filename LIKE ?
            ORDER BY transcribed_at DESC
        """, (f'%{search}%', f'%{search}%'))
    else:
        cursor.execute("SELECT * FROM transcripts ORDER BY transcribed_at DESC")

    transcripts = [dict(t) for t in cursor.fetchall()]
    conn.close()

    return jsonify(transcripts)


@app.route('/api/transcript/<int:transcript_id>', methods=['DELETE'])
def delete_transcript(transcript_id):
    """Delete a transcript."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT filename FROM transcripts WHERE id = ?", (transcript_id,))
    result = cursor.fetchone()

    if not result:
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    transcript_file = TRANSCRIPTS_DIR / f"{Path(result['filename']).stem}.txt"
    if transcript_file.exists():
        transcript_file.unlink()

    cursor.execute("DELETE FROM transcripts WHERE id = ?", (transcript_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True})


if __name__ == '__main__':
    print(f"Starting server at http://{FLASK_HOST}:{FLASK_PORT}")
    print(f"Access from other devices: http://YOUR_MAC_IP:{FLASK_PORT}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False)
