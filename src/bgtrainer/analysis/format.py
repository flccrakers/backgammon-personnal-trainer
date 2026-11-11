"""Mise en forme texte des statistiques gnubg (pur, sans GUI)."""
from __future__ import annotations


def move_text(mv: list) -> str:
    return " ".join(f"{'bar' if a == 25 else a}/{'off' if b == 0 else b}" for a, b in mv) or "(aucun coup)"


def _pct(x: float | None) -> str:
    return "  -  " if x is None else f"{100 * x:5.1f}"


def _probs(p: list | None) -> tuple[str, str, str, str, str, str]:
    if not p or len(p) < 5:
        return ("  -  ",) * 6
    win, wg, wbg, lg, lbg = p[:5]
    return _pct(win), _pct(wg), _pct(wbg), _pct(1 - win), _pct(lg), _pct(lbg)


def analysis_text(analysis: dict | None, plies: int | None = None, answer: list | None = None) -> str:
    if not analysis:
        return "Statistiques gnubg indisponibles pour cet exercice (relancez un scan après avoir vidé la base)."
    if analysis["type"] == "move":
        return _moves(analysis, plies, answer)
    return _cube(analysis, plies)


def _moves(a: dict, plies: int | None, answer: list | None = None) -> str:
    head = f"gnubg {a.get('plies', plies)} plies  ( * meilleur, M match, J vous )"
    cols = f"{'':3} {'Coup':<17}{'Équité':>7} {'Écart':>7} {'Gagne':>6}"
    lines = [head, cols, "-" * len(cols)]
    mine = sorted(tuple(x) for x in answer) if answer else None
    for c in a["candidates"]:
        is_mine = mine is not None and sorted(tuple(x) for x in c["move"]) == mine
        mark = ("*" if c["best"] else " ") + ("M" if c["played"] else " ") + ("J" if is_mine else " ")
        w = _probs(c.get("probs"))[0].strip()
        lines.append(f"{mark:3} {move_text(c['move']):<17}{c['equity']:>+7.3f} {c['diff']:>+7.3f} {w + ('' if w == '-' else '%'):>6}")
    hidden = a.get("total_candidates", len(a["candidates"])) - len(a["candidates"])
    if hidden > 0:
        lines.append(f"... {hidden} autre(s) coup(s) moins bons non affichés")
    return "\n".join(lines)


def _cube(a: dict, plies: int | None) -> str:
    nd, dt, dp = a.get("nd"), a.get("dt"), a.get("dp", 1.0)
    f = lambda x: "  -  " if x is None else f"{x:+.3f}"
    lines = [f"Analyse gnubg du cube ({plies} plies)"]
    w, wg, wbg, l, lg, lbg = _probs(a.get("probs"))
    lines.append(f"Gagne {w}%  (gammon {wg}%, BG {wbg}%)")
    lines.append(f"Perd  {l}%  (gammon {lg}%, BG {lbg}%)")
    lines.append(f"  Pas de double (ND)   : {f(nd)}")
    lines.append(f"  Double/prise (D/T)   : {f(dt)}")
    lines.append(f"  Double/passe (D/P)   : {f(dp)}")
    if nd is not None and dt is not None:
        dbl = min(dt, dp)
        best = "Double" if dbl > nd else "Pas de double"
        resp = "Prise" if dt <= dp else "Passe"
        lines.append(f"  Meilleur : {best}" + (f" / {resp}" if best == "Double" else "") + f"   (écart ND - D = {abs(nd - dbl):.3f})")
    return "\n".join(lines)
