"""Coaching : explique un coup ou une décision de cube à l'aide de docs/REGLES_BACKGAMMON.md.

Module pur (sans GUI ni base). Le moteur gnubg reste l'arbitre : ces règles sont des
heuristiques (44 à 57 % de concordance avec le coup exact). Les explications servent à
comprendre POURQUOI un coup est préféré, pas à le juger.

Les renvois « §n » désignent les sections de REGLES_BACKGAMMON.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from typing import Sequence

from ..domain.board import Position, apply_step, legal_plays

Steps = Sequence[Sequence[int]]


@dataclass(frozen=True)
class Remark:
    kind: str   # "ok" (règle suivie), "bad" (règle non respectée), "info"
    text: str


# --------------------------------------------------------------------------- ouverture (§1)
def _o(s: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for tok in s.split():
        n = 1
        if tok.endswith(")"):
            tok, c = tok[:-1].split("(")
            n = int(c)
        a, b = tok.split("/")
        out += [(int(a), int(b))] * n
    return out


OPENING: dict[tuple[int, int], list[str]] = {
    (2, 1): ["13/11 24/23", "13/11 6/5"],
    (3, 1): ["8/5 6/5"],
    (3, 2): ["24/21 13/11"],
    (4, 1): ["13/9 24/23"],
    (4, 2): ["8/4 6/4"],
    (4, 3): ["13/9 24/21"],
    (5, 1): ["13/8 24/23"],
    (5, 2): ["13/8 24/22"],
    (5, 3): ["8/3 6/3"],
    (5, 4): ["13/8 24/20"],
    (6, 1): ["13/7 8/7"],
    (6, 2): ["24/18 13/11"],
    (6, 3): ["24/18 13/10"],
    (6, 4): ["24/18 13/9", "8/2 6/2", "24/18 18/14"],
    (6, 5): ["24/18 18/13"],
    (1, 1): ["8/7(2) 6/5(2)"],
    (2, 2): ["13/11(2) 6/4(2)"],
    (3, 3): ["24/21(2) 13/10(2)"],
    (4, 4): ["24/20(2) 13/9(2)"],
    (5, 5): ["13/8(2) 8/3(2)"],
    (6, 6): ["24/18(2) 13/7(2)"],
}
MAKE_POINT_OPENINGS = {(3, 1): 5, (4, 2): 4, (5, 3): 3, (6, 1): 7}
POINT_NAME = {7: "la barre (point 7)", 20: "l'ancre avancée (point 20)", 21: "l'ancre avancée (point 21)"}
MAKE_FREQ = {6: 96, 5: 91, 4: 85, 8: 82, 7: 71, 3: 72, 20: 69}
MAKE_ORDER = [6, 5, 4, 7, 8, 3, 20, 21, 2, 1]


def _pname(p: int) -> str:
    return POINT_NAME.get(p, f"le point {p}")


# --------------------------------------------------------------------------- utilitaires plateau
def _replay(pos: Position, steps: Steps) -> tuple[Position, list[int]]:
    """Rejoue les pas ; renvoie (position finale, points frappés)."""
    st = [(int(a), int(b)) for a, b in steps]

    def run(seq):
        p, hits = pos, []
        for s in seq:
            if 1 <= s[1] <= 24 and p.count_opp_at(s[1]) == 1:
                hits.append(s[1])
            p = apply_step(p, s)
        return p, hits

    try:
        return run(st)
    except ValueError:
        for perm in set(permutations(st)):
            try:
                return run(perm)
            except ValueError:
                continue
        raise


def _contact(p: Position) -> bool:
    if p.mine[24] or p.opp[24]:
        return True
    mine = [i + 1 for i in range(24) if p.mine[i]]
    opp = [q for q in range(1, 25) if p.count_opp_at(q)]
    return bool(mine and opp and max(mine) > min(opp))


def _shots(final: Position) -> int:
    """Nombre de jets (sur 36) permettant à l'adversaire de frapper un de nos pions."""
    fl = final.flipped()
    base = fl.opp[24]
    n = 0
    for a in range(1, 7):
        for b in range(a, 7):
            if any(pl.final.opp[24] > base for pl in legal_plays(fl, (a, b))):
                n += 1 if a == b else 2
    return n


def _attackers(f: Position, p: int) -> bool:
    return bool(f.opp[24]) or any(f.count_opp_at(q) for q in range(1, p))


def _direct(f: Position, p: int) -> bool:
    return (bool(f.opp[24]) and p <= 6) or any(f.count_opp_at(q) for q in range(max(1, p - 6), p))


def _prime(mine: Sequence[int]) -> int:
    best = run = 0
    for i in range(24):
        run = run + 1 if mine[i] >= 2 else 0
        best = max(best, run)
    return best


def _features(start: Position, steps: Steps) -> dict:
    f, hits = _replay(start, steps)
    m = f.mine
    blots = [p for p in range(1, 25) if m[p - 1] == 1]
    back = m[24] + sum(m[18:24])
    contact = _contact(f)
    return {
        "final": f,
        "hits": hits,
        "contact": contact,
        "made": [p for p in range(1, 25) if m[p - 1] >= 2 and start.mine[p - 1] < 2],
        "slots": [p for p in (4, 5, 7) if m[p - 1] == 1 and start.mine[p - 1] == 0
                  and p not in hits and _attackers(f, p)],
        "home_blots": [p for p in blots if p <= 6 and _direct(f, p)],
        "buried": (m[0] + m[1] > start.mine[0] + start.mine[1]) and back > 0,
        "stacks": [p for p in range(1, 25) if m[p - 1] >= 5 and m[p - 1] > start.mine[p - 1]],
        "home_pts": sum(1 for p in range(1, 7) if m[p - 1] >= 2),
        "prime": _prime(m),
        "off": f.off_mine() - start.off_mine(),
        "pips": f.pips_mine(),
        "six": m[5],
        "shots": _shots(f) if contact else 0,
    }


def _hit_freq(p: int) -> str:
    if p >= 13:
        return "environ 90 % des cas"
    if p >= 8:
        return "environ 83 % des cas"
    if p == 7:
        return "environ 70 % des cas"
    if p in (4, 5):
        return "environ 50 % des cas"
    if p == 3:
        return "environ 30 % des cas"
    if p <= 2:
        return "seulement 14 % des cas"
    return "assez souvent"


def _pct(n: int) -> str:
    return f"{n}/36 = {100 * n / 36:.0f} %"


# --------------------------------------------------------------------------- commentaires d'un coup
def _positives(f: dict, start: Position) -> list[Remark]:
    """Règles que respecte ce coup (par ordre de priorité du §0)."""
    out: list[Remark] = []
    hits = f["hits"]
    if len(hits) >= 2:
        loc = "tous deux hors de votre jan intérieur" if min(hits) >= 7 else "dont un dans votre jan intérieur"
        out.append(Remark("ok", f"Double frappe ({loc}) : le GM frappe deux pions dans 78 % des cas quand les deux "
                                f"frappes sont à partir du point 7 (24 % si l'une est dans le jan). Règle 2, §2."))
    elif hits:
        p = hits[0]
        extra = " Faire le point en frappant est encore mieux." if p in f["made"] else ""
        out.append(Remark("ok", f"Frappe au point {p} : le GM frappe à cet endroit dans {_hit_freq(p)}. "
                                f"Règle 2, §2.{extra}"))
    for p in sorted(f["made"], key=lambda x: MAKE_ORDER.index(x) if x in MAKE_ORDER else 99):
        if p in MAKE_FREQ or p == 21:
            fr = f" (choisi dans {MAKE_FREQ[p]} % des cas)" if p in MAKE_FREQ else ""
            out.append(Remark("ok", f"Fait {_pname(p)}{fr}. Règle 3, §3 : ordre de valeur 6, 5, 4, barre, 8, 3, puis 2 et 1."))
    if f["prime"] >= 4:
        out.append(Remark("ok", f"Prime de {f['prime']} points consécutifs : préféré 78 à 86 % du temps (§3)."))
    if f["contact"]:
        if f["shots"] == 0:
            out.append(Remark("ok", "Ne laisse aucun tir à l'adversaire. Règle 4, §4."))
        elif f["shots"] <= 4:
            out.append(Remark("ok", f"Laisse très peu de tirs ({_pct(f['shots'])}) : sous ~11 %, le GM choisit l'option "
                                    f"sûre environ 75 % du temps. Règle 4, §4."))
    else:
        if f["off"]:
            out.append(Remark("ok", f"Sort {f['off']} pion(s) : le GM sort le maximum de pions (89 %). Règle 8, §9."))
    return out


def _vs_best(u: dict, b: dict, start: Position) -> list[Remark]:
    """Écarts entre votre coup (u) et le meilleur (b), expliqués par les règles."""
    out: list[Remark] = []
    # 2. frappes
    if b["hits"] and not u["hits"]:
        p = min(b["hits"])
        out.append(Remark("bad", f"Le meilleur coup frappe au point {p} ({_hit_freq(p)} chez le GM). "
                                 f"Vous n'avez pas frappé. Règle 2, §2 : frapper en zone extérieure ou de son côté "
                                 f"est presque toujours bon."))
    elif u["hits"] and not b["hits"]:
        p = min(u["hits"])
        if p <= 3:
            out.append(Remark("bad", f"Frappe profonde au point {p} : le GM ne le fait que dans {_hit_freq(p)}. "
                                     f"Frapper seul aux points 1 à 3 est souvent faux : comptez d'abord ce que coûte le "
                                     f"coup de retour. Règle 4, §2."))
        else:
            out.append(Remark("bad", f"Votre frappe au point {p} n'est pas la meilleure ici : une autre priorité l'emporte "
                                     f"(faire un point clé ou rester sûr)."))
    elif len(b["hits"]) > len(u["hits"]):
        out.append(Remark("bad", "Le meilleur coup frappe deux pions (§2) ; vous n'en frappez qu'un."))
    # 3. points
    missed = [p for p in b["made"] if p not in u["made"] and (p in MAKE_FREQ or p == 21)]
    if missed:
        p = min(missed, key=lambda x: MAKE_ORDER.index(x) if x in MAKE_ORDER else 99)
        fr = f" (choisi dans {MAKE_FREQ[p]} % des cas)" if p in MAKE_FREQ else ""
        out.append(Remark("bad", f"Vous avez manqué de faire {_pname(p)}{fr}. Règle 3, §3 : c'est la règle la plus fiable ; "
                                 f"faire le point 6 ou 5 passe même avant une frappe."))
    if b["prime"] >= 4 and u["prime"] < b["prime"]:
        out.append(Remark("bad", f"Le meilleur coup construit un prime de {b['prime']} points ; le vôtre {u['prime']}. §3."))
    # 4. sécurité
    if u["slots"] and not b["slots"]:
        s = ", ".join(str(p) for p in u["slots"])
        out.append(Remark("bad", f"Vous slottez {_pname(u['slots'][0]) if len(u['slots']) == 1 else 'les points ' + s} "
                                 f"sous le tir adverse. Règle 6, §4 : ne jamais slotter le 5, le 4 ou la barre s'il y a "
                                 f"une alternative (évité 85 à 93 % du temps)."))
    if len(u["home_blots"]) > len(b["home_blots"]):
        s = ", ".join(str(p) for p in u["home_blots"])
        out.append(Remark("bad", f"Pion seul exposé dans votre jan intérieur (point {s}) sous tir direct. "
                                 f"Règle 7, §4 (évité environ 86 % du temps)."))
    if u["contact"] and u["shots"] - b["shots"] >= 4:
        out.append(Remark("bad", f"Votre coup laisse {_pct(u['shots'])} de tirs contre {_pct(b['shots'])} pour le meilleur. "
                                 f"Règle 4, §4 : comptez l'exposition et laissez le plus petit tir."))
    # 5. structure
    if u["buried"] and not b["buried"]:
        out.append(Remark("bad", "Vous enterrez un pion sur le point 1 ou 2 alors qu'il reste des pions en arrière. "
                                 "Règle 8, §5 (évité 79 % du temps)."))
    extra_stack = [p for p in u["stacks"] if p not in b["stacks"]]
    if extra_stack and u["contact"]:
        out.append(Remark("bad", f"Vous empilez {u['final'].mine[extra_stack[0] - 1]} pions sur le point {extra_stack[0]} : "
                                 f"évitez plus de 3 ou 4 pions par point et gardez des constructeurs aux points 7 à 12. §5."))
    # 9. course
    if not u["contact"] and not b["contact"]:
        if u["off"] < b["off"]:
            out.append(Remark("bad", "Le meilleur coup sort plus de pions. Règle 8, §9 : sortir le maximum (89 %)."))
        elif u["off"] == b["off"] and u["pips"] > b["pips"]:
            out.append(Remark("bad", f"Vous gaspillez {u['pips'] - b['pips']} pip(s) : sans sortie possible, minimisez les pips "
                                     f"restants (90 %). §9."))
        if u["six"] > b["six"]:
            out.append(Remark("bad", "Vous empilez sur le point 6 : le GM choisit la pile la plus basse seulement 6 % du "
                                     "temps (§9)."))
    return out


def _context(start: Position, u: dict | None, b: dict) -> list[Remark]:
    if not b["contact"]:
        return []
    mine, opp = start.pips_mine(), start.pips_opp()
    lead = (opp - mine) / max(opp, mine) * 100
    if lead >= 8:
        t = (f"Vous avez {lead:.0f} % d'avance à la course (§6) : jouez sûr (68 % contre 55 % en retard) et sortez les "
             f"pions arrière.")
    elif lead <= -8:
        t = (f"Vous avez {-lead:.0f} % de retard à la course (§6) : frappez et restez derrière avec une ancre.")
    else:
        t = "Course à peu près égale (§6) : gardez deux pions ensemble comme ancre."
    return [Remark("info", t)]


def _opening(start: Position, dice: Sequence[int], user: Steps | None) -> list[Remark]:
    if start != Position.initial():
        return []
    key = (max(dice), min(dice))
    table = OPENING.get(key)
    if not table:
        return []
    finals = {apply_all(start, _o(t)).key() for t in table}
    shown = " ou ".join(table)
    hint = ""
    if key in MAKE_POINT_OPENINGS:
        hint = f" Aide-mémoire : avec ce jet on fait un point ({MAKE_POINT_OPENINGS[key]})."
    if user is None:
        return [Remark("info", f"Ouverture {key[0]}-{key[1]} : le GM joue presque toujours {shown} (85 à 100 %). "
                               f"Règle 1, §1.{hint}")]
    if _replay(start, user)[0].key() in finals:
        return [Remark("ok", f"Coup d'ouverture standard {key[0]}-{key[1]} ({shown}), joué 85 à 100 % du temps par le GM. "
                             f"Règle 1, §1.")]
    return [Remark("bad", f"Ouverture {key[0]}-{key[1]} : le GM joue presque toujours {shown} (85 à 100 %). "
                          f"Règle 1, §1 : apprenez la table d'ouverture.{hint}")]


def apply_all(pos: Position, steps: Steps) -> Position:
    return _replay(pos, steps)[0]


NEAR_GOOD = 0.04  # écart d'équité sous lequel un coup faux est jugé « presque bon »


def user_loss(analysis: dict | None, user: Steps | None) -> float | None:
    """Perte d'équité de votre coup par rapport au meilleur, si gnubg l'a évalué."""
    return _diff_for(analysis, user)


def _diff_for(analysis: dict | None, user: Steps | None) -> float | None:
    if not analysis or not user:
        return None
    mine = sorted(tuple(x) for x in user)
    for c in analysis.get("candidates", []):
        if sorted(tuple(x) for x in c["move"]) == mine:
            return abs(c["diff"])
    return None


def explain_move(start: Position, dice: Sequence[int], best_moves: list, user: Steps | None,
                 analysis: dict | None = None) -> list[Remark]:
    """Explications règle par règle.

    ``best_moves`` : coups acceptés (le premier sert de référence). ``user`` : votre coup, ou
    None si vous demandez seulement la correction."""
    best = best_moves[0]
    bf = _features(start, best)
    uf = _features(start, user) if user else None
    correct = bool(user) and uf["final"].key() in {_replay(start, m)[0].key() for m in best_moves}
    out: list[Remark] = []

    out += _opening(start, dice, user)
    if user is None or correct:
        pos = _positives(bf if user is None else uf, start)
        head = "Règles appliquées par le meilleur coup :" if user is None else "Règles que suit votre coup :"
        if pos:
            out.append(Remark("info", head))
            out += pos
        else:
            out.append(Remark("info", "Aucune règle de priorité (ouverture, frappe, point clé, sécurité) ne dicte ce coup : "
                                      "le moteur le choisit sur des critères plus fins (timing, structure, cube)."))
    else:
        diffs = _vs_best(uf, bf, start)
        d = _diff_for(analysis, user)
        if diffs:
            out.append(Remark("info", "Ce qui ne va pas dans votre coup :"))
            out += diffs
        else:
            out.append(Remark("info", "Aucune règle simple du document ne distingue clairement votre coup du meilleur : "
                                      "la différence est fine, faites confiance au moteur."))
        if d is not None:
            if d < 0.02:
                out.append(Remark("info", f"Écart d'équité de {d:.3f} seulement : votre coup est pratiquement équivalent."))
            elif d >= 0.1:
                out.append(Remark("info", f"Écart d'équité de {d:.3f} : erreur importante."))
            else:
                out.append(Remark("info", f"Écart d'équité de {d:.3f}."))
        bp = _positives(bf, start)
        if bp:
            out.append(Remark("info", "Règles appliquées par le meilleur coup :"))
            out += bp
        up = [r for r in _positives(uf, start)]
        if up:
            out.append(Remark("info", "Ce que votre coup fait malgré tout correctement :"))
            out += up
    out += _context(start, uf, bf)
    return out


# --------------------------------------------------------------------------- cube (§10)
_CUBE = {"double": "Doubler", "no_double": "Ne pas doubler", "take": "Prendre", "pass": "Passer"}
_DISCLAIMER = ("Ces seuils sont approximatifs (échantillon faible, §10) : le score du match, les gammons et le cube "
               "modifient la décision.")


def _cube_suggestion(pos: Position, asked: str) -> tuple[str, list[str]]:
    """(action suggérée par les règles ou '', explications)."""
    mine, opp = pos.pips_mine(), pos.pips_opp()
    notes: list[str] = []
    contact = _contact(pos)
    if asked == "double":
        # le joueur au trait peut doubler
        lead = (opp - mine) / max(opp, 1) * 100
        home = sum(1 for p in range(1, 7) if pos.mine[p - 1] >= 2)
        prime = _prime(pos.mine)
        notes.append(f"Votre avance à la course : {lead:.0f} %.")
        if not contact:
            notes.append("Course pure : doubler à partir d'environ 8 % d'avance, l'adversaire prend sous ~12 %, passe au-delà.")
            return ("double" if lead >= 8 else "no_double"), notes
        notes.append(f"Contact : {home} point(s) dans votre jan intérieur, prime de {prime}. Le double moyen vient vers "
                     f"9 % d'avance, avec au moins 3 points au jan, un prime d'au moins 3 et une chance de frappe.")
        return ("double" if (lead >= 9 and home >= 3 and prime >= 3) else "no_double"), notes
    # prendre / passer : pos est vue du preneur, l'adversaire (doubleur) est « opp »
    lead = (mine - opp) / max(mine, 1) * 100  # avance du doubleur
    notes.append(f"Avance du doubleur à la course : {lead:.0f} %.")
    if not contact:
        notes.append("Course pure : prendre sous ~12 % d'avance du doubleur, passer au-delà. Presque tous les doubles à 15 % "
                     "ou plus sont refusés.")
        return ("take" if lead <= 12 else "pass"), notes
    home = sum(1 for i in range(6) if pos.opp[i] >= 2)
    notes.append(f"Contact : le doubleur a {home} point(s) dans son jan. Prendre sous ~10 % d'avance, passer au-dessus de "
                 f"15 à 20 % avec un bon jan (ceux qui passent avaient en moyenne 14 % d'avance contre 7 % pour ceux qui "
                 f"prennent).")
    if lead < 10:
        return "take", notes
    if lead > 15 and home >= 3:
        return "pass", notes
    return "", notes


def explain_cube(pos: Position, asked: str, best: str, user: str | None) -> list[Remark]:
    asked = "double" if asked == "double" else "response"
    sug, notes = _cube_suggestion(pos, "double" if asked == "double" else "response")
    out = [Remark("info", n) for n in notes]
    if sug == "":
        out.append(Remark("info", "Zone grise : les règles ne tranchent pas, seul le moteur peut décider."))
    elif sug == best:
        out.append(Remark("ok", f"La règle du cube (§10) suggère aussi « {_CUBE[sug]} » : le meilleur choix est cohérent "
                                f"avec elle."))
    else:
        out.append(Remark("info", f"La règle approximative du §10 suggérerait « {_CUBE[sug]} », mais le moteur préfère "
                                  f"« {_CUBE[best]} » : cette position sort du cas moyen (score, gammons, structure)."))
    if user is not None:
        if user == best:
            out.append(Remark("ok", f"Votre choix « {_CUBE[user]} » est le bon."))
        else:
            out.append(Remark("bad", f"Votre choix « {_CUBE[user]} » n'est pas le meilleur ; le meilleur est « {_CUBE[best]} »."))
    out.append(Remark("info", _DISCLAIMER))
    return out


# --------------------------------------------------------------------------- désaccord moteur / règles
def rules_conflict(start: Position, dice: Sequence[int], user: Steps, correct: bool) -> str | None:
    """Texte du désaccord si les règles du document contredisent le verdict du moteur, sinon None.

    * moteur « correct » mais votre coup viole une règle (slot, pion seul au jan, pion enterré, hors table d'ouverture) ;
    * moteur « faux » mais votre coup suit une règle forte (ouverture standard, point clé, frappe à distance)
      sans en violer aucune."""
    try:
        f = _features(start, user)
    except Exception:
        return None
    viol: list[str] = []
    if start == Position.initial():
        table = OPENING.get((max(dice), min(dice)))
        if table and f["final"].key() not in {apply_all(start, _o(t)).key() for t in table}:
            viol.append("hors de la table d'ouverture (§1)")
    if f["slots"]:
        viol.append("slot du 5, du 4 ou de la barre sous tir (§4)")
    if f["home_blots"]:
        viol.append("pion seul exposé dans votre jan intérieur (§4)")
    if f["buried"]:
        viol.append("pion enterré sur le point 1 ou 2 (§5)")
    if correct:
        if viol:
            return "Le moteur valide votre coup, mais les règles s'y opposent : " + ", ".join(viol) + "."
        return None
    if viol:
        return None
    why = []
    if start == Position.initial() and OPENING.get((max(dice), min(dice))):
        why.append("ouverture standard (§1)")
    key = [p for p in f["made"] if p in (4, 5, 6, 7, 8)]
    if key:
        why.append(f"point {key[0]} fait (§3)")
    far = [p for p in f["hits"] if p >= 7]
    if far:
        why.append(f"frappe au point {far[0]} (§2)")
    if why:
        return "Le moteur préfère un autre coup, mais les règles soutiennent le vôtre : " + ", ".join(why) + "."
    return None


def cube_conflict(pos: Position, asked: str, best: str) -> str | None:
    sug, _ = _cube_suggestion(pos, "double" if asked == "double" else "response")
    if sug and sug != best:
        return (f"Le moteur préfère « {_CUBE[best]} » alors que les règles du cube (§10) suggèrent "
                f"« {_CUBE[sug]} ».")
    return None
