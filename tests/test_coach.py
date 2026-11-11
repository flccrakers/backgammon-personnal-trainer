from bgtrainer.analysis.coach import explain_cube, explain_move
from bgtrainer.domain.board import Position


def test_opening_slot_is_flagged():
    r = explain_move(Position.initial(), (6, 2), [[(24, 18), (13, 11)]], [(13, 11), (6, 5)])
    assert any(k.kind == "bad" and "slotte" in k.text for k in r)


def test_opening_correct_is_ok():
    r = explain_move(Position.initial(), (3, 1), [[(8, 5), (6, 5)]], [(8, 5), (6, 5)])
    assert any(k.kind == "ok" and "point 5" in k.text for k in r)


def test_cube_wrong_choice():
    r = explain_cube(Position.initial(), "double", "no_double", "double")
    assert any(k.kind == "bad" for k in r)


def test_conflict_engine_ok_but_rules_violated():
    from bgtrainer.analysis.coach import rules_conflict
    assert rules_conflict(Position.initial(), (6, 2), [(13, 11), (6, 5)], True)
    assert rules_conflict(Position.initial(), (6, 2), [(24, 18), (13, 11)], True) is None


def test_conflict_engine_wrong_but_rules_follow():
    from bgtrainer.analysis.coach import rules_conflict
    assert rules_conflict(Position.initial(), (3, 1), [(8, 5), (6, 5)], False)
