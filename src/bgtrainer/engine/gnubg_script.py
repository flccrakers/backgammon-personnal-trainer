"""Script exécuté DANS gnubg (``gnubg -t -q -p gnubg_script.py``).

Entrées via variables d'environnement :
  BGT_INPUT   chemin du .mat
  BGT_OUTPUT  chemin du JSON produit
  BGT_PLIES   profondeur d'analyse (défaut 2)
  BGT_CLASSES classes de skill retenues, séparées par '|' (défaut 'doubtful|bad|very bad')

Ce module n'est pas importable hors de gnubg (module ``gnubg`` embarqué).
"""
import json
import os
import sys
import traceback

import gnubg  # noqa: E402  (fourni par l'interpréteur embarqué)

SCHEMA = 1
SCRIPT_VERSION = 2


def _side(board):
    return list(board)


def _pos(board_id):
    opp, mine = gnubg.positionfromid(board_id)
    # opp = adversaire du joueur au trait ; mine = joueur au trait.
    # Index 0..23 = points 1..24 (point de vue du joueur concerné), 24 = barre.
    return {"mine": list(mine), "opp": list(opp)}


def _moves(mv):
    return [[int(a), int(b)] for a, b in mv]


def run():
    src = os.environ["BGT_INPUT"]
    out = os.environ["BGT_OUTPUT"]
    plies = int(os.environ.get("BGT_PLIES", "2"))
    keep = set(os.environ.get("BGT_CLASSES", "doubtful|bad|very bad").split("|"))

    gnubg.command("set analysis chequerplay evaluation plies %d" % plies)
    gnubg.command("set analysis cubedecision evaluation plies %d" % plies)
    gnubg.command("set analysis moves on")
    gnubg.command("set analysis cube on")
    gnubg.command("set analysis luck off")
    # Le ~/.gnubg/gnubgautorc de l'utilisateur peut définir un joueur IA (gnubg 3 plies) et un délai :
    # « new session » ferait alors jouer des coups à l'IA (des dizaines de secondes) avant l'import.
    for cmd in ("set delay 0", "set automatic game off", "set automatic roll off", "set automatic move off",
                "set player 0 human", "set player 1 human"):
        gnubg.command(cmd)
    gnubg.command("new session")
    gnubg.command('import mat "%s"' % src)
    gnubg.command("analyse match")
    m = gnubg.match(1, 1, 0, 1)
    if not m:
        raise RuntimeError("gnubg n'a produit aucun match")
    info = m["match-info"]
    result = {
        "schema": SCHEMA,
        "plies": plies,
        "match": {
            "X": info.get("X", {}).get("name"),
            "O": info.get("O", {}).get("name"),
            "length": info.get("match-length", 0),
            "rules": info.get("rules", []),
        },
        "games": [],
        "stats": {"decisions": 0, "classes": {}},
    }
    stats = result["stats"]
    for gi, g in enumerate(m["games"]):
        gi_info = g["info"]
        cube, owner = 1, None
        pending = None
        crawford = bool(gi_info.get("crawford"))
        game = {
            "index": gi,
            "score": {"X": gi_info.get("score-X"), "O": gi_info.get("score-O")},
            "crawford": crawford,
            "winner": gi_info.get("winner"),
            "points": gi_info.get("points-won"),
            "decisions": [],
        }
        for ai, a in enumerate(g["game"]):
            act = a["action"]
            an = a.get("analysis") or {}
            player = a.get("player")
            if act == "move":
                cskill = an.get("cube-skill")
                if cskill:
                    stats["classes"]["cube:" + cskill] = stats["classes"].get("cube:" + cskill, 0) + 1
                if cskill in keep and a.get("board"):
                    d = {
                        "kind": "cube", "action_index": ai, "player": player,
                        "action": "no_double", "skill": cskill,
                        "cube": cube, "owner": owner, "pending_cube": None,
                        "position": _pos(a["board"]),
                    }
                    for k in ("nd-cubeful-eq", "dt-cubeful-eq", "nd-match-eq", "dt-match-eq"):
                        if k in an:
                            d[k] = an[k]
                    if an.get("probs"):
                        d["probs"] = list(an["probs"])
                    game["decisions"].append(d)
                skill = an.get("skill")
                if a.get("dice") and a.get("move") is not None and an:
                    stats["decisions"] += 1
                if skill:
                    stats["classes"][skill] = stats["classes"].get(skill, 0) + 1
                if skill in keep and an.get("moves") is not None:
                    cands = []
                    for c in an["moves"]:
                        cands.append({
                            "move": _moves(c["move"]), "score": c.get("score"),
                            "probs": list(c["probs"]) if c.get("probs") else None,
                            "plies": (c.get("evalcontext") or {}).get("plies", plies),
                        })
                    game["decisions"].append({
                        "kind": "move", "action_index": ai, "player": player,
                        "position": _pos(a["board"]), "dice": list(a["dice"]),
                        "played": _moves(a["move"]), "imove": an.get("imove"),
                        "skill": skill, "candidates": cands,
                        "cube": cube, "owner": owner,
                    })
            elif act in ("double", "take", "drop"):
                skill = an.get("skill")
                stats["decisions"] += 1
                if skill:
                    stats["classes"][skill] = stats["classes"].get(skill, 0) + 1
                if skill in keep:
                    d = {
                        "kind": "cube", "action_index": ai, "player": player,
                        "action": act, "skill": skill,
                        "cube": cube, "owner": owner,
                        "pending_cube": pending,
                    }
                    if a.get("board"):
                        d["position"] = _pos(a["board"])
                    for k in ("nd-cubeful-eq", "dt-cubeful-eq", "nd-match-eq", "dt-match-eq"):
                        if k in an:
                            d[k] = an[k]
                    if an.get("probs"):
                        d["probs"] = list(an["probs"])
                    game["decisions"].append(d)
                # suivi de l'état du cube
                if act == "double":
                    pending = cube * 2
                elif act == "take":
                    cube = pending or cube * 2
                    owner = player
                    pending = None
                else:
                    pending = None
            # position pour les décisions de réponse : celle du doubleur
        # pour take/drop, rattacher la position/équités du double précédent
        decs = game["decisions"]
        acts = g["game"]
        for d in decs:
            if d["kind"] == "cube" and d["action"] in ("take", "drop"):
                prev = acts[d["action_index"] - 1]
                if prev.get("action") == "double":
                    d["double_player"] = prev.get("player")
                    pan = prev.get("analysis") or {}
                    if prev.get("board"):
                        d["position_double"] = _pos(prev["board"])
                    for k in ("nd-cubeful-eq", "dt-cubeful-eq", "nd-match-eq", "dt-match-eq"):
                        if k in pan:
                            d[k] = pan[k]
                    if pan.get("probs"):
                        d["probs"] = list(pan["probs"])
        result["games"].append(game)

    with open(out + ".tmp", "w") as f:
        json.dump(result, f)
    os.replace(out + ".tmp", out)


try:
    run()
except Exception:
    with open(os.environ["BGT_OUTPUT"] + ".err", "w") as f:
        f.write(traceback.format_exc())
gnubg.command("exit") if False else None
