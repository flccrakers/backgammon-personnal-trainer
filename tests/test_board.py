from bgtrainer.domain.board import Position, legal_plays, apply_steps, next_steps

def test_opening_31_has_expected_equivalents():
    p = Position.initial()
    plays = legal_plays(p, (3, 1))
    finals = {pl.final.key() for pl in plays}
    assert len(finals) == 15 or len(finals) > 10
    mv = apply_steps(p, [(8, 5), (6, 5)])
    assert mv.key() in finals

def test_double_and_bar_entry():
    p = Position.initial()
    assert len(legal_plays(p, (6, 6))) >= 1
    mine = [0] * 25; mine[24] = 1; mine[5] = 14
    opp = [0] * 25; opp[23] = 2; opp[3] = 13   # points 1 et 22 adverses
    pos = Position(tuple(mine), tuple(opp))
    plays = legal_plays(pos, (1, 3))   # 25-1=24 bloqué par opp[0]? opp point 1 => notre 24
    assert all(pl.steps[0][0] == 25 for pl in plays)

def test_hit_sends_to_bar():
    mine = [0]*25; mine[12] = 2
    opp = [0]*25; opp[24-8] = 1; opp[0] = 14
    pos = Position(tuple(mine), tuple(opp))
    after = apply_steps(pos, [(13, 8)])
    assert after.opp[24] == 1

def test_bearoff_and_forced_larger_die():
    mine = [0]*25; mine[0] = 2; mine[1] = 2
    pos = Position(tuple(mine), tuple([0]*25))
    plays = legal_plays(pos, (6, 5))
    assert plays and all(len(pl.steps) == 2 for pl in plays)
    assert next_steps(plays, ())

def test_no_move():
    mine = [0]*25; mine[24] = 1; mine[5]=14
    opp=[0]*25
    for i in range(18, 24): opp[i] = 2   # nos points 1..6 bloqués -> opp idx 24-p
    opp=[0]*25
    for p in range(19, 25): opp[24-(25-p)] = 0
    # bloque 19..24 (entrée) : opp point q adverse = notre 25-q ; entrer avec d -> 25-d
    for d in range(1, 7): opp[24-(25-d)] = 2
    pos = Position(tuple(mine), tuple(opp))
    assert legal_plays(pos, (2, 3)) == [] or all(not pl.steps for pl in legal_plays(pos, (2, 3)))
