"""Transforme la sortie gnubg (JSON) en exercices (classes douteux/mauvais/très mauvais ; déterministe, sans E/S)."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.board import BOARD_SCHEMA_VERSION, Position, apply_steps, legal_plays

KEEP_CLASSES = ("doubtful", "bad", "very bad")


@dataclass
class ExerciseDraft:
    logical_key: str
    kind: str
    game_index: int
    action_index: int
    player_name: str
    player_color: str
    position: dict
    dice: list | None
    cube_value: int
    cube_owner: str | None
    offered_cube: int | None
    score_me: int | None
    score_opp: int | None
    match_length: int | None
    crawford: bool
    played: dict
    best: dict
    accepted: list
    equity_loss: float | None
    metric: str | None
    extra: dict = field(default_factory=dict)
    classification: str = "very bad"
    board_schema_version: int = BOARD_SCHEMA_VERSION


def _other(c: str) -> str:
    return "O" if c == "X" else "X"


def _steps(mv: list) -> list[tuple[int, int]]:
    return [(int(a), int(b)) for a, b in mv]


def build_exercises(data: dict, match_key: str, tolerance: float = 0.001,
                    classes: tuple[str, ...] = KEEP_CLASSES) -> tuple[list[ExerciseDraft], list[str]]:
    """Retourne (exercices, avertissements). Ne retient que les classes de `classes`."""
    out: list[ExerciseDraft] = []
    warns: list[str] = []
    names = {"X": data["match"]["X"] or "X", "O": data["match"]["O"] or "O"}
    length = data["match"].get("length")
    for g in data["games"]:
        score = g["score"]
        for d in g["decisions"]:
            if d.get("skill") not in classes:
                continue
            color = d["player"]
            ex = None
            try:
                if d["kind"] == "move":
                    ex = _move(d, g, color, names, length, match_key, tolerance)
                else:
                    ex = _cube(d, g, color, names, length, match_key)
            except Exception as e:  # décision non exploitable : jamais d'exercice inventé
                warns.append(f"game {g['index']} action {d.get('action_index')}: non analysable ({e})")
            if ex:
                ex.classification = d["skill"]
                out.append(ex)
    return out, warns


def _ctx(g, color, d):
    me, opp = ("X", "O") if color == "X" else ("O", "X")
    sc = g["score"]
    owner = d.get("owner")
    rel = None if owner is None else ("me" if owner == color else "opp")
    return sc.get(me), sc.get(opp), rel


def _move(d, g, color, names, length, match_key, tol) -> ExerciseDraft:
    pos = Position.from_dict(d["position"])
    cands = d["candidates"]
    if not cands:
        raise ValueError("aucun candidat")
    imove = d["imove"]
    if imove is None or not (0 <= imove < len(cands)):
        raise ValueError("coup joué absent de la liste analysée")
    best_score = max(c["score"] for c in cands)
    played_score = cands[imove]["score"]
    legal = {pl.final.key() for pl in legal_plays(pos, d["dice"])}
    accepted, seen = [], set()
    for c in cands:
        if c["score"] < best_score - tol:
            continue
        fin = apply_steps(pos, _steps(c["move"]))
        k = fin.key()
        if k not in legal:
            raise ValueError("candidat illégal selon le moteur de règles interne")
        if k in seen:
            continue
        seen.add(k)
        accepted.append({"move": c["move"], "final": fin.to_dict(), "key": k, "score": c["score"]})
    best = max(cands, key=lambda c: c["score"])
    played_final = apply_steps(pos, _steps(d["played"]))
    if played_final.key() in seen:
        raise ValueError("coup joué équivalent à une réponse acceptée")
    me_sc, opp_sc, rel = _ctx(g, color, d)
    accepted_keys = {a["key"] for a in accepted}
    stats = []
    for i, c in enumerate(cands):
        if i >= 12 and i != imove:
            continue
        stats.append({"move": c["move"], "equity": c["score"], "diff": c["score"] - best_score,
                      "probs": c.get("probs"), "plies": c.get("plies"),
                      "played": i == imove, "best": c["score"] >= best_score - 1e-12})
    return ExerciseDraft(
        logical_key=f"{match_key}:{g['index']}:{d['action_index']}:move",
        kind="move", game_index=g["index"], action_index=d["action_index"],
        player_name=names[color], player_color=color, position=pos.to_dict(),
        dice=list(d["dice"]), cube_value=d["cube"], cube_owner=rel, offered_cube=None,
        score_me=me_sc, score_opp=opp_sc, match_length=length, crawford=bool(g.get("crawford")),
        played={"move": d["played"], "final": played_final.to_dict(), "score": played_score},
        best={"move": best["move"], "score": best["score"]},
        accepted=accepted, equity_loss=best_score - played_score, metric="equity",
        extra={"analysis": {"type": "move", "plies": data_plies(d), "candidates": stats,
                            "total_candidates": len(cands)}},
    )


def data_plies(d) -> int | None:
    for c in d.get("candidates", []):
        if c.get("plies") is not None:
            return c["plies"]
    return None


def _cube(d, g, color, names, length, match_key) -> ExerciseDraft:
    act = d["action"]
    if act in ("take", "drop"):
        if "position_double" not in d:
            raise ValueError("position du double absente")
        pos = Position.from_dict(d["position_double"]).flipped()
        played = "take" if act == "take" else "pass"
        best = "pass" if act == "take" else "take"
        offered = d["cube"] * 2
        options = ["take", "pass"]
    else:
        if "position" not in d:
            raise ValueError("position absente")
        pos = Position.from_dict(d["position"])
        played = "double" if act == "double" else "no_double"
        best = "no_double" if act == "double" else "double"
        offered = None
        options = ["double", "no_double"]
    me_sc, opp_sc, rel = _ctx(g, color, d)
    extra = {"options": options, "engine_action": act}
    for k in ("nd-cubeful-eq", "dt-cubeful-eq", "nd-match-eq", "dt-match-eq"):
        if k in d:
            extra[k] = d[k]
    extra["analysis"] = {
        "type": "cube",
        "nd": d.get("nd-cubeful-eq"), "dt": d.get("dt-cubeful-eq"), "dp": 1.0,
        "nd_match": d.get("nd-match-eq"), "dt_match": d.get("dt-match-eq"),
        "probs": d.get("probs"), "asked": "double" if act in ("double", "no_double") else "response",
    }
    return ExerciseDraft(
        logical_key=f"{match_key}:{g['index']}:{d['action_index']}:cube",
        kind="cube", game_index=g["index"], action_index=d["action_index"],
        player_name=names[color], player_color=color, position=pos.to_dict(), dice=None,
        cube_value=d["cube"], cube_owner=rel, offered_cube=offered,
        score_me=me_sc, score_opp=opp_sc, match_length=length, crawford=bool(g.get("crawford")),
        played={"action": played}, best={"action": best}, accepted=[best],
        equity_loss=None, metric=None, extra=extra,
    )
