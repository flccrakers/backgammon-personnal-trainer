# Backgammon: simple rules extracted from 200 matches

Source: 100 GM-vs-GM matches and 100 GM-vs-beginner matches. The GM is GNUBG at 2-ply. The beginner is 0-ply with noise.
I replayed every move with my own rules engine. That covers about 36,500 checker plays, with every legal alternative generated for each one.
The percentages below say how often the GM picked the option with that property, when at least one option had it and at least one didn't.
They are measured, not guessed.

Numbering: your own points go 1 to 24, with 1 being your home-board corner. 24 is your back anchor point and 7 is the bar point.
Your home board is points 1-6.

---

## 0. Order of priority

Go through the list from top to bottom and stop at the first rule that applies.
This hierarchy alone matches the GM about 44% of the time, against 11% at random. A full linear model gets about 57% on contact positions.
The rest of the GM's choice comes from subtle equity calculations that nobody can do by hand.

1. Opening: use the table in section 1.
2. Can you hit two checkers, or hit in the outfield or on your side of the board? Hit (rule 2).
3. Can you make your 6, 5 or 4 point, or the bar point? Do it (rule 3).
4. Otherwise, play safe and keep the structure tidy (rules 4 and 5).
5. If there is no contact, race (rules 8 and 9).

---

## 1. Opening: play the same move every time

The GM played the same move in the large majority of cases, usually 85-100% of the time.

| Roll | Move | Roll | Move |
|---|---|---|---|
| 2-1 | 13/11 24/23 (or 13/11 6/5) | 5-2 | 13/8 24/22 |
| 3-1 | 8/5 6/5 (make the 5 point) | 5-3 | 8/3 6/3 (make the 3 point) |
| 3-2 | 24/21 13/11 | 5-4 | 13/8 24/20 |
| 4-1 | 13/9 24/23 | 6-1 | 13/7 8/7 (make the bar point) |
| 4-2 | 8/4 6/4 (make the 4 point) | 6-2 | 24/18 13/11 |
| 4-3 | 13/9 24/21 | 6-3 | 24/18 13/10 |
| 5-1 | 13/8 24/23 | 6-4 | 24/18 13/9 (or 8/2 6/2 or 24/14) |
| 6-5 | 24/18 18/13 ("lover's leap") | | |

Doubles:
- 1-1: 8/7(2) 6/5(2).
- 2-2: 13/11(2) 6/4(2).
- 3-3: 24/21(2) 13/10(2).
- 4-4: 24/20(2) 13/9(2).
- 5-5: 13/8(2) 8/3(2).
- 6-6: 24/18(2) 13/7(2).

Memory aid: with 3-1, 4-2, 5-3 and 6-1 you make a point (5, 4, 3 and bar). Otherwise you either run one back checker or bring a builder down from the midpoint.

---

## 2. Hitting

| Where the hit lands | GM hits |
|---|---|
| Your opponent's outfield or home board (your points 13-24) | about 90% |
| Your outfield (points 8-12) | about 83% |
| Your bar point (7) | about 70% |
| Your 4 or 5 point | about 50% |
| Your 3 point | about 30% |
| Your 1 or 2 point | only 14%, so don't. Deep hits are usually wrong. |

Further hit rules:
- Double hit (two checkers on the bar): the GM does it 78% of the time when both hits are outside your home board (points 7 and up), but only 24% when one of them is in your home board.
- Hit by pointing on the checker (making the point on top of it) is a bit better than hitting loose.
- When the opponent is already on the bar and you have home points, the GM is somewhat more willing to hit (about 55% against 35-40% otherwise, for hits in your home board).
- Hitting loose in your own board (points 1-3) is often wrong. First count what you give back: if a return shot costs you a lot, don't hit.

---

## 3. Making points (the most reliable rule)

When a move makes the point, the GM chose it this often:
- 6 point: 96%
- 5 point: 91%
- 4 point: 85%
- 8 point: 82%
- Bar point (7): 71%
- 3 point: 72%
- 20 anchor (opp's 5 point): 69%
- More points in your home board overall: 81%

The order of value is 6, 5, 4, bar, 8, 3 and then 2 and 1.
Making a point beats hitting when it's the 6 or 5 point (the GM chose the point over a hit 389 times to 137 for the 5 point and 124 to 10 for the 6 point).
For the 4 point the choice is close to even, and the bar point against a hit is even.
Think of the points as a prime. Having a block of 4 or 5 consecutive points is worth a lot: the GM prefers a longer prime 78-86% of the time.

---

## 4. Safety

- Don't slot (leave a single checker on) the 5, 4 or bar point unless you must. Slots are avoided 85-93% of the time. This is the strongest "don't".
- Don't leave a blot in your home board that can be hit. The GM avoids it about 86% of the time.
- Count your exposure. If you must leave a shot, make it the smaller one. At roughly 11% (a 4-or-fewer-roll shot) the GM picks the safer option about 75% of the time.
- The stronger the opponent's board, the less the GM hits loose in its own home board (41% with 1 point against 34% with 4 points, when the opponent is not on the bar).
- Leaving fewer blots is not a goal in itself (the GM chose the move with fewer blots only about half the time). What matters is the chance of getting hit and what it costs.

---

## 5. Structure: avoid deep checkers and gaps

- Don't bury checkers on your 1 and 2 points (the "deep" points) while others are still back. The GM avoids it 79% of the time.
- Fill the board in order, 6 then 5 then 4. A 6-5-4-3 board beats having the same number of checkers spread with holes.
- Don't stack more than 3 or 4 checkers on one point. This was a small but consistent effect.
- Keep spare builders (single spare checkers) on points 7 to 12 aimed at the points you want to make.
- Midpoint and 8 point: keep them as long as it's cheap. They are the source of builders.
- Making an advanced anchor (your 20 or 21 point) was chosen 64-69% of the time when available. Having more checkers on 24 or 23 is mildly penalised in the fit.
- The advanced anchors (opp's 5 and 4 points: your points 20 and 21) are good. The 24 and 23 anchors are weaker.

---

## 6. Back checkers (running or staying)

- Opening: run one back checker with 6-2, 6-3 and 6-5 (24/18). Don't leave both back until late.
- When behind in the race by more than 8%, the GM hits and stays back more, and does not hurry to run. It plays for hits and holds an anchor.
- When ahead in the race by more than 8%, it plays safe (it picked the least-risk move 68% of the time, against 55% when behind). Get the back checkers out.
- Evens: keep two checkers together as an anchor.

---

## 7. Mid-game plan in short

1. Count the race (pips). Ahead means play safe and run. Behind means hit and hold an anchor.
2. Make home points with the builders you have.
3. Keep your checkers connected (a spare 2-6 pips from the point you want).
4. Don't leave a shot if a move that doesn't is almost as good.

---

## 8. What changed against the beginner

The GM plays the same way, so these rules hold for both. The beginner's choices matched them much less often:
- Making the 5 point: GM 91%, beginner 72%.
- Making the bar point: GM 71%, beginner 51%.
- Playing the safest move: GM 65%, beginner 44%.
- Choosing 0 blots: GM 52%, beginner 33% (which is a mistake, because it also fails to take the better hit).

The beginner's main errors are leaving unnecessary shots and slotting, not making key points, and burying checkers deep.

---

## 9. Race / bear-off (no more contact)

- Bear off the maximum number of checkers whenever you can. The GM does it 89% of the time.
- If you can't take a checker off, fill the gaps and avoid wasting pips. Move the farthest checkers into the home board first (64%).
- When no checker can come off, pick the move that leaves the fewest pips. In 90% of cases the GM minimises pips.
- Prefer not to pile checkers on the 6 point (the GM chose the lower stack on 6 only 6% of the time when it could choose a higher one: it keeps checkers moving forward).
- Ignore holes and gaps in the bear-off (the GM chose fewer gaps only 30% of the time). Efficiency comes first.

---

## 10. The doubling cube (less reliable: small sample)

Only about 766 GM cube decisions were available, so treat this as a rough guide.
- GM doubles about 4% of contact turns and about 3% of pure-race turns.
- Doubles come early: the middle double is on about the 6th move, and a quarter of doubles come by the 3rd.
- Pure race (only about 55 doubles in the sample): the GM doubled with a lead of about 8% or more. Takes occurred at leads of 6% to 14%. Almost all doubles with a lead of 15% or more were dropped.
  Rule of thumb (rough): double from about 8%, take if the lead is under about 12%, pass beyond that. The sample is too small for finer thresholds.
- Contact positions: the average double comes at about a 9% pip lead, with 3 or more home points. You double with a strong board, a prime of 3 or more, and a hit chance.
- Contact: drop vs take. Opponents who dropped had a larger lead (14% on average against 7% for takes), and the doubler had more home points (3.3 against 2.6) and a longer prime (3.1 against 2.6).
  Rule of thumb (rough): take if the lead is under about 10%, drop if it's above about 15-20% with a strong board.
- Very large pip leads (60%+) in contact positions were almost never doubled (1.3% of turns). The data can't tell why, probably because the GM plays on for a gammon or the position was already a pass.
- Rarely redouble. Only 104 of 712 doubles were redoubles.

---

## 11. Pocket version (the 12 rules)

1. Opening: use the table.
2. Make the 6, 5 or 4 point before anything else.
3. Make the bar point or the 8 point if you can.
4. Hit when it's far from your home (outfield, or the opponent's side). Don't hit deep (points 1-2).
5. Hit two checkers when both hits are outside your home board.
6. Never slot the 5, 4 or bar point if there's an alternative.
7. Don't leave a home-board blot to direct shots.
8. Don't bury checkers on points 1 and 2.
9. Ahead in the race: run and play safe. Behind: hold an anchor and hunt for hits.
10. Move the back anchor up to point 20 or 21 when you can.
11. Race: bear off as many as possible, otherwise the fewest pips.
12. Cube (rough): double with a lead of about 8-15% and a good board; take if the lead is under about 10%.

## Limits

- These rules approximate a 2-ply bot. Their combined accuracy is about 44-57% for exact move matches. They find a sound move far more often than they find the single best move.
- Exceptions exist that these rules can't capture (timing, gammon chances, match score). Each match here is to 7 points, and score-dependent play isn't covered.
- The scripts used are in `analyse/` (`bg.py` replays matches, `feats.py` builds features, `fit.py`, `hier.py`, `cond.py` produce the statistics).
