#!/usr/bin/env python3
"""
Flask web app for viewing and searching transcripts.
"""
import sqlite3
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, abort

import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import DB_PATH, TRANSCRIPTS_DIR, VOICE_MEMOS_DIR, FLASK_HOST, FLASK_PORT

app = Flask(__name__)


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
    import re
    match = re.match(r'^(\d{8})\s*(\d{6})', filename)
    if match:
        try:
            date_str = match.group(1) + match.group(2)
            return datetime.strptime(date_str, "%Y%m%d%H%M%S")
        except ValueError:
            pass
    return None


@app.route('/')
def index():
    """Main page - list all transcripts."""
    search = request.args.get('q', '').strip()
    sort = request.args.get('sort', 'filename')  # filename or transcribed

    conn = get_db()
    cursor = conn.cursor()

    if search:
        cursor.execute("""
            SELECT * FROM transcripts
            WHERE transcript LIKE ? OR filename LIKE ?
        """, (f'%{search}%', f'%{search}%'))
    else:
        cursor.execute("SELECT * FROM transcripts")

    transcripts = cursor.fetchall()
    conn.close()

    # Format for display
    items = []
    for t in transcripts:
        filename_ts = parse_filename_timestamp(t['filename'])
        items.append({
            'id': t['id'],
            'filename': t['filename'],
            'transcript': t['transcript'],
            'preview': t['transcript'][:200] + '...' if len(t['transcript'] or '') > 200 else t['transcript'],
            'duration': format_duration(t['duration_seconds']),
            'date': format_date(t['transcribed_at']),
            'filename_date': filename_ts.strftime("%Y-%m-%d %H:%M") if filename_ts else '',
            'filename_ts': filename_ts,
            'transcribed_at': t['transcribed_at'],
            'original_path': t['original_path']
        })

    # Sort based on user preference
    if sort == 'filename':
        items.sort(key=lambda x: x['filename_ts'] or datetime.min, reverse=True)
    else:
        items.sort(key=lambda x: x['transcribed_at'] or '', reverse=True)

    return render_template('index.html', transcripts=items, search=search, sort=sort)


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
    """Serve the original audio file."""
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

    # Get filename first
    cursor.execute("SELECT filename FROM transcripts WHERE id = ?", (transcript_id,))
    result = cursor.fetchone()

    if not result:
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    # Delete transcript file
    transcript_file = TRANSCRIPTS_DIR / f"{Path(result['filename']).stem}.txt"
    if transcript_file.exists():
        transcript_file.unlink()

    # Delete from database
    cursor.execute("DELETE FROM transcripts WHERE id = ?", (transcript_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True})


if __name__ == '__main__':
    print(f"Starting server at http://{FLASK_HOST}:{FLASK_PORT}")
    print(f"Access from other devices: http://YOUR_MAC_IP:{FLASK_PORT}")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False)
