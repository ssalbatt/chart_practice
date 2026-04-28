"""
Database abstraction layer.
- Local dev  : SQLite  (no DATABASE_URL env var)
- Production : PostgreSQL via DATABASE_URL env var (e.g. Neon)
"""
import os, json, sqlite3

DATABASE_URL = os.environ.get('DATABASE_URL', '')
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chart_practice.db')

_DEFAULT_SETTINGS = json.dumps({
    "ma": [5, 20, 60, 120, 200],
    "active": {"vol": True, "ma20": True, "ma60": True}
})

SQLITE_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS users (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    pw_hash  TEXT NOT NULL,
    settings TEXT DEFAULT '{_DEFAULT_SETTINGS}',
    created  TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sessions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL,
    ticker   TEXT NOT NULL,
    name     TEXT DEFAULT '',
    interval TEXT NOT NULL,
    candles  TEXT NOT NULL,
    hide_idx INTEGER NOT NULL,
    total    INTEGER NOT NULL,
    status   TEXT DEFAULT 'active',
    note     TEXT DEFAULT '',
    score    INTEGER,
    correct  INTEGER DEFAULT 0,
    wrong    INTEGER DEFAULT 0,
    ambig    INTEGER DEFAULT 0,
    created  TEXT DEFAULT CURRENT_TIMESTAMP,
    ended    TEXT
);
CREATE TABLE IF NOT EXISTS reveals (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    sess_id INTEGER NOT NULL,
    num     INTEGER NOT NULL,
    shown   INTEGER NOT NULL,
    trend   TEXT,
    conf    TEXT,
    eval    TEXT,
    note    TEXT DEFAULT '',
    created TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

PG_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS users (
    id       SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    pw_hash  TEXT NOT NULL,
    settings TEXT DEFAULT '{_DEFAULT_SETTINGS}',
    created  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sessions (
    id       SERIAL PRIMARY KEY,
    user_id  INTEGER NOT NULL,
    ticker   TEXT NOT NULL,
    name     TEXT DEFAULT '',
    interval TEXT NOT NULL,
    candles  TEXT NOT NULL,
    hide_idx INTEGER NOT NULL,
    total    INTEGER NOT NULL,
    status   TEXT DEFAULT 'active',
    note     TEXT DEFAULT '',
    score    INTEGER,
    correct  INTEGER DEFAULT 0,
    wrong    INTEGER DEFAULT 0,
    ambig    INTEGER DEFAULT 0,
    created  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended    TIMESTAMP
);
CREATE TABLE IF NOT EXISTS reveals (
    id      SERIAL PRIMARY KEY,
    sess_id INTEGER NOT NULL,
    num     INTEGER NOT NULL,
    shown   INTEGER NOT NULL,
    trend   TEXT,
    conf    TEXT,
    eval    TEXT,
    note    TEXT DEFAULT '',
    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class DB:
    """Thin wrapper that normalizes SQLite and PostgreSQL differences."""

    def __init__(self):
        if DATABASE_URL:
            import psycopg2
            import psycopg2.extras
            self._conn = psycopg2.connect(DATABASE_URL,
                                          cursor_factory=psycopg2.extras.RealDictCursor)
            self._pg = True
        else:
            self._conn = sqlite3.connect(DB_PATH)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute('PRAGMA foreign_keys = ON')
            self._pg = False

    def _q(self, sql):
        return sql.replace('?', '%s') if self._pg else sql

    def execute(self, sql, params=()):
        if self._pg:
            cur = self._conn.cursor()
            cur.execute(self._q(sql), params)
            return cur
        return self._conn.execute(sql, params)

    def fetchone(self, sql, params=()):
        row = self.execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetchall(self, sql, params=()):
        return [dict(r) for r in self.execute(sql, params).fetchall()]

    def insert(self, sql, params=()):
        """Execute INSERT, return new row id."""
        if self._pg:
            cur = self._conn.cursor()
            cur.execute(self._q(sql) + ' RETURNING id', params)
            self._conn.commit()
            return cur.fetchone()['id']
        self._conn.execute(sql, params)
        self._conn.commit()
        return self._conn.execute('SELECT last_insert_rowid()').fetchone()[0]

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


_initialized = False


def get_db():
    return DB()


def init_db():
    global _initialized
    db = get_db()
    try:
        if db._pg:
            for stmt in PG_SCHEMA.split(';'):
                stmt = stmt.strip()
                if stmt:
                    db.execute(stmt)
        else:
            db._conn.executescript(SQLITE_SCHEMA)
        db.commit()
    finally:
        db.close()
    _initialized = True


def ensure_init():
    global _initialized
    if not _initialized:
        init_db()
