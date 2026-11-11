import json
from bgtrainer.config.settings import Settings
from bgtrainer.services.api import TrainerService


def _svc(tmp_path):
    s = Settings(database_path=str(tmp_path / "t.db"))
    svc = TrainerService(s)
    c = svc.conn
    with c:
        c.execute("INSERT INTO source_file(canonical_path,content_sha256,byte_size,status) VALUES('p','h',1,'analyzed')")
        c.execute("INSERT INTO match_record(source_file_id,content_sha256) VALUES(1,'h')")
        c.execute("INSERT INTO analysis_run(match_id,engine_name,engine_version,profile_fingerprint,config_json,status) VALUES(1,'g','1','f','{}','complete')")
        for i in range(4):
            c.execute("""INSERT INTO exercise(logical_key,kind,match_id,analysis_run_id,game_index,action_index,player_name,player_color,
                board_schema_version,position_json,played_json,best_json,accepted_json,classification,extra_json)
                VALUES(?,?,1,1,0,?,?, 'X',1,?,?,?,?,'very bad',?)""",
                      (f"k{i}", "cube", i, "FLC", json.dumps({"mine": [0]*25, "opp": [0]*25}),
                       json.dumps({"action": "double"}), json.dumps({"action": "no_double"}),
                       json.dumps(["no_double"]), json.dumps({"options": ["double", "no_double"]})))
    return svc


def test_session_outcomes_and_summary(tmp_path):
    svc = _svc(tmp_path)
    items = svc.list_exercises()
    sid = svc.start_session(items, {"kinds": ["cube"]})
    ids = [e["id"] for e in items]
    assert svc.submit_attempt(ids[0], {"action": "no_double"}, sid).correct          # 1er essai
    assert not svc.submit_attempt(ids[1], {"action": "double"}, sid).correct
    r = svc.submit_attempt(ids[1], {"action": "no_double"}, sid)                     # modification refusée
    assert r.locked and not r.correct
    assert svc.is_locked(sid, ids[1]) and svc.session_answer(sid, ids[1])["answer"] == {"action": "double"}
    svc.record_reveal(sid, ids[2])
    assert svc.submit_attempt(ids[2], {"action": "no_double"}, sid).locked           # correction vue : verrouillé
    svc.record_skip(sid, ids[3])
    out = svc.session_outcomes(sid)
    assert [out[i] for i in ids] == ["first_try", "failed", "failed", "skipped"]
    # hors session : on peut réessayer
    assert svc.submit_attempt(ids[1], {"action": "no_double"}).correct
    sm = svc.finish_session(sid)
    assert sm["status"] == "finished" and sm["score_pct"] == 25.0 and sm["by_player"]["FLC"]["total"] == 4


def test_new_session_abandons_running_and_keeps_history(tmp_path):
    svc = _svc(tmp_path)
    items = svc.list_exercises()
    a = svc.start_session(items, {})
    b = svc.start_session(items[:2], {})
    sess = svc.list_sessions()
    assert [s["status"] for s in sess] == ["abandoned", "running"] and sess[0]["unanswered"] == 4
    assert svc.session_summary(b)["total"] == 2


def test_reset_database_keeps_sessions_and_backs_up(tmp_path):
    svc = _svc(tmp_path)
    svc.start_session(svc.list_exercises(), {})
    info = svc.reset_database()
    assert svc.list_exercises() == [] and svc.conn.execute("SELECT COUNT(*) FROM source_file").fetchone()[0] == 0
    assert svc.conn.execute("SELECT COUNT(*) FROM training_session").fetchone()[0] == 1
    assert info["backup"].endswith(".bak-reset")
    svc.reset_database(keep_sessions=False)
    assert svc.conn.execute("SELECT COUNT(*) FROM training_session").fetchone()[0] == 0


def test_class_filter_and_migration(tmp_path):
    svc = _svc(tmp_path)
    with svc.conn:
        svc.conn.execute("UPDATE exercise SET classification='bad' WHERE id=1")
        svc.conn.execute("UPDATE exercise SET classification='doubtful' WHERE id=2")
    assert len(svc.list_exercises()) == 4
    assert [e["classification"] for e in svc.list_exercises(classes=["bad"])] == ["bad"]
    assert len(svc.list_exercises(classes=["bad", "doubtful"])) == 2
    assert len(svc.list_exercises(classes=["very bad"])) == 2


def test_clear_sessions_keeps_exercises_and_progress(tmp_path):
    svc = _svc(tmp_path)
    items = svc.list_exercises()
    sid = svc.start_session(items, {})
    svc.submit_attempt(items[0]["id"], {"action": "no_double"}, sid)
    assert svc.list_sessions()
    info = svc.clear_sessions()
    assert info["sessions"] == 1
    assert svc.list_sessions() == []
    assert svc.conn.execute("SELECT COUNT(*) FROM session_event").fetchone()[0] == 0
    assert len(svc.list_exercises()) == 4
    assert svc.list_exercises()[0]["state"] == "correct"


def test_exercise_history(tmp_path):
    svc = _svc(tmp_path)
    items = svc.list_exercises()
    ids = [e["id"] for e in items]
    for answers in (("no_double", "double", "double"), ("no_double", "double", "no_double")):
        sid = svc.start_session(items[:3], {})
        for i, a in zip(ids, answers):
            svc.submit_attempt(i, {"action": a}, sid)
        svc.finish_session(sid)
    h = svc.exercise_history()
    assert h[items[0]["logical_key"]] == (2, 0)     # toujours réussi
    assert h[items[1]["logical_key"]] == (2, 2)     # toujours raté
    assert h[items[2]["logical_key"]] == (2, 1)     # 50 % : pas « > 50 % »
    assert items[3]["logical_key"] not in h         # jamais fait


def test_summary_vs_match(tmp_path):
    svc = _svc(tmp_path)
    items = svc.list_exercises()
    sid = svc.start_session(items[:3], {})
    ids = [e["id"] for e in items[:3]]
    svc.submit_attempt(ids[0], {"action": "no_double"}, sid)   # = meilleur (le match avait joué « double »)
    svc.submit_attempt(ids[1], {"action": "double"}, sid)      # = coup du match
    svc.record_skip(sid, ids[2])
    v = svc.finish_session(sid)["vs_match"]["cube"]
    assert (v["better"], v["same"], v["worse"]) == (1, 1, 0)
