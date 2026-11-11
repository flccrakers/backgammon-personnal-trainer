"""SQLite : connexion, migrations numérotées (PRAGMA user_version) et sauvegarde."""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

MIGRATIONS: list[str] = [
    # 1
    """
    CREATE TABLE source_file (
        id INTEGER PRIMARY KEY,
        canonical_path TEXT NOT NULL,
        content_sha256 TEXT NOT NULL,
        byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
        mtime_utc TEXT,
        status TEXT NOT NULL CHECK (status IN
            ('discovered','imported','analyzed','failed','unsupported','duplicate')),
        last_error TEXT,
        superseded INTEGER NOT NULL DEFAULT 0,
        imported_at_utc TEXT,
        UNIQUE (canonical_path, content_sha256)
    );
    CREATE TABLE match_record (
        id INTEGER PRIMARY KEY,
        source_file_id INTEGER NOT NULL REFERENCES source_file(id),
        content_sha256 TEXT NOT NULL UNIQUE,
        source_match_key TEXT,
        player_x TEXT, player_o TEXT,
        match_date TEXT,
        match_length INTEGER,
        raw_metadata TEXT,
        game_count INTEGER
    );
    CREATE TABLE analysis_run (
        id INTEGER PRIMARY KEY,
        match_id INTEGER NOT NULL REFERENCES match_record(id),
        engine_name TEXT NOT NULL,
        engine_version TEXT NOT NULL,
        profile_fingerprint TEXT NOT NULL,
        config_json TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('running','complete','failed')),
        decisions_seen INTEGER,
        started_at_utc TEXT, completed_at_utc TEXT,
        error_text TEXT,
        UNIQUE (match_id, profile_fingerprint)
    );
    CREATE TABLE exercise (
        id INTEGER PRIMARY KEY,
        logical_key TEXT NOT NULL,
        kind TEXT NOT NULL CHECK (kind IN ('move','cube')),
        match_id INTEGER NOT NULL REFERENCES match_record(id),
        analysis_run_id INTEGER NOT NULL REFERENCES analysis_run(id),
        game_index INTEGER NOT NULL,
        action_index INTEGER NOT NULL,
        player_name TEXT NOT NULL,
        player_color TEXT NOT NULL CHECK (player_color IN ('X','O')),
        board_schema_version INTEGER NOT NULL,
        position_json TEXT NOT NULL,
        dice_json TEXT,
        cube_value INTEGER NOT NULL DEFAULT 1,
        cube_owner TEXT CHECK (cube_owner IN ('me','opp') OR cube_owner IS NULL),
        offered_cube INTEGER,
        score_me INTEGER, score_opp INTEGER, match_length INTEGER, crawford INTEGER,
        played_json TEXT NOT NULL,
        best_json TEXT NOT NULL,
        accepted_json TEXT NOT NULL,
        equity_loss REAL,
        metric TEXT,
        classification TEXT NOT NULL CHECK (classification = 'very bad'),
        extra_json TEXT,
        UNIQUE (analysis_run_id, logical_key)
    );
    CREATE INDEX idx_exercise_match ON exercise(match_id);
    CREATE INDEX idx_exercise_player ON exercise(player_name);
    CREATE INDEX idx_match_source ON match_record(source_file_id);
    CREATE TABLE exercise_progress (
        logical_key TEXT PRIMARY KEY,
        state TEXT NOT NULL DEFAULT 'new' CHECK (state IN ('new','in_progress','correct','skipped')),
        attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
        last_attempt_at_utc TEXT,
        updated_at_utc TEXT NOT NULL
    );
    """,
    # 2 : sessions d'entraînement
    """
    CREATE TABLE training_session (
        id INTEGER PRIMARY KEY,
        started_at_utc TEXT NOT NULL,
        ended_at_utc TEXT,
        status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','finished','abandoned')),
        filters_json TEXT NOT NULL,
        items_json TEXT NOT NULL,
        total INTEGER NOT NULL CHECK (total >= 0)
    );
    CREATE TABLE session_event (
        id INTEGER PRIMARY KEY,
        session_id INTEGER NOT NULL REFERENCES training_session(id) ON DELETE CASCADE,
        exercise_id INTEGER NOT NULL,
        logical_key TEXT NOT NULL,
        event TEXT NOT NULL CHECK (event IN ('attempt','reveal','skip')),
        correct INTEGER CHECK (correct IN (0,1) OR correct IS NULL),
        answer_json TEXT,
        created_at_utc TEXT NOT NULL
    );
    CREATE INDEX idx_session_event ON session_event(session_id, exercise_id);
    """,
    # 3 : toutes les classes d'erreur gnubg (douteux, mauvais, très mauvais)
    """
    CREATE TABLE exercise_new (
        id INTEGER PRIMARY KEY,
        logical_key TEXT NOT NULL,
        kind TEXT NOT NULL CHECK (kind IN ('move','cube')),
        match_id INTEGER NOT NULL REFERENCES match_record(id),
        analysis_run_id INTEGER NOT NULL REFERENCES analysis_run(id),
        game_index INTEGER NOT NULL,
        action_index INTEGER NOT NULL,
        player_name TEXT NOT NULL,
        player_color TEXT NOT NULL CHECK (player_color IN ('X','O')),
        board_schema_version INTEGER NOT NULL,
        position_json TEXT NOT NULL,
        dice_json TEXT,
        cube_value INTEGER NOT NULL DEFAULT 1,
        cube_owner TEXT CHECK (cube_owner IN ('me','opp') OR cube_owner IS NULL),
        offered_cube INTEGER,
        score_me INTEGER, score_opp INTEGER, match_length INTEGER, crawford INTEGER,
        played_json TEXT NOT NULL,
        best_json TEXT NOT NULL,
        accepted_json TEXT NOT NULL,
        equity_loss REAL,
        metric TEXT,
        classification TEXT NOT NULL CHECK (classification IN ('doubtful','bad','very bad')),
        extra_json TEXT,
        UNIQUE (analysis_run_id, logical_key)
    );
    INSERT INTO exercise_new SELECT * FROM exercise;
    DROP TABLE exercise;
    ALTER TABLE exercise_new RENAME TO exercise;
    CREATE INDEX idx_exercise_match ON exercise(match_id);
    CREATE INDEX idx_exercise_player ON exercise(player_name);
    CREATE INDEX idx_exercise_class ON exercise(classification);
    """,
]

SCHEMA_VERSION = len(MIGRATIONS)


def connect(path: str | Path, migrate: bool = True) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    if migrate:
        _migrate(conn, path)
    return conn


def _migrate(conn: sqlite3.Connection, path: Path) -> None:
    cur = conn.execute("PRAGMA user_version").fetchone()[0]
    if cur > SCHEMA_VERSION:
        raise RuntimeError(f"Base en version {cur}, application en version {SCHEMA_VERSION} : mise à jour requise.")
    if cur == SCHEMA_VERSION:
        return
    if cur > 0 and path.exists():
        conn.commit()
        shutil.copy2(path, path.with_suffix(f".bak-v{cur}"))
    for v in range(cur, SCHEMA_VERSION):
        conn.executescript("BEGIN;\n" + MIGRATIONS[v] + f"\nPRAGMA user_version = {v + 1};\nCOMMIT;")
