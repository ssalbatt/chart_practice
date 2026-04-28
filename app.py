"""로컬 개발 서버"""
from flask import Flask, send_file, request, jsonify
import json, os, time, hmac, hashlib, base64
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db, init_db
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))
from chart import process

app = Flask(__name__)
SECRET = os.environ.get('JWT_SECRET', 'chart-practice-local-secret')


# ── auth helpers ─────────────────────────────────────────────────────────────
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
    header = request.headers.get('Authorization', '')
    return verify_token(header[7:]) if header.startswith('Bearer ') else None


def need_auth():
    return jsonify({'error': '로그인 필요'}), 401


# ── static ────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_file('index.html')


# ── auth ──────────────────────────────────────────────────────────────────────
@app.route('/api/register', methods=['POST'])
def register():
    d = request.json or {}
    u, p = d.get('username', '').strip(), d.get('password', '')
    if not u or not p:
        return jsonify({'error': '아이디와 비밀번호를 입력하세요'}), 400
    if len(u) < 2 or len(u) > 30:
        return jsonify({'error': '아이디는 2~30자'}), 400
    if len(p) < 4:
        return jsonify({'error': '비밀번호 4자 이상'}), 400
    db = get_db()
    try:
        db.execute('INSERT INTO users (username, pw_hash) VALUES (?,?)',
                   (u, generate_password_hash(p)))
        db.commit()
        uid = db.execute('SELECT id FROM users WHERE username=?', (u,)).fetchone()['id']
        return jsonify({'token': make_token(uid), 'username': u})
    except Exception as e:
        return jsonify({'error': '이미 사용 중인 아이디' if 'UNIQUE' in str(e) else str(e)}), 400
    finally:
        db.close()


@app.route('/api/login', methods=['POST'])
def login():
    d = request.json or {}
    u, p = d.get('username', '').strip(), d.get('password', '')
    db = get_db()
    try:
        row = db.execute('SELECT id, pw_hash FROM users WHERE username=?', (u,)).fetchone()
        if not row or not check_password_hash(row['pw_hash'], p):
            return jsonify({'error': '아이디 또는 비밀번호 오류'}), 401
        return jsonify({'token': make_token(row['id']), 'username': u})
    finally:
        db.close()


@app.route('/api/me')
def me():
    uid = auth_uid()
    if not uid:
        return need_auth()
    db = get_db()
    try:
        row = db.execute('SELECT username, settings FROM users WHERE id=?', (uid,)).fetchone()
        return jsonify({'username': row['username'],
                        'settings': json.loads(row['settings'] or '{}')})
    finally:
        db.close()


@app.route('/api/me/settings', methods=['PATCH'])
def update_settings():
    uid = auth_uid()
    if not uid:
        return need_auth()
    data = request.json or {}
    db = get_db()
    try:
        row = db.execute('SELECT settings FROM users WHERE id=?', (uid,)).fetchone()
        s = json.loads(row['settings'] or '{}')
        s.update(data)
        db.execute('UPDATE users SET settings=? WHERE id=?', (json.dumps(s), uid))
        db.commit()
        return jsonify({'settings': s})
    finally:
        db.close()


# ── chart data ────────────────────────────────────────────────────────────────
@app.route('/api/chart')
def chart():
    params = {k: [v] for k, v in request.args.items()}
    result, status = process(params)
    return jsonify(result), status


# ── sessions ──────────────────────────────────────────────────────────────────
@app.route('/api/sessions', methods=['GET', 'POST'])
def sessions():
    uid = auth_uid()
    if not uid:
        return need_auth()
    db = get_db()
    try:
        if request.method == 'GET':
            rows = db.execute('''
                SELECT id, ticker, name, interval, hide_idx, total,
                       status, score, correct, wrong, ambig, created, ended
                FROM sessions WHERE user_id=? ORDER BY created DESC LIMIT 100
            ''', (uid,)).fetchall()
            return jsonify([dict(r) for r in rows])

        d = request.json or {}
        db.execute('''
            INSERT INTO sessions (user_id, ticker, name, interval, candles, hide_idx, total)
            VALUES (?,?,?,?,?,?,?)
        ''', (uid, d['ticker'], d.get('name', ''), d['interval'],
              json.dumps(d['candles']), d['hide_idx'], d['total']))
        db.commit()
        sid = db.execute('SELECT last_insert_rowid() as id').fetchone()['id']
        return jsonify({'id': sid}), 201
    finally:
        db.close()


@app.route('/api/sessions/<int:sid>', methods=['GET', 'PATCH'])
def session_detail(sid):
    uid = auth_uid()
    if not uid:
        return need_auth()
    db = get_db()
    try:
        s = db.execute('SELECT * FROM sessions WHERE id=? AND user_id=?', (sid, uid)).fetchone()
        if not s:
            return jsonify({'error': '세션 없음'}), 404

        if request.method == 'GET':
            result = dict(s)
            result['candles'] = json.loads(s['candles'])
            result['reveals'] = [dict(r) for r in
                db.execute('SELECT * FROM reveals WHERE sess_id=? ORDER BY num', (sid,)).fetchall()]
            return jsonify(result)

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
    finally:
        db.close()


@app.route('/api/sessions/<int:sid>/reveals', methods=['POST'])
def add_reveal(sid):
    uid = auth_uid()
    if not uid:
        return need_auth()
    d = request.json or {}
    db = get_db()
    try:
        if not db.execute('SELECT id FROM sessions WHERE id=? AND user_id=?', (sid, uid)).fetchone():
            return jsonify({'error': '세션 없음'}), 404
        num = (db.execute('SELECT COUNT(*) as c FROM reveals WHERE sess_id=?',
                          (sid,)).fetchone()['c'] or 0) + 1
        db.execute('''
            INSERT INTO reveals (sess_id, num, shown, trend, conf, eval, note)
            VALUES (?,?,?,?,?,?,?)
        ''', (sid, num, d.get('shown', 0), d.get('trend'), d.get('conf'),
              d.get('eval'), d.get('note', '')))
        ev = d.get('eval')
        if ev in ('correct', 'wrong', 'ambig'):
            db.execute(f'UPDATE sessions SET {ev}={ev}+1 WHERE id=?', (sid,))
        db.commit()
        return jsonify({'num': num}), 201
    finally:
        db.close()


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5050)
