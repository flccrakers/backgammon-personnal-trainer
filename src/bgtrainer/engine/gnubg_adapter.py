"""Adaptateur GNU Backgammon : lance gnubg en sous-processus (sans shell)
avec le script interne ``gnubg_script.py`` et lit le JSON produit."""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

SCRIPT = Path(__file__).with_name("gnubg_script.py")
SUPPORTED_SCHEMA = 1


class EngineError(Exception):
    pass


class EngineUnavailable(EngineError):
    pass


class EngineTimeout(EngineError):
    pass


class EngineBadOutput(EngineError):
    pass


class ScanCancelled(Exception):
    """Analyse interrompue à la demande de l'utilisateur (le processus gnubg a été arrêté)."""


def _kill_group(proc: subprocess.Popen, sig: int) -> None:
    """Envoie le signal à tout le groupe (gnubg et ses éventuels sous-processus)."""
    try:
        os.killpg(proc.pid, sig)
    except (ProcessLookupError, PermissionError, AttributeError):
        proc.send_signal(sig)


def _run_cancellable(cmd: list[str], env: dict, cwd: str, timeout: float, cancel: threading.Event | None):
    """Comme subprocess.run, mais arrête gnubg dès que ``cancel`` est positionné."""
    proc = subprocess.Popen(cmd, env=env, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True)
    t0 = time.monotonic()
    while True:
        try:
            out, err = proc.communicate(timeout=0.3)
            return subprocess.CompletedProcess(cmd, proc.returncode, out, err)
        except subprocess.TimeoutExpired:
            pass
        if cancel is not None and cancel.is_set():
            _kill_group(proc, signal.SIGTERM)
            try:
                proc.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                _kill_group(proc, signal.SIGKILL)
                proc.communicate()
            raise ScanCancelled()
        if time.monotonic() - t0 > timeout:
            _kill_group(proc, signal.SIGKILL)
            proc.communicate()
            raise subprocess.TimeoutExpired(cmd, timeout)


@dataclass(frozen=True)
class EngineInfo:
    executable: str
    version: str


def probe(executable: str = "gnubg", timeout: float = 30) -> EngineInfo:
    """Vérifie que l'exécutable est bien GNU Backgammon et retourne sa version."""
    import shutil

    exe = shutil.which(executable) or (executable if os.path.isfile(executable) else None)
    if not exe:
        raise EngineUnavailable(
            f"Exécutable '{executable}' introuvable. Installez GNU Backgammon (gnubg) "
            "ou configurez [engine].executable (gpg/GnuPG n'est pas un moteur de backgammon)."
        )
    if os.path.basename(exe).startswith("gpg"):
        raise EngineUnavailable("GnuPG n'analyse pas le backgammon : configurez gnubg.")
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise EngineTimeout("gnubg --version : délai dépassé") from e
    out = (r.stdout or "") + (r.stderr or "")
    m = re.search(r"GNU Backgammon\s+([0-9][^\s]*)", out)
    if not m:
        raise EngineUnavailable(f"'{exe}' ne semble pas être GNU Backgammon.")
    return EngineInfo(exe, m.group(1))


def analyze_file(
    mat_path: str | Path,
    executable: str = "gnubg",
    plies: int = 2,
    classes: tuple[str, ...] = ("doubtful", "bad", "very bad"),
    timeout: float = 600,
    cancel: threading.Event | None = None,
) -> dict:
    """Analyse un .mat ; retourne le JSON (voir gnubg_script.py)."""
    info = probe(executable)
    with tempfile.TemporaryDirectory(prefix="bgt-") as td:
        out = os.path.join(td, "out.json")
        # Copie dans le répertoire temporaire : chemin simple, source jamais modifiée.
        src = os.path.join(td, "in.mat")
        with open(mat_path, "rb") as fi, open(src, "wb") as fo:
            fo.write(fi.read())
        env = dict(os.environ)
        env.update(BGT_INPUT=src, BGT_OUTPUT=out, BGT_PLIES=str(plies), BGT_CLASSES="|".join(classes))
        try:
            r = _run_cancellable([info.executable, "-t", "-q", "-p", str(SCRIPT)], env, td, timeout, cancel)
        except subprocess.TimeoutExpired as e:
            raise EngineTimeout(f"gnubg : délai de {timeout}s dépassé") from e
        if os.path.exists(out + ".err"):
            raise EngineBadOutput(Path(out + ".err").read_text()[-2000:])
        if not os.path.exists(out):
            tail = (r.stderr or "")[-500:]
            raise EngineError(f"gnubg n'a rien produit (code {r.returncode}) {tail}")
        try:
            data = json.loads(Path(out).read_text())
        except json.JSONDecodeError as e:
            raise EngineBadOutput("JSON gnubg illisible") from e
    if data.get("schema") != SUPPORTED_SCHEMA:
        raise EngineBadOutput("schéma de sortie inconnu")
    data["engine_version"] = info.version
    return data
