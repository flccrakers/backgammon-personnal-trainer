"""CLI sans GUI : python -m bgtrainer.cli scan [--no-analyze] | stats"""
import argparse
import sys

from .config.settings import ConfigError, load_settings
from .engine.gnubg_adapter import EngineError
from .services.api import TrainerService


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bgtrainer-cli")
    ap.add_argument("cmd", choices=["scan", "stats"])
    ap.add_argument("--limit", type=int, help="ne traiter que les N premiers fichiers")
    a = ap.parse_args(argv)
    try:
        s = load_settings()
        svc = TrainerService(s)
        if a.cmd == "stats":
            for p in svc.list_players():
                print(f"{p['name']}: {p['count']}")
            return 0
        files = svc.discover()
        if a.limit:
            files = files[: a.limit]
        last = [0]

        def prog(phase, n, total):
            if n == total or n - last[0] >= 10 or n == 1:
                last[0] = n
                print(f"[{phase}] {n}/{total}", flush=True)

        r = svc.scan_sources(files, progress=prog)
    except (ConfigError, EngineError) as e:
        print(f"Erreur : {e}", file=sys.stderr)
        return 2
    for st in ("new", "modified", "unchanged", "duplicate", "unsupported", "failed", "retry"):
        if r.count(st):
            print(st, r.count(st))
    for f in r.files:
        if f.error:
            print("ERREUR", f.path, f.error[:200])
    print("exercices ajoutés :", sum(f.exercises for f in r.files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
