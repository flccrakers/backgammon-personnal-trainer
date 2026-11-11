"""Plateau canonique et règles de déplacement.

Convention canonique (versionnée, BOARD_SCHEMA_VERSION) :
  * Une position est vue du joueur AU TRAIT.
  * ``mine`` et ``opp`` sont des tuples de 25 entiers (nombre de pions).
    Index i (0..23) = point i+1 ; 24 = barre. Le point 24 est le plus éloigné
    de la sortie, le point 1 le plus proche. « off » = point 0.
  * Un pion adverse sur le point p adverse se trouve sur le point 25-p du
    joueur au trait.
  * Un pas est (origine, destination, dé) avec origine 25 = barre, destination 0 = sortie.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from typing import Iterable, Sequence

BOARD_SCHEMA_VERSION = 1
BAR = 25

Step = tuple[int, int]  # (origine, destination)


@dataclass(frozen=True)
class Position:
    mine: tuple[int, ...]
    opp: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.mine) != 25 or len(self.opp) != 25:
            raise ValueError("Une position comporte 25 cases par camp")

    @staticmethod
    def initial() -> "Position":
        m = [0] * 25
        m[5], m[7], m[12], m[23] = 5, 3, 5, 2
        return Position(tuple(m), tuple(m))

    @staticmethod
    def from_dict(d: dict) -> "Position":
        return Position(tuple(d["mine"]), tuple(d["opp"]))

    def to_dict(self) -> dict:
        return {"mine": list(self.mine), "opp": list(self.opp)}

    def count_mine(self, point: int) -> int:
        return self.mine[point - 1] if 1 <= point <= 24 else (self.mine[24] if point == BAR else 0)

    def count_opp_at(self, point: int) -> int:
        """Pions adverses sur le point ``point`` (repère du joueur au trait)."""
        return self.opp[24 - point] if 1 <= point <= 24 else 0

    def key(self) -> str:
        return ",".join(map(str, self.mine)) + "|" + ",".join(map(str, self.opp))

    def off_mine(self) -> int:
        return 15 - sum(self.mine)

    def off_opp(self) -> int:
        return 15 - sum(self.opp)

    def pips_mine(self) -> int:
        return sum((i + 1) * n for i, n in enumerate(self.mine))

    def pips_opp(self) -> int:
        return sum((i + 1) * n for i, n in enumerate(self.opp))

    def flipped(self) -> "Position":
        """Même position vue de l'adversaire (après son tour)."""
        return Position(self.opp, self.mine)


def _idx(point: int) -> int:
    return 24 if point == BAR else point - 1


def apply_step(pos: Position, step: Step) -> Position:
    """Applique un pas SANS vérifier la légalité des dés (mais vérifie les pions)."""
    src, dst = step
    mine = list(pos.mine)
    opp = list(pos.opp)
    if mine[_idx(src)] <= 0:
        raise ValueError(f"Aucun pion sur {src}")
    mine[_idx(src)] -= 1
    if dst > 0:
        if dst < 25:
            oi = 24 - dst
            if opp[oi] >= 2:
                raise ValueError(f"Point {dst} bloqué")
            if opp[oi] == 1:
                opp[oi] = 0
                opp[24] += 1
        mine[dst - 1] += 1
    return Position(tuple(mine), tuple(opp))


def apply_steps(pos: Position, steps: Sequence[Step]) -> Position:
    """Applique des pas dans l'ordre donné, ou dans un ordre valide si besoin."""
    try:
        p = pos
        for s in steps:
            p = apply_step(p, s)
        return p
    except ValueError:
        for perm in set(permutations(steps)):
            try:
                p = pos
                for s in perm:
                    p = apply_step(p, s)
                return p
            except ValueError:
                continue
        raise


def _all_home(pos: Position) -> bool:
    return pos.mine[24] == 0 and sum(pos.mine[6:24]) == 0


def _step_options(pos: Position, die: int) -> list[Step]:
    """Pas légaux avec un dé donné depuis ``pos``."""
    res: list[Step] = []
    if pos.mine[24] > 0:
        dst = 25 - die
        if pos.count_opp_at(dst) < 2:
            res.append((BAR, dst))
        return res
    home = _all_home(pos)
    for src in range(24, 0, -1):
        if pos.mine[src - 1] <= 0:
            continue
        dst = src - die
        if dst >= 1:
            if pos.count_opp_at(dst) < 2:
                res.append((src, dst))
        elif home:
            if dst == 0:
                res.append((src, 0))
            else:
                # dé supérieur : seulement si aucun pion plus éloigné
                if all(pos.mine[p - 1] == 0 for p in range(src + 1, 7)):
                    res.append((src, 0))
    return res


@dataclass(frozen=True)
class Play:
    steps: tuple[tuple[int, int, int], ...]  # (origine, destination, dé)
    final: Position

    def simple(self) -> list[Step]:
        return [(s, d) for s, d, _ in self.steps]


def legal_plays(pos: Position, dice: Sequence[int]) -> list[Play]:
    """Tous les jeux complets légaux (règle du maximum de dés utilisés incluse).

    Chaque séquence ordonnée distincte est retournée ; utiliser ``final.key()``
    pour regrouper les équivalences.
    """
    a, b = dice
    seqs = [(a,) * 4] if a == b else [(a, b), (b, a)]
    found: dict[tuple, Play] = {}
    best = 0

    def dfs(p: Position, remaining: tuple[int, ...], done: tuple) -> None:
        nonlocal best
        extended = False
        if remaining:
            die = remaining[0]
            for st in _step_options(p, die):
                extended = True
                dfs(apply_step(p, st), remaining[1:], done + (st + (die,),))
        if not extended:
            n = len(done)
            if n > best:
                best = n
                found.clear()
            if n == best:
                found.setdefault(done, Play(done, p))

    for s in seqs:
        dfs(pos, s, ())
    plays = list(found.values())
    # un seul dé jouable : obligation de jouer le plus grand si possible
    if a != b and best == 1:
        hi = max(a, b)
        big = [pl for pl in plays if pl.steps[0][2] == hi]
        if big:
            plays = big
    return plays


def next_steps(plays: Iterable[Play], done: Sequence[tuple[int, int, int]]) -> set[tuple[int, int, int]]:
    """Pas possibles après ``done`` (préfixe), d'après les jeux complets légaux."""
    n = len(done)
    res = set()
    for pl in plays:
        if len(pl.steps) > n and pl.steps[:n] == tuple(done):
            res.add(pl.steps[n])
    return res
