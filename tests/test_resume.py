import threading
import time

import pytest

from bgtrainer.config.settings import Settings
from bgtrainer.engine import gnubg_adapter as eng
from bgtrainer.services import api
from bgtrainer.services.api import TrainerService


def test_analyze_file_cancel_kills_process(tmp_path, monkeypatch):
    fake = tmp_path / "gnubg"
    fake.write_text("#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo 'GNU Backgammon 1.06'; exit 0; fi\nsleep 30\n")
    fake.chmod(0o755)
    mat = tmp_path / "a.mat"
    mat.write_text("x")
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    t0 = time.monotonic()
    with pytest.raises(eng.ScanCancelled):
        eng.analyze_file(mat, str(fake), cancel=cancel)
    assert time.monotonic() - t0 < 8


def test_discover_includes_new_files_and_subdirs(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.mat").write_text("x")
    svc = TrainerService(Settings(database_path=str(tmp_path / "t.db"), mat_directory=str(tmp_path)))
    (tmp_path / "sub" / "b.mat").write_text("y")
    (tmp_path / "c.MAT").write_text("z")
    names = {p.name for p in svc.discover()}
    assert names == {"a.mat", "b.mat", "c.MAT"}


def test_interrupted_file_is_resumed_and_done_ones_are_not(tmp_path, monkeypatch):
    s = Settings(database_path=str(tmp_path / "t.db"), engine_workers=1)
    svc = TrainerService(s)
    files = []
    for i in range(3):
        f = tmp_path / f"{i}.mat"
        f.write_text(str(i))
        files.append(f)
    monkeypatch.setattr(api.eng, "probe", lambda exe: type("E", (), {"version": "1", "executable": exe})())
    monkeypatch.setattr(svc, "_import_one", lambda p: api.FileReport(str(p), "new"))
    ids = {f: i + 1 for i, f in enumerate(files)}
    monkeypatch.setattr(svc, "_match_id_for", lambda p: ids[p])
    done = set()
    monkeypatch.setattr(svc, "_analysis_done", lambda m, fp: m in done)
    calls = []

    def fake(p, engine, fp):
        calls.append(p.name)
        if p.name == "1.mat" and len(calls) < 3:
            raise api.eng.ScanCancelled()
        done.add(ids[p])
        return 0, 0, []

    monkeypatch.setattr(svc, "_analyze_path", fake)
    r1 = svc.scan_sources(files)
    assert [f.status for f in r1.files if f.path.endswith("1.mat")] == ["interrupted"]
    assert done == {1, 3}
    calls.clear()
    svc.scan_sources(files)
    assert calls == ["1.mat"]            # seul le fichier interrompu est repris


def test_recover_interrupted_removes_running_runs(tmp_path):
    svc = TrainerService(Settings(database_path=str(tmp_path / "t.db")))
    c = svc.conn
    with c:
        c.execute("INSERT INTO source_file(canonical_path,content_sha256,byte_size,status) VALUES('p','h',1,'imported')")
        c.execute("INSERT INTO match_record(source_file_id,content_sha256) VALUES(1,'h')")
        c.execute("INSERT INTO analysis_run(match_id,engine_name,engine_version,profile_fingerprint,config_json,status) VALUES(1,'g','1','f','{}','running')")
    assert svc.recover_interrupted() == 1
    assert c.execute("SELECT COUNT(*) FROM analysis_run").fetchone()[0] == 0
