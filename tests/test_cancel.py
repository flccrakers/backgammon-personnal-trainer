import threading
import time

from bgtrainer.config.settings import Settings
from bgtrainer.services import api
from bgtrainer.services.api import TrainerService


def test_cancel_reports_remaining(tmp_path, monkeypatch):
    s = Settings(database_path=str(tmp_path / "t.db"), engine_workers=2)
    svc = TrainerService(s)
    files = []
    for i in range(5):
        f = tmp_path / f"{i}.mat"
        f.write_text("x")
        files.append(f)
    monkeypatch.setattr(api.eng, "probe", lambda exe: type("E", (), {"version": "1", "executable": exe})())
    monkeypatch.setattr(svc, "_import_one", lambda p: api.FileReport(str(p), "new"))
    monkeypatch.setattr(svc, "_match_id_for", lambda p: 1)
    monkeypatch.setattr(svc, "_analysis_done", lambda m, fp: False)
    started = []

    def fake(p, engine, fp):
        started.append(p)
        time.sleep(0.8)
        return 0, 0, []

    monkeypatch.setattr(svc, "_analyze_path", fake)
    cancel = threading.Event()
    events = []
    threading.Timer(0.3, cancel.set).start()
    svc.scan_sources(files, progress=lambda *a: events.append(a), cancel=cancel)
    ann = [e for e in events if e[0] == "annulation"]
    assert ann[0][1:] == (0, 2)            # 2 analyses en cours au moment de l'annulation
    assert ann[-1][1:] == (2, 2)           # toutes terminées
    assert len(started) == 2               # les 3 autres n'ont jamais démarré
