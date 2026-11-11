"""Parseur du .mat ASCII (BackgammonGalaxy / Tavla).

Rôle : métadonnées, structure (parties, scores, résultats) et validation
d'un fichier avant analyse. Le rejeu des positions est fait par gnubg ;
les mouvements ne sont pas réinterprétés ici, seulement tokenisés.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

PARSER_VERSION = 1


class MatError(Exception):
    """Fichier .mat invalide (motif dans le message)."""


@dataclass
class MatTurn:
    number: int
    left: str
    right: str


@dataclass
class MatGame:
    index: int
    score: tuple[int, int] | None
    turns: list[MatTurn] = field(default_factory=list)
    result: str | None = None  # texte brut "Wins 2 points"


@dataclass
class MatFile:
    path: str
    sha256: str
    size: int
    meta: dict[str, str]
    player1: str
    player2: str
    match_length: int
    games: list[MatGame]
    match_id: str | None

    @property
    def players(self) -> tuple[str, str]:
        return self.player1, self.player2


_META = re.compile(r'^;\s*\[(?P<k>[^"\]]+?)\s+"(?P<v>.*)"\]\s*$')
_LEN = re.compile(r"^\s*(\d+)\s+point match\s*$", re.I)
_GAME = re.compile(r"^\s*Game\s+(\d+)\s*$")
_TURN = re.compile(r"^\s*(\d+\)) ?(.*)$")
_SCORE = re.compile(r"^\s*(.+?)\s*:\s*(\d+)\s{2,}(.+?)\s*:\s*(\d+)\s*$")
_RESULT = re.compile(r"(Wins|Losses)\s+(\d+)\s+points?", re.I)


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_mat(path: str | Path) -> MatFile:
    p = Path(path)
    raw = p.read_bytes()
    if not raw.strip():
        raise MatError("fichier vide")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except UnicodeDecodeError as e:  # pragma: no cover
            raise MatError("encodage invalide") from e
    meta: dict[str, str] = {}
    length: int | None = None
    games: list[MatGame] = []
    cur: MatGame | None = None
    names: tuple[str, str] | None = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.lstrip().startswith(";"):
            m = _META.match(line.strip())
            if m:
                meta[m["k"].strip()] = m["v"]
            continue
        m = _LEN.match(line)
        if m and length is None:
            length = int(m[1])
            continue
        m = _GAME.match(line)
        if m:
            cur = MatGame(index=int(m[1]), score=None)
            games.append(cur)
            continue
        if cur is None:
            continue
        m = _SCORE.match(line)
        if m and cur.score is None and not _TURN.match(line):
            cur.score = (int(m[2]), int(m[4]))
            names = (m[1].strip(), m[3].strip())
            continue
        m = _TURN.match(line)
        if m:
            body = m[2]
            left, right = _split_turn(body)
            cur.turns.append(MatTurn(int(m[1][:-1]), left, right))
            r = _RESULT.search(body)
            if r:
                cur.result = r.group(0)
            continue
        r = _RESULT.search(line)
        if r:
            cur.result = r.group(0)
    if length is None:
        raise MatError("longueur de match absente ('N point match')")
    if not games:
        raise MatError("aucune partie ('Game N')")
    p1 = meta.get("Player 1") or (names[0] if names else None)
    p2 = meta.get("Player 2") or (names[1] if names else None)
    if not p1 or not p2:
        raise MatError("noms des joueurs absents")
    for g in games:
        if g.score is None:
            raise MatError(f"Game {g.index}: score absent")
        if not g.turns:
            raise MatError(f"Game {g.index}: aucun tour")
    return MatFile(
        path=str(p), sha256=hashlib.sha256(raw).hexdigest(), size=len(raw),
        meta=meta, player1=p1, player2=p2, match_length=length, games=games,
        match_id=meta.get("Match ID"),
    )


def _split_turn(body: str) -> tuple[str, str]:
    """Sépare les deux côtés d'un tour (colonne droite à partir de ~34 car.)."""
    parts = re.split(r"\s{2,}", body.strip(), maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return body.strip(), ""
