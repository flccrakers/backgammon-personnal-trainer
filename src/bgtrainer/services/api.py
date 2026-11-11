"""Façade de services : utilisable sans GUI (scan, analyse, exercices)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..analysis.builder import build_exercises
from ..analysis.coach import cube_conflict, explain_cube, explain_move, rules_conflict
from ..config.settings import ConfigError, Settings
from ..domain.board import Position, apply_steps, legal_plays, next_steps
from ..engine import gnubg_adapter as eng
from ..formats.mat import MatError, parse_mat, sha256_file
from ..repositories import db

ProgressCb = Callable[[str, int, int], None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class FileReport:
    path: str
    status: str  # new|unchanged|modified|duplicate|failed|unsupported|retry
    analyzed: bool = False
    exercises: int = 0
    decisions: int = 0
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class ScanReport:
    files: list[FileReport] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for f in self.files if f.status == status)

    @property
    def up_to_date(self) -> bool:
        return all(f.status in ("unchanged", "duplicate") and not f.error for f in self.files)


@dataclass
class AttemptResult:
    correct: bool
    legal: bool
    message: str
    reveal: dict | None = None
    locked: bool = False


class TrainerService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self.conn = db.connect(settings.db_file)  # connexion du fil appelant
        self._local = threading.local()

    # ---------- profil d'analyse ----------
    def profile(self) -> dict:
        s = self.settings
        return {"plies": s.engine_plies, "classes": sorted(s.exercise_classes), "tol": s.near_equal_tolerance,
                "builder": 4, "script": 2}

    def profile_fingerprint(self, engine_version: str) -> str:
        raw = json.dumps({**self.profile(), "engine": engine_version}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _conn(self) -> sqlite3.Connection:
        """Connexion propre au fil courant (jamais partagée entre threads)."""
        if threading.current_thread() is threading.main_thread() and not hasattr(self._local, "c"):
            return self.conn
        c = getattr(self._local, "c", None)
        if c is None:
            c = self._local.c = db.connect(self.settings.db_file, migrate=False)
        return c

    # ---------- découverte ----------
    _force_retry = False

    def _retry_failed(self) -> bool:
        return self._force_retry or self.settings.scan_retry_failed

    def discover(self, root: Path | None = None) -> list[Path]:
        root = root or self.settings.check_mat_directory()
        it = root.rglob("*") if self.settings.include_subdirectories else root.glob("*")
        return sorted(p for p in it if p.is_file() and p.suffix.lower() == ".mat")

    # ---------- scan ----------
    def scan_sources(self, paths: list[Path] | None = None, analyze: bool = True,
                     progress: ProgressCb | None = None, cancel: threading.Event | None = None,
                     retry_failed: bool = False) -> ScanReport:
        files = paths if paths is not None else self.discover()
        engine = eng.probe(self.settings.engine_executable) if analyze else None
        fp = self.profile_fingerprint(engine.version) if engine else None
        report = ScanReport()
        self._cancel = cancel
        self._force_retry = retry_failed   # « relancer » : retente aussi les fichiers en échec
        self.scan_exercises = 0   # exercices créés pendant ce scan (lu par l'UI)
        todo: list[tuple[FileReport, Path, str]] = []
        for i, p in enumerate(files):
            if cancel and cancel.is_set():
                break
            fr = self._import_one(p)
            report.files.append(fr)
            if progress:
                progress("import", i + 1, len(files))
            if analyze and fr.status != "failed" and fr.status != "unsupported":
                mid = self._match_id_for(p)
                if mid and (not self._analysis_done(mid, fp) or
                            (fr.status in ("retry",) and self._retry_failed())):
                    todo.append((fr, p, fp))
        if progress and analyze:
            progress("analyse", 0, len(todo))
        if analyze and todo:
            done = 0
            with ThreadPoolExecutor(max_workers=self.settings.engine_workers) as ex:
                futs = {ex.submit(self._analyze_path, p, engine, f): fr for fr, p, f in todo}
                pending = set(futs)
                stopping: int | None = None   # nb d'analyses encore en cours au moment de l'annulation
                stopped = 0
                while pending:
                    finished, pending = wait(pending, timeout=0.3, return_when=FIRST_COMPLETED)
                    for fut in finished:
                        fr = futs[fut]
                        try:
                            r = fut.result()
                            fr.analyzed, fr.exercises, fr.decisions, fr.warnings = True, r[0], r[1], r[2]
                            self.scan_exercises += r[0]
                        except eng.ScanCancelled:
                            fr.status = "interrupted"
                        except Exception as e:  # noqa: BLE001 - échec local, scan continue
                            fr.error = f"{type(e).__name__}: {e}"[:500]
                            fr.status = "failed"
                        done += 1
                        if stopping is not None:
                            stopped += 1
                            if progress:
                                progress("annulation", stopped, stopping)
                        elif progress:
                            progress("analyse", done, len(futs))
                    if cancel and cancel.is_set() and stopping is None:
                        # annule les analyses pas encore démarrées ; seules celles en cours se terminent
                        pending = {f for f in pending if not f.cancel()}
                        stopping = len(pending)
                        if progress:
                            progress("annulation", 0, stopping)
        return report

    def recover_interrupted(self) -> int:
        """Au démarrage : oublie les analyses restées « en cours » (arrêt brutal). Elles seront refaites."""
        c = self._conn()
        with c:
            n = c.execute("DELETE FROM analysis_run WHERE status='running' AND id NOT IN (SELECT analysis_run_id FROM exercise)").rowcount
        return n

    def _import_one(self, p: Path) -> FileReport:
        c = self._conn()
        path = str(p.resolve())
        try:
            sha = sha256_file(p)
            st = p.stat()
        except OSError as e:
            return FileReport(path, "failed", error=f"illisible: {e}")
        prev = c.execute("SELECT * FROM source_file WHERE canonical_path=? ORDER BY id DESC LIMIT 1", (path,)).fetchone()
        same = c.execute("SELECT * FROM source_file WHERE canonical_path=? AND content_sha256=?", (path, sha)).fetchone()
        if same:
            if same["status"] == "failed" and self._retry_failed():
                status = "retry"
            elif same["status"] == "unsupported":
                return FileReport(path, "unsupported", error=same["last_error"])
            else:
                return FileReport(path, "unchanged" if same["status"] != "duplicate" else "duplicate")
            if status == "retry" and same["status"] == "failed":
                pass
        dup = c.execute("SELECT m.id FROM match_record m WHERE m.content_sha256=?", (sha,)).fetchone()
        try:
            mf = parse_mat(p)
        except MatError as e:
            with c:
                c.execute("""INSERT INTO source_file(canonical_path,content_sha256,byte_size,mtime_utc,status,last_error,imported_at_utc)
                             VALUES(?,?,?,?, 'unsupported',?,?)
                             ON CONFLICT(canonical_path,content_sha256) DO UPDATE SET status='unsupported', last_error=excluded.last_error""",
                          (path, sha, st.st_size, _mtime(st), str(e), _now()))
            return FileReport(path, "unsupported", error=str(e))
        status = "new" if not prev else "modified"
        with c:  # transaction
            if prev and prev["content_sha256"] != sha:
                c.execute("UPDATE source_file SET superseded=1 WHERE canonical_path=?", (path,))
            c.execute("""INSERT INTO source_file(canonical_path,content_sha256,byte_size,mtime_utc,status,imported_at_utc)
                         VALUES(?,?,?,?, ?,?)
                         ON CONFLICT(canonical_path,content_sha256) DO UPDATE SET status=excluded.status, last_error=NULL""",
                      (path, sha, st.st_size, _mtime(st), "duplicate" if dup else "imported", _now()))
            sid = c.execute("SELECT id FROM source_file WHERE canonical_path=? AND content_sha256=?", (path, sha)).fetchone()["id"]
            if dup:
                return FileReport(path, "duplicate")
            c.execute("""INSERT INTO match_record(source_file_id,content_sha256,source_match_key,player_x,player_o,match_date,match_length,raw_metadata,game_count)
                         VALUES(?,?,?,?,?,?,?,?,?)""",
                      (sid, sha, mf.match_id, mf.player1, mf.player2, mf.meta.get("EventDate"), mf.match_length,
                       json.dumps(mf.meta, ensure_ascii=False), len(mf.games)))
        return FileReport(path, status)

    def _match_id_for(self, p: Path) -> int | None:
        c = self._conn()
        sha = sha256_file(p)
        r = c.execute("SELECT id FROM match_record WHERE content_sha256=?", (sha,)).fetchone()
        return r["id"] if r else None

    def _analysis_done(self, match_id: int, fp: str) -> bool:
        r = self._conn().execute("SELECT status FROM analysis_run WHERE match_id=? AND profile_fingerprint=?", (match_id, fp)).fetchone()
        return bool(r and r["status"] == "complete")

    # ---------- analyse ----------
    _cancel: threading.Event | None = None
    scan_exercises: int = 0

    def _analyze_path(self, p: Path, engine: eng.EngineInfo, fp: str) -> tuple[int, int, list[str]]:
        c = self._conn()
        sha = sha256_file(p)
        m = c.execute("SELECT * FROM match_record WHERE content_sha256=?", (sha,)).fetchone()
        mid = m["id"]
        with c:
            c.execute("""INSERT INTO analysis_run(match_id,engine_name,engine_version,profile_fingerprint,config_json,status,started_at_utc)
                         VALUES(?, 'gnubg', ?, ?, ?, 'running', ?)
                         ON CONFLICT(match_id,profile_fingerprint) DO UPDATE SET status='running', started_at_utc=excluded.started_at_utc, error_text=NULL""",
                      (mid, engine.version, fp, json.dumps(self.profile()), _now()))
        run_id = c.execute("SELECT id FROM analysis_run WHERE match_id=? AND profile_fingerprint=?", (mid, fp)).fetchone()["id"]
        try:
            data = eng.analyze_file(p, self.settings.engine_executable, self.settings.engine_plies,
                                    tuple(self.settings.exercise_classes), self.settings.engine_timeout_seconds,
                                    cancel=self._cancel)
            drafts, warns = build_exercises(data, m["content_sha256"][:16], self.settings.near_equal_tolerance,
                                            tuple(self.settings.exercise_classes))
        except eng.ScanCancelled:
            with c:  # aucun exercice n'est encore écrit : on oublie ce run, le fichier sera repris au prochain scan
                c.execute("DELETE FROM analysis_run WHERE id=? AND status='running'", (run_id,))
            raise
        except Exception as e:
            with c:
                c.execute("UPDATE analysis_run SET status='failed', error_text=?, completed_at_utc=? WHERE id=?",
                          (f"{type(e).__name__}: {e}"[:1000], _now(), run_id))
                c.execute("UPDATE source_file SET status='failed', last_error=? WHERE id=?", (str(e)[:500], m["source_file_id"]))
            raise
        with c:  # tout ou rien
            c.execute("DELETE FROM exercise WHERE analysis_run_id=?", (run_id,))
            for d in drafts:
                c.execute("""INSERT INTO exercise(logical_key,kind,match_id,analysis_run_id,game_index,action_index,player_name,player_color,
                    board_schema_version,position_json,dice_json,cube_value,cube_owner,offered_cube,score_me,score_opp,match_length,crawford,
                    played_json,best_json,accepted_json,equity_loss,metric,classification,extra_json)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (d.logical_key, d.kind, mid, run_id, d.game_index, d.action_index, d.player_name, d.player_color,
                           d.board_schema_version, json.dumps(d.position), json.dumps(d.dice) if d.dice else None,
                           d.cube_value, d.cube_owner, d.offered_cube, d.score_me, d.score_opp, d.match_length, int(d.crawford),
                           json.dumps(d.played), json.dumps(d.best), json.dumps(d.accepted), d.equity_loss, d.metric,
                           d.classification, json.dumps(d.extra)))
            c.execute("UPDATE analysis_run SET status='complete', decisions_seen=?, completed_at_utc=?, error_text=NULL WHERE id=?",
                      (data["stats"]["decisions"], _now(), run_id))
            c.execute("UPDATE source_file SET status='analyzed', last_error=NULL WHERE id=?", (m["source_file_id"],))
        return len(drafts), data["stats"]["decisions"], warns

    # ---------- remise à zéro ----------
    def reset_database(self, keep_sessions: bool = True) -> dict:
        """Vide les données importées/analysées (sources, matchs, analyses, exercices, progression).
        Les fichiers .mat ne sont jamais touchés. Sauvegarde préalable de la base."""
        import shutil
        c = self._conn()
        c.commit()
        path = self.settings.db_file
        backup = path.with_suffix(".bak-reset")
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        shutil.copy2(path, backup)
        tables = ["exercise_progress", "exercise", "analysis_run", "match_record", "source_file"]
        if not keep_sessions:
            tables = ["session_event", "training_session"] + tables
        with c:
            for t in tables:
                c.execute(f"DELETE FROM {t}")
        c.execute("VACUUM")
        return {"backup": str(backup), "tables": tables}

    def clear_sessions(self) -> dict:
        """Supprime uniquement l'historique des sessions (sessions + événements).
        Exercices, analyses et progression (réussi/raté) sont conservés. Sauvegarde préalable de la base."""
        import shutil
        c = self._conn()
        c.commit()
        path = self.settings.db_file
        backup = path.with_suffix(".bak-sessions")
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        shutil.copy2(path, backup)
        n = c.execute("SELECT COUNT(*) FROM training_session").fetchone()[0]
        with c:
            c.execute("DELETE FROM session_event")
            c.execute("DELETE FROM training_session")
        return {"backup": str(backup), "sessions": n}

    # ---------- requêtes ----------
    def list_players(self) -> list[dict]:
        rows = self._conn().execute(
            "SELECT player_name, COUNT(*) n FROM exercise WHERE analysis_run_id IN (SELECT id FROM analysis_run WHERE status='complete') "
            "GROUP BY player_name ORDER BY n DESC, player_name").fetchall()
        return [{"name": r["player_name"], "count": r["n"]} for r in rows]

    def list_exercises(self, kinds: tuple[str, ...] = ("move", "cube"), players: list[str] | None = None,
                       states: list[str] | None = None, source_path: str | None = None,
                       order: str = "match", classes: list[str] | None = None) -> list[dict]:
        """``players`` / ``classes`` vide ou None = tous. ``source_path`` : mode fichier unique (filtre strict)."""
        q = ["SELECT e.id, e.kind, e.player_name, e.logical_key, e.game_index, e.action_index, e.equity_loss, e.classification,",
             "COALESCE(p.state,'new') state, COALESCE(p.attempts,0) attempts, m.id match_id",
             "FROM exercise e JOIN match_record m ON m.id=e.match_id",
             "JOIN analysis_run r ON r.id=e.analysis_run_id",
             "JOIN source_file s ON s.id=m.source_file_id",
             "LEFT JOIN exercise_progress p ON p.logical_key=e.logical_key",
             "WHERE r.status='complete' AND r.profile_fingerprint=(SELECT r2.profile_fingerprint FROM analysis_run r2 WHERE r2.match_id=r.match_id AND r2.status='complete' ORDER BY r2.completed_at_utc DESC, r2.id DESC LIMIT 1)"]
        args: list = []
        if kinds:
            q.append("AND e.kind IN (%s)" % ",".join("?" * len(kinds)))
            args += list(kinds)
        if players:
            q.append("AND e.player_name IN (%s)" % ",".join("?" * len(players)))
            args += players
        if classes:
            q.append("AND e.classification IN (%s)" % ",".join("?" * len(classes)))
            args += list(classes)
        if states:
            q.append("AND COALESCE(p.state,'new') IN (%s)" % ",".join("?" * len(states)))
            args += states
        if source_path:
            sha = sha256_file(source_path)
            q.append("AND m.content_sha256=?")
            args.append(sha)
        q.append({"match": "ORDER BY m.id, e.game_index, e.action_index",
                  "loss": "ORDER BY e.equity_loss DESC",
                  "random": "ORDER BY RANDOM()"}.get(order, "ORDER BY e.id"))
        return [dict(r) for r in self._conn().execute(" ".join(q), args).fetchall()]

    def source_status(self, path: str) -> dict:
        """Distingue : non importé / non analysé / échec / analysé sans exercice / avec exercices."""
        c = self._conn()
        sha = sha256_file(path)
        m = c.execute("SELECT m.id, s.status, s.last_error FROM match_record m JOIN source_file s ON s.id=m.source_file_id WHERE m.content_sha256=?", (sha,)).fetchone()
        if not m:
            r = c.execute("SELECT status,last_error FROM source_file WHERE canonical_path=? AND content_sha256=?", (str(Path(path).resolve()), sha)).fetchone()
            return {"state": "unsupported" if r and r["status"] == "unsupported" else "not_imported", "error": r["last_error"] if r else None}
        run = c.execute("SELECT status,error_text,id FROM analysis_run WHERE match_id=? ORDER BY id DESC LIMIT 1", (m["id"],)).fetchone()
        if not run:
            return {"state": "not_analyzed"}
        if run["status"] == "failed":
            return {"state": "analysis_failed", "error": run["error_text"]}
        if run["status"] != "complete":
            return {"state": "not_analyzed"}
        n = c.execute("SELECT COUNT(*) FROM exercise WHERE analysis_run_id=?", (run["id"],)).fetchone()[0]
        return {"state": "ready" if n else "no_errors", "exercises": n}

    def get_exercise(self, exercise_id: int) -> dict:
        r = self._conn().execute("SELECT e.*, m.player_x, m.player_o, m.match_date FROM exercise e JOIN match_record m ON m.id=e.match_id WHERE e.id=?", (exercise_id,)).fetchone()
        if not r:
            raise KeyError(exercise_id)
        d = dict(r)
        for k in ("position_json", "dice_json", "played_json", "best_json", "accepted_json", "extra_json"):
            d[k[:-5]] = json.loads(d.pop(k)) if d[k] else None
        return d

    # ---------- tentatives ----------
    def legal_next(self, exercise_id: int, done: list[tuple[int, int, int]]) -> set[tuple[int, int, int]]:
        ex = self.get_exercise(exercise_id)
        pos = Position.from_dict(ex["position"])
        return next_steps(legal_plays(pos, ex["dice"]), done)

    def submit_attempt(self, exercise_id: int, answer: dict, session_id: int | None = None) -> AttemptResult:
        """move : {"steps": [[src,dst],...]} ; cube : {"action": "..."}."""
        ex = self.get_exercise(exercise_id)
        if session_id is not None and self.is_locked(session_id, exercise_id):
            return AttemptResult(False, False, "Réponse déjà validée dans cette session : elle ne peut plus être modifiée.",
                                 locked=True)
        if ex["kind"] == "move":
            pos = Position.from_dict(ex["position"])
            plays = legal_plays(pos, ex["dice"])
            try:
                steps = [(int(a), int(b)) for a, b in answer["steps"]]
                final = apply_steps(pos, steps)
            except Exception:
                return AttemptResult(False, False, "Coup illégal : déplacement impossible.")
            legal_finals = {p.final.key(): p for p in plays}
            if not plays:
                return AttemptResult(False, False, "Aucun coup légal pour ce jet.")
            if final.key() not in legal_finals:
                full = max((len(p.steps) for p in plays), default=0)
                msg = "Coup incomplet : jouez tous les dés possibles." if len(steps) < full else "Coup illégal pour ce jet."
                return AttemptResult(False, False, msg)
            ok = final.key() in {a["key"] for a in ex["accepted"]}
        else:
            act = answer.get("action")
            if act not in ex["extra"]["options"]:
                return AttemptResult(False, False, "Action non disponible pour cette décision.")
            ok = act in [a for a in ex["accepted"]]
        self._record(ex["logical_key"], ok)
        if session_id is not None:
            self._event(session_id, ex, "attempt", ok, answer)
        reveal = self._reveal(ex) if (ok or self.settings.reveal_correction_after_incorrect or session_id is not None) else None
        return AttemptResult(ok, True, "Correct." if ok else "Incorrect.", reveal)

    # ---------- sessions ----------
    def _event(self, session_id: int, ex: dict, event: str, correct: bool | None = None, answer: dict | None = None) -> None:
        c = self._conn()
        with c:
            c.execute("INSERT INTO session_event(session_id,exercise_id,logical_key,event,correct,answer_json,created_at_utc) VALUES(?,?,?,?,?,?,?)",
                      (session_id, ex["id"], ex["logical_key"], event, None if correct is None else int(correct),
                       json.dumps(answer) if answer else None, _now()))

    def start_session(self, items: list[dict], filters: dict) -> int:
        """Démarre une session sur une liste figée d'exercices (dicts de list_exercises).
        Les sessions encore ouvertes sont marquées « abandonnées » (résultats conservés)."""
        if not items:
            raise ValueError("Aucun exercice pour démarrer une session.")
        c = self._conn()
        brief = [{"id": e["id"], "key": e["logical_key"], "kind": e["kind"], "player": e["player_name"],
                  "classification": e.get("classification")} for e in items]
        with c:
            c.execute("UPDATE training_session SET status='abandoned', ended_at_utc=? WHERE status='running'", (_now(),))
            cur = c.execute("INSERT INTO training_session(started_at_utc,filters_json,items_json,total) VALUES(?,?,?,?)",
                            (_now(), json.dumps(filters), json.dumps(brief), len(brief)))
        return cur.lastrowid

    def is_locked(self, session_id: int, exercise_id: int) -> bool:
        """Vrai si une réponse a été validée (ou la correction consultée) dans cette session."""
        r = self._conn().execute(
            "SELECT 1 FROM session_event WHERE session_id=? AND exercise_id=? AND event IN ('attempt','reveal') LIMIT 1",
            (session_id, exercise_id)).fetchone()
        return bool(r)

    def session_answer(self, session_id: int, exercise_id: int) -> dict | None:
        """Dernière réponse validée dans la session : {correct, answer} ou None."""
        r = self._conn().execute(
            "SELECT correct, answer_json FROM session_event WHERE session_id=? AND exercise_id=? AND event='attempt' ORDER BY id LIMIT 1",
            (session_id, exercise_id)).fetchone()
        if not r:
            return None
        return {"correct": bool(r["correct"]), "answer": json.loads(r["answer_json"]) if r["answer_json"] else None}

    def record_reveal(self, session_id: int, exercise_id: int) -> None:
        if self.is_locked(session_id, exercise_id):
            return
        self._event(session_id, self.get_exercise(exercise_id), "reveal")

    def record_skip(self, session_id: int, exercise_id: int) -> None:
        self._event(session_id, self.get_exercise(exercise_id), "skip")

    def session_outcomes(self, session_id: int) -> dict[int, str]:
        """Résultat par exercice : first_try | retry | failed | skipped | unanswered."""
        c = self._conn()
        row = c.execute("SELECT items_json FROM training_session WHERE id=?", (session_id,)).fetchone()
        if not row:
            raise KeyError(session_id)
        res = {i["id"]: "unanswered" for i in json.loads(row["items_json"])}
        evs: dict[int, list] = {}
        for r in c.execute("SELECT exercise_id,event,correct FROM session_event WHERE session_id=? ORDER BY id", (session_id,)):
            evs.setdefault(r["exercise_id"], []).append((r["event"], r["correct"]))
        for eid, seq in evs.items():
            if eid not in res:
                continue
            attempts = [x for x in seq if x[0] == "attempt"]
            revealed_first = False
            out = None
            for i, (ev, ok) in enumerate(seq):
                if ev == "reveal":
                    revealed_first = True
                elif ev == "attempt" and ok:
                    out = "first_try" if not any(e == "attempt" for e, _ in seq[:i]) and not revealed_first else (
                        "failed" if revealed_first else "retry")
                    break
            if out is None:
                out = "failed" if (attempts or revealed_first) else ("skipped" if seq else "unanswered")
            res[eid] = out
        return res

    def _vs_match(self, ex: dict, answer: dict | None) -> tuple[str, float | None] | None:
        """Compare votre réponse au coup joué dans le match : ("better" | "same" | "worse", gain d'équité ou None).
        None si la comparaison est impossible (pas de réponse, coup non évalué par gnubg)."""
        if not answer:
            return None
        if ex["kind"] == "cube":
            act = answer.get("action")
            if not act:
                return None
            played, best = ex["played"]["action"], ex["best"]["action"]
            return ("same", 0.0) if act == played else (("better", None) if act == best else ("worse", None))
        if "steps" not in answer:
            return None
        pos = Position.from_dict(ex["position"])
        try:
            ukey = apply_steps(pos, [(int(a), int(b)) for a, b in answer["steps"]]).key()
        except Exception:
            return None
        pkey = apply_steps(pos, [(int(a), int(b)) for a, b in ex["played"]["move"]]).key()
        if ukey == pkey:
            return ("same", 0.0)
        cands = ((ex.get("extra") or {}).get("analysis") or {}).get("candidates", [])
        diff_of: dict[str, float] = {}
        for c in cands:
            try:
                diff_of[apply_steps(pos, [(int(a), int(b)) for a, b in c["move"]]).key()] = c["diff"]
            except Exception:
                continue
        if ukey in {a["key"] for a in ex["accepted"]}:
            ud = 0.0
        elif ukey in diff_of:
            ud = diff_of[ukey]
        else:
            return None
        pd = diff_of.get(pkey, -(ex["equity_loss"] or 0.0))
        gain = ud - pd
        return ("better" if gain > 1e-9 else "worse" if gain < -1e-9 else "same", gain)

    def session_summary(self, session_id: int) -> dict:
        c = self._conn()
        s = c.execute("SELECT * FROM training_session WHERE id=?", (session_id,)).fetchone()
        if not s:
            raise KeyError(session_id)
        items = json.loads(s["items_json"])
        out = self.session_outcomes(session_id)
        cnt = {k: 0 for k in ("first_try", "retry", "failed", "skipped", "unanswered")}
        by_kind: dict[str, dict] = {}
        by_player: dict[str, dict] = {}
        for it in items:
            o = out[it["id"]]
            cnt[o] += 1
            for grp, key in ((by_kind, it["kind"]), (by_player, it["player"])):
                g = grp.setdefault(key, {"total": 0, "first_try": 0, "failed": 0, "answered": 0})
                g["total"] += 1
                g["first_try"] += o == "first_try"
                g["failed"] += o == "failed"
                g["answered"] += o != "unanswered"
        vs = {k: {"better": 0, "same": 0, "worse": 0, "unknown": 0, "gain": 0.0, "gain_n": 0} for k in ("move", "cube")}
        for it in items:
            if out[it["id"]] in ("skipped", "unanswered"):
                continue
            ans = self.session_answer(session_id, it["id"])
            r = self._vs_match(self.get_exercise(it["id"]), ans["answer"] if ans else None)
            v = vs[it["kind"]]
            if r is None:
                v["unknown"] += 1
                continue
            v[r[0]] += 1
            if r[1] is not None:
                v["gain"] += r[1]
                v["gain_n"] += 1
        total = s["total"]
        return {"vs_match": vs, "id": s["id"], "started": s["started_at_utc"], "ended": s["ended_at_utc"], "status": s["status"],
                "total": total, **cnt, "answered": total - cnt["unanswered"],
                "score_pct": round(100 * cnt["first_try"] / total, 1) if total else 0.0,
                "by_kind": by_kind, "by_player": by_player, "filters": json.loads(s["filters_json"])}

    def exercise_history(self) -> dict[str, tuple[int, int]]:
        """Par exercice (logical_key) : (nb de fois où il a été proposé et traité en session, nb d'erreurs).
        Une erreur = pas réussi du premier coup (réussi après erreur ou échec). Passé / non traité : ignoré."""
        c = self._conn()
        hist: dict[str, list[int]] = {}
        for r in c.execute("SELECT id, items_json FROM training_session").fetchall():
            out = self.session_outcomes(r["id"])
            for it in json.loads(r["items_json"]):
                o = out.get(it["id"])
                if o in ("first_try", "retry", "failed"):
                    h = hist.setdefault(it["key"], [0, 0])
                    h[0] += 1
                    h[1] += o != "first_try"
        return {k: (v[0], v[1]) for k, v in hist.items()}

    def finish_session(self, session_id: int) -> dict:
        c = self._conn()
        with c:
            c.execute("UPDATE training_session SET status='finished', ended_at_utc=? WHERE id=? AND status='running'", (_now(), session_id))
        return self.session_summary(session_id)

    def list_sessions(self) -> list[dict]:
        ids = [r["id"] for r in self._conn().execute("SELECT id FROM training_session ORDER BY started_at_utc, id")]
        return [self.session_summary(i) for i in ids]

    def _reveal(self, ex: dict) -> dict:
        if ex["kind"] == "move":
            return {"best": [a["move"] for a in ex["accepted"]], "played": ex["played"]["move"], "loss": ex["equity_loss"],
                    "analysis": (ex["extra"] or {}).get("analysis"), "plies": self.settings.engine_plies}
        return {"best": ex["best"]["action"], "played": ex["played"]["action"],
                "analysis": (ex["extra"] or {}).get("analysis"), "plies": self.settings.engine_plies}

    def coach(self, exercise_id: int, answer: dict | None = None) -> list[tuple[str, str]]:
        """Explications fondées sur REGLES_BACKGAMMON.md : liste de (type, texte), type = ok | bad | info."""
        ex = self.get_exercise(exercise_id)
        try:
            pos = Position.from_dict(ex["position"])
            an = (ex["extra"] or {}).get("analysis")
            if ex["kind"] == "move":
                user = answer.get("steps") if answer else None
                rem = explain_move(pos, ex["dice"], [a["move"] for a in ex["accepted"]], user, an)
            else:
                rem = explain_cube(pos, (an or {}).get("asked", "double"), ex["best"]["action"],
                                   answer.get("action") if answer else None)
        except Exception:  # le coaching ne doit jamais bloquer la correction
            return []
        return [(r.kind, r.text) for r in rem]

    def conflict(self, exercise_id: int, answer: dict | None, correct: bool) -> str | None:
        """Désaccord entre le verdict du moteur et les règles (None si aucun)."""
        ex = self.get_exercise(exercise_id)
        try:
            pos = Position.from_dict(ex["position"])
            if ex["kind"] == "move":
                if not answer or "steps" not in answer:
                    return None
                return rules_conflict(pos, ex["dice"], answer["steps"], correct)
            an = (ex["extra"] or {}).get("analysis") or {}
            return cube_conflict(pos, an.get("asked", "double"), ex["best"]["action"])
        except Exception:
            return None

    def reveal(self, exercise_id: int) -> dict:
        return self._reveal(self.get_exercise(exercise_id))

    def _record(self, key: str, ok: bool) -> None:
        c = self._conn()
        with c:
            c.execute("""INSERT INTO exercise_progress(logical_key,state,attempts,last_attempt_at_utc,updated_at_utc)
                         VALUES(?,?,1,?,?)
                         ON CONFLICT(logical_key) DO UPDATE SET attempts=attempts+1, last_attempt_at_utc=excluded.last_attempt_at_utc,
                         updated_at_utc=excluded.updated_at_utc,
                         state=CASE WHEN ?='correct' THEN 'correct' WHEN state='correct' THEN 'correct' ELSE 'in_progress' END""",
                      (key, "correct" if ok else "in_progress", _now(), _now(), "correct" if ok else "x"))

    def set_exercise_status(self, exercise_id: int, state: str) -> None:
        if state not in ("new", "in_progress", "correct", "skipped"):
            raise ValueError(state)
        key = self.get_exercise(exercise_id)["logical_key"]
        c = self._conn()
        with c:
            c.execute("""INSERT INTO exercise_progress(logical_key,state,updated_at_utc) VALUES(?,?,?)
                         ON CONFLICT(logical_key) DO UPDATE SET state=excluded.state, updated_at_utc=excluded.updated_at_utc""",
                      (key, state, _now()))


def _mtime(st) -> str:
    return datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds")
