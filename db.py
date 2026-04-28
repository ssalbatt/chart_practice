import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), 'chart_practice.db')

DEFAULT_SETTINGS = '{"ma":[5,20,60,120,200],"active":{"vol":true,"ma20":true,"ma60":true}}'


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            pw_hash  TEXT NOT NULL,
            settings TEXT DEFAULT '{"ma":[5,20,60,120,200],"active":{"vol":true,"ma20":true,"ma60":true}}',
            created  TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  INTEGER NOT NULL,
            ticker   TEXT NOT NULL,
            name     TEXT DEFAULT "",
            interval TEXT NOT NULL,
            candles  TEXT NOT NULL,
            hide_idx INTEGER NOT NULL,
            total    INTEGER NOT NULL,
            status   TEXT DEFAULT "active",
            note     TEXT DEFAULT "",
            score    INTEGER,
            correct  INTEGER DEFAULT 0,
            wrong    INTEGER DEFAULT 0,
            ambig    INTEGER DEFAULT 0,
            created  TEXT DEFAULT CURRENT_TIMESTAMP,
            ended    TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS reveals (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            sess_id INTEGER NOT NULL,
            num     INTEGER NOT NULL,
            shown   INTEGER NOT NULL,
            trend   TEXT,
            conf    TEXT,
            eval    TEXT,
            note    TEXT DEFAULT "",
            created TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sess_id) REFERENCES sessions(id)
        );
    ''')
    db.commit()
    db.close()
