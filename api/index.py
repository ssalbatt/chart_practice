"""
Vercel serverless entry point (Flask WSGI).
Handles all /api/* routes except /api/chart (handled by chart.py).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json, time, hmac, hashlib, base64
from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db, ensure_init

app = Flask(__name__)
SECRET = os.environ.get('JWT_SECRET', 'chart-practice-dev-secret')


# ── token helpers ─────────────────────────────────────────────────────────────
def make_token(uid):
    payload = base64.b64encode(
        json.dumps({'uid': uid, 'exp': time.time() + 86400 * 30}).encode()
    ).decode()
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_token(tok):
    try:
        payload_b64, sig = tok.rsplit('.', 1)
        expected = hmac.new(SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(base64.b64decode(payload_b64).decode())
        return data['uid'] if data['exp'] > time.time() else None
    except Exception:
        return None


def auth_uid():
    h = request.headers.get('Authorization', '')
    return verify_token(h[7:]) if h.startswith('Bearer ') else None


def unauth():
    return jsonify({'error': '로그인 필요'}), 401


# ── auth ──────────────────────────────────────────────────────────────────────
@app.route('/api/register', methods=['POST'])
def register():
    ensure_init()
    d = request.json or {}
    u, p = d.get('username', '').strip(), d.get('password', '')
    if not u or not p:
        return jsonify({'error': '아이디와 비밀번호를 입력하세요'}), 400
    if len(u) < 2 or len(u) > 30:
        return jsonify({'error': '아이디는 2~30자'}), 400
    if len(p) < 4:
        return jsonify({'error': '비밀번호 4자 이상'}), 400
    with get_db() as db:
        try:
            uid = db.insert('INSERT INTO users (username, pw_hash) VALUES (?,?)',
                            (u, generate_password_hash(p)))
            return jsonify({'token': make_token(uid), 'username': u})
        except Exception as e:
            return jsonify({'error': '이미 사용 중인 아이디' if 'unique' in str(e).lower() else str(e)}), 400


@app.route('/api/login', methods=['POST'])
def login():
    ensure_init()
    d = request.json or {}
    u, p = d.get('username', '').strip(), d.get('password', '')
    with get_db() as db:
        row = db.fetchone('SELECT id, pw_hash FROM users WHERE username=?', (u,))
        if not row or not check_password_hash(row['pw_hash'], p):
            return jsonify({'error': '아이디 또는 비밀번호 오류'}), 401
        return jsonify({'token': make_token(row['id']), 'username': u})


@app.route('/api/me')
def me():
    ensure_init()
    uid = auth_uid()
    if not uid:
        return unauth()
    with get_db() as db:
        row = db.fetchone('SELECT username, settings FROM users WHERE id=?', (uid,))
        if not row:
            return jsonify({'error': '사용자 없음'}), 404
        return jsonify({'username': row['username'],
                        'settings': json.loads(row['settings'] or '{}')})


@app.route('/api/me/settings', methods=['PATCH'])
def update_settings():
    ensure_init()
    uid = auth_uid()
    if not uid:
        return unauth()
    data = request.json or {}
    with get_db() as db:
        row = db.fetchone('SELECT settings FROM users WHERE id=?', (uid,))
        s = json.loads(row['settings'] or '{}')
        s.update(data)
        db.execute('UPDATE users SET settings=? WHERE id=?', (json.dumps(s), uid))
        db.commit()
        return jsonify({'settings': s})


# ── sessions ──────────────────────────────────────────────────────────────────
@app.route('/api/sessions', methods=['GET', 'POST'])
def sessions():
    ensure_init()
    uid = auth_uid()
    if not uid:
        return unauth()
    with get_db() as db:
        if request.method == 'GET':
            rows = db.fetchall('''
                SELECT id, ticker, name, interval, hide_idx, total,
                       status, score, correct, wrong, ambig, created, ended
                FROM sessions WHERE user_id=? ORDER BY created DESC LIMIT 100
            ''', (uid,))
            return jsonify(rows)

        d = request.json or {}
        sid = db.insert('''
            INSERT INTO sessions (user_id, ticker, name, interval, candles, hide_idx, total)
            VALUES (?,?,?,?,?,?,?)
        ''', (uid, d['ticker'], d.get('name', ''), d['interval'],
              json.dumps(d['candles']), d['hide_idx'], d['total']))
        return jsonify({'id': sid}), 201


@app.route('/api/sessions/<int:sid>', methods=['GET', 'PATCH'])
def session_detail(sid):
    ensure_init()
    uid = auth_uid()
    if not uid:
        return unauth()
    with get_db() as db:
        s = db.fetchone('SELECT * FROM sessions WHERE id=? AND user_id=?', (sid, uid))
        if not s:
            return jsonify({'error': '세션 없음'}), 404

        if request.method == 'GET':
            s['candles'] = json.loads(s['candles'])
            s['reveals'] = db.fetchall(
                'SELECT * FROM reveals WHERE sess_id=? ORDER BY num', (sid,))
            return jsonify(s)

        d = request.json or {}
        allowed = ['note', 'score', 'status', 'correct', 'wrong', 'ambig', 'ended']
        fields, vals = [], []
        for k in allowed:
            if k in d:
                fields.append(f'{k}=?')
                vals.append(d[k])
        if fields:
            db.execute(f'UPDATE sessions SET {",".join(fields)} WHERE id=?', [*vals, sid])
            db.commit()
        return jsonify({'ok': True})


@app.route('/api/sessions/<int:sid>/reveals', methods=['POST'])
def add_reveal(sid):
    ensure_init()
    uid = auth_uid()
    if not uid:
        return unauth()
    d = request.json or {}
    with get_db() as db:
        if not db.fetchone('SELECT id FROM sessions WHERE id=? AND user_id=?', (sid, uid)):
            return jsonify({'error': '세션 없음'}), 404
        count = db.fetchone('SELECT COUNT(*) as c FROM reveals WHERE sess_id=?', (sid,))
        num = (count['c'] or 0) + 1
        db.insert('''
            INSERT INTO reveals (sess_id, num, shown, trend, conf, eval, note)
            VALUES (?,?,?,?,?,?,?)
        ''', (sid, num, d.get('shown', 0), d.get('trend'),
              d.get('conf'), d.get('eval'), d.get('note', '')))
        ev = d.get('eval')
        if ev in ('correct', 'wrong', 'ambig'):
            db.execute(f'UPDATE sessions SET {ev}={ev}+1 WHERE id=?', (sid,))
            db.commit()
        return jsonify({'num': num}), 201
