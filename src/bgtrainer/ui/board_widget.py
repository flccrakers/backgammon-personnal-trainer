"""Plateau (couleurs issues du thème ; pions noirs/blancs) (QPainter). Ne contient aucune logique de règles."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QPushButton, QSizePolicy, QWidget

from ..domain.board import Position
from . import theme

PW = 48        # largeur d'un point
BARW = 44
CUBEW = 56
OFFW = 64
TOP = 28
H = 480
CK = PW - 6    # diamètre pion
BX = CUBEW + 8
DIE = 46
DGAP = 10
CBW, CBH, CBGAP = 110, 32, 10  # boutons de décision de cube (unités plateau)


class BoardWidget(QWidget):
    pointClicked = pyqtSignal(int)  # 1..24, 25 = barre, 0 = sortie
    diceClicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.pos: Position | None = None
        self.selected: int | None = None
        self.targets: set[int] = set()
        self.arrows: list[tuple[list, str, bool]] = []  # (pas, couleur, pointillé)
        self.cube_value = 1
        self.cube_owner: str | None = None
        self.offered: int | None = None
        self.dice: tuple[int, int] | None = None
        self.show_pips = False
        self.LW = BX + 12 * PW + BARW + OFFW + 16
        self.LH = TOP + H + 30
        self.setMinimumSize(self.LW // 2, self.LH // 2)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prompt: str | None = None
        self._cube_btns: list[QPushButton] = []
        self._undo_btn: QPushButton | None = None
        self._ok_btn: QPushButton | None = None

    # ---- API ----
    def attach_move_buttons(self, undo: QPushButton, ok: QPushButton) -> None:
        """« Annuler » (moitié gauche du plateau) et « Valider » (à droite des dés) vivent sur le plateau."""
        self._undo_btn, self._ok_btn = undo, ok
        for b in (undo, ok):
            b.setParent(self)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.hide()
        self._place_buttons()

    def set_state(self, pos: Position, cube_value=1, cube_owner=None, offered=None) -> None:
        self.pos, self.cube_value, self.cube_owner, self.offered = pos, cube_value, cube_owner, offered
        self.selected, self.targets = None, set()
        self.update()

    def set_show_pips(self, on: bool) -> None:
        self.show_pips = on
        self.update()

    def set_dice(self, dice, used=()) -> None:
        self.dice = tuple(dice) if dice else None
        self.used_dice = tuple(used)
        self.update()

    def set_prompt(self, text: str | None) -> None:
        """Question affichée dans la moitié gauche du plateau (décision de cube)."""
        self.prompt = text
        self.update()

    def set_cube_buttons(self, options: list[tuple[str, object]]) -> None:
        """Boutons côte à côte, centrés dans la moitié droite. ``options`` : [(libellé, callback)]."""
        for b in self._cube_btns:
            b.hide()
            b.setParent(None)
            b.deleteLater()
        self._cube_btns = []
        for label, cb in options:
            b = QPushButton(label, self)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, f=cb: f())
            theme.set_role(b, "choice")
            b.show()
            self._cube_btns.append(b)
        self._place_buttons()

    def set_cube_buttons_enabled(self, on: bool) -> None:
        for b in self._cube_btns:
            b.setEnabled(on)

    def _place_buttons(self) -> None:
        sc, ox, oy = self._scale()
        if self._undo_btn and self._ok_btn:
            font = theme.make_font(max(8, int(14 * sc)), 600)
            ux = BX + 3 * PW - CBW / 2
            self._undo_btn.setFont(font)
            self._undo_btn.setGeometry(int(ox + ux * sc), int(oy + (TOP + H / 2 - CBH / 2) * sc), int(CBW * sc), int(CBH * sc))
            dx, dy = self._dice_origin()
            okw = 90
            self._ok_btn.setFont(font)
            self._ok_btn.setGeometry(int(ox + (dx + 2 * DIE + DGAP + 14) * sc), int(oy + (dy + DIE / 2 - CBH / 2) * sc),
                                     int(okw * sc), int(CBH * sc))
        n = len(self._cube_btns)
        if not n:
            return
        total = n * CBW + (n - 1) * CBGAP
        cx = self._bar_x() + BARW + 3 * PW
        x0, y0 = cx - total / 2, TOP + H / 2 - CBH / 2
        font = theme.make_font(max(8, int(14 * sc)), 600)
        for i, b in enumerate(self._cube_btns):
            b.setFont(font)
            b.setGeometry(int(ox + (x0 + i * (CBW + CBGAP)) * sc), int(oy + y0 * sc), int(CBW * sc), int(CBH * sc))

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._place_buttons()

    def set_selection(self, selected: int | None, targets: set[int]) -> None:
        self.selected, self.targets = selected, targets
        self.update()

    def set_arrows(self, arrows: list[tuple[list, str, bool]]) -> None:
        self.arrows = arrows
        self.update()

    # ---- géométrie ----
    def _col_x(self, col: int) -> float:
        return BX + col * PW + (BARW if col >= 6 else 0)

    def _pt_geom(self, p: int) -> tuple[float, bool]:
        """(x gauche, en_haut)."""
        if p >= 13:
            return self._col_x(p - 13), True
        return self._col_x(12 - p), False

    def _bar_x(self) -> float:
        return BX + 6 * PW

    def _off_x(self) -> float:
        return BX + 12 * PW + BARW + 6

    def _anchor(self, p: int, frac: float = 0.28) -> QPointF:
        if p == 25:
            return QPointF(self._bar_x() + BARW / 2, TOP + H * 0.75)
        if p == 0:
            return QPointF(self._off_x() + OFFW / 2, TOP + H * 0.75)
        x, top = self._pt_geom(p)
        y = TOP + H * frac if top else TOP + H * (1 - frac)
        return QPointF(x + PW / 2, y)

    def _hit(self, x: float, y: float) -> int | None:
        if x >= self._off_x() and x <= self._off_x() + OFFW:
            return 0
        if self._bar_x() <= x <= self._bar_x() + BARW:
            return 25
        for p in range(1, 25):
            px, top = self._pt_geom(p)
            if px <= x <= px + PW and ((y < TOP + H / 2) == top) and TOP <= y <= TOP + H:
                return p
        return None

    def _scale(self) -> tuple[float, float, float]:
        sc = min(self.width() / self.LW, self.height() / self.LH)
        return sc, (self.width() - self.LW * sc) / 2, (self.height() - self.LH * sc) / 2

    def mousePressEvent(self, e) -> None:  # noqa: N802
        sc, ox, oy = self._scale()
        lx, ly = (e.position().x() - ox) / sc, (e.position().y() - oy) / sc
        dx, dy = self._dice_origin()
        if self.dice and dx - 6 <= lx <= dx + 2 * DIE + DGAP + 6 and dy - 6 <= ly <= dy + DIE + 6:
            self.diceClicked.emit()
            return
        p = self._hit((e.position().x() - ox) / sc, (e.position().y() - oy) / sc)
        if p is not None:
            self.pointClicked.emit(p)

    # ---- dessin ----
    def paintEvent(self, _e) -> None:  # noqa: N802
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = theme.current()
        qp.fillRect(self.rect(), Qt.GlobalColor.transparent)
        sc, ox, oy = self._scale()
        qp.translate(ox, oy)
        qp.scale(sc, sc)
        black, white = QColor(pal.board_ink), QColor(pal.board_paper)
        qp.setPen(QPen(black, 2))
        right = self._off_x() + OFFW
        qp.drawRect(QRectF(BX, TOP, right - BX, H))
        qp.drawRect(QRectF(self._bar_x(), TOP, BARW, H))
        qp.setFont(QFont("sans", 8))
        for p in range(1, 25):
            x, top = self._pt_geom(p)
            poly = QPolygonF()
            if top:
                poly << QPointF(x, TOP) << QPointF(x + PW, TOP) << QPointF(x + PW / 2, TOP + H * 0.42)
            else:
                poly << QPointF(x, TOP + H) << QPointF(x + PW, TOP + H) << QPointF(x + PW / 2, TOP + H * 0.58)
            qp.setPen(QPen(black, 1))
            qp.setBrush(QBrush(QColor(pal.board_alt) if p % 2 else white))
            qp.drawPolygon(poly)
            if p in self.targets or p == self.selected:
                qp.setPen(QPen(black, 4 if p == self.selected else 2, Qt.PenStyle.SolidLine if p == self.selected else Qt.PenStyle.DashLine))
                qp.setBrush(Qt.BrushStyle.NoBrush)
                qp.drawPolygon(poly)
            qp.setPen(black)
            qp.drawText(QRectF(x, TOP - 18 if top else TOP + H + 2, PW, 16), Qt.AlignmentFlag.AlignCenter, str(p))
        if p_ := self.pos:
            for p in range(1, 25):
                self._stack(qp, p, p_.mine[p - 1], True)
                self._stack(qp, p, p_.opp[24 - p], False)
            self._bar_stack(qp, p_.mine[24], True)
            self._bar_stack(qp, p_.opp[24], False)
            self._off(qp, p_)
        if self.selected == 25 or 0 in self.targets:
            qp.setPen(QPen(black, 3, Qt.PenStyle.DashLine))
            qp.setBrush(Qt.BrushStyle.NoBrush)
            if self.selected == 25:
                qp.drawRect(QRectF(self._bar_x(), TOP + H / 2, BARW, H / 2))
            if 0 in self.targets:
                qp.drawRect(QRectF(self._off_x(), TOP + H / 2, OFFW, H / 2))
        self._cube(qp)
        self._dice(qp)
        self._prompt(qp)
        if self.pos is not None:
            for i, (steps, color, dashed) in enumerate(self.arrows):
                self._draw_play(qp, steps, color, dashed, (0, 8, -8)[i % 3])

    def _stack(self, qp: QPainter, p: int, n: int, mine: bool) -> None:
        if n <= 0:
            return
        x, top = self._pt_geom(p)
        shown = min(n, 5)
        for i in range(shown):
            cy = (TOP + CK / 2 + 2 + i * CK) if top else (TOP + H - CK / 2 - 2 - i * CK)
            self._checker(qp, x + PW / 2, cy, mine, str(n) if (i == shown - 1 and n > 5) else None)

    def _bar_stack(self, qp: QPainter, n: int, mine: bool) -> None:
        for i in range(min(n, 4)):
            cy = TOP + H / 2 + CK / 2 + 4 + i * CK if mine else TOP + H / 2 - CK / 2 - 4 - i * CK
            self._checker(qp, self._bar_x() + BARW / 2, cy, mine, str(n) if (i == min(n, 4) - 1 and n > 4) else None)

    def _off(self, qp: QPainter, pos: Position) -> None:
        qp.setPen(QPen(QColor(theme.current().board_ink), 1))
        qp.setFont(QFont("sans", 10))
        qp.drawText(QRectF(self._off_x(), TOP + H * 0.55, OFFW, 20), Qt.AlignmentFlag.AlignCenter, "Sortis")
        qp.drawText(QRectF(self._off_x(), TOP + H * 0.62, OFFW, 28), Qt.AlignmentFlag.AlignCenter, f"{pos.off_mine()} noirs")
        qp.drawText(QRectF(self._off_x(), TOP + H * 0.30, OFFW, 28), Qt.AlignmentFlag.AlignCenter, f"{pos.off_opp()} blancs")
        if self.show_pips:
            qp.setFont(QFont("sans", 10, QFont.Weight.Bold))
            qp.drawText(QRectF(self._off_x(), TOP + H * 0.12, OFFW, 36), Qt.AlignmentFlag.AlignCenter, f"Pips\n{pos.pips_opp()}")
            qp.drawText(QRectF(self._off_x(), TOP + H * 0.78, OFFW, 36), Qt.AlignmentFlag.AlignCenter, f"Pips\n{pos.pips_mine()}")

    def _checker(self, qp: QPainter, cx: float, cy: float, mine: bool, label: str | None) -> None:
        qp.setPen(QPen(QColor(theme.current().board_ink if not mine or theme.current().is_dark else "#000000"), 2))
        qp.setBrush(QBrush(QColor("#1D1D1F") if mine else QColor("#FFFFFF")))
        qp.drawEllipse(QPointF(cx, cy), CK / 2 - 1, CK / 2 - 1)
        if label:
            qp.setPen(QColor("#FFFFFF") if mine else QColor("#1D1D1F"))
            qp.setFont(QFont("sans", 11, QFont.Weight.Bold))
            qp.drawText(QRectF(cx - CK / 2, cy - CK / 2, CK, CK), Qt.AlignmentFlag.AlignCenter, label)

    def _cube(self, qp: QPainter) -> None:
        y = {None: TOP + H / 2 - 22, "me": TOP + H - 56, "opp": TOP + 8}[self.cube_owner]
        r = QRectF(6, y, 44, 44)
        pal = theme.current()
        qp.setPen(QPen(QColor(pal.board_ink), 3))
        qp.setBrush(QBrush(QColor(pal.board_paper)))
        qp.drawRoundedRect(r, 8, 8)
        qp.setPen(QColor(pal.board_ink))
        qp.setFont(QFont("sans", 16, QFont.Weight.Bold))
        qp.drawText(r, Qt.AlignmentFlag.AlignCenter, str(64 if self.cube_value == 1 and self.cube_owner is None else self.cube_value))
        if self.offered:
            qp.setFont(QFont("sans", 9, QFont.Weight.Bold))
            qp.drawText(QRectF(0, TOP + H / 2 + 26, CUBEW, 40), Qt.AlignmentFlag.AlignCenter, f"double\n-> {self.offered}")

    _PIPS = {1: [(1, 1)], 2: [(0, 0), (2, 2)], 3: [(0, 0), (1, 1), (2, 2)],
             4: [(0, 0), (2, 0), (0, 2), (2, 2)], 5: [(0, 0), (2, 0), (1, 1), (0, 2), (2, 2)],
             6: [(0, 0), (2, 0), (0, 1), (2, 1), (0, 2), (2, 2)]}

    def _prompt(self, qp: QPainter) -> None:
        if not self.prompt:
            return
        w = 6 * PW - 24
        qp.setPen(QColor(theme.current().board_ink))
        qp.setFont(QFont("sans", 17, QFont.Weight.Bold))
        qp.drawText(QRectF(BX + 12, TOP + H / 2 - 70, w, 140),
                    int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap), self.prompt)

    def _dice_origin(self) -> tuple[float, float]:
        """Coin haut-gauche des dés : centre de la moitié droite du plateau (bande entre les pointes)."""
        cx = self._bar_x() + BARW + 3 * PW
        return cx - (2 * DIE + DGAP) / 2, TOP + H / 2 - DIE / 2

    def _dice(self, qp: QPainter) -> None:
        if not self.dice:
            return
        x0, y = self._dice_origin()
        for i, v in enumerate(self.dice):
            self._die(qp, x0 + i * (DIE + DGAP), y, v, i in self._greyed())
        if self.dice[0] == self.dice[1]:
            qp.setPen(QColor(theme.current().board_ink))
            qp.setFont(QFont("sans", 9, QFont.Weight.Bold))
            qp.drawText(QRectF(x0, y + DIE + 1, 2 * DIE + DGAP, 16), Qt.AlignmentFlag.AlignCenter, "double : x4")

    def _greyed(self) -> set[int]:
        used = list(getattr(self, "used_dice", ()))
        if not self.dice:
            return set()
        if self.dice[0] == self.dice[1]:
            return {i for i in range(2) if len(used) >= 2 * (i + 1)}
        g = set()
        for i, v in enumerate(self.dice):
            if v in used:
                used.remove(v)
                g.add(i)
        return g

    def _die(self, qp: QPainter, x: float, y: float, v: int, grey: bool = False) -> None:
        ink = "#D0D0D0" if grey else "#FFFFFF"
        qp.setPen(QPen(QColor("#8A8A8A" if grey else "#000000"), 2))
        qp.setBrush(QBrush(QColor("#8A8A8A" if grey else "#1D1D1F")))
        qp.drawRoundedRect(QRectF(x, y, DIE, DIE), 10, 10)
        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QBrush(QColor(ink)))
        m, step, r = DIE * 0.2, DIE * 0.3, DIE * 0.09
        for cx, cy in self._PIPS[v]:
            qp.drawEllipse(QPointF(x + m + cx * step, y + m + cy * step), r, r)

    def _slot(self, p: int, k: int) -> QPointF:
        """Centre du k-ième pion (0 = bord du plateau) d'une pile de ``p`` (25 = barre, 0 = sortie)."""
        k = min(k, 4)
        if p == 25:
            return QPointF(self._bar_x() + BARW / 2, TOP + H / 2 + CK / 2 + 4 + min(k, 3) * CK)
        if p == 0:
            return QPointF(self._off_x() + OFFW / 2, TOP + H * 0.80 + k * 8)
        x, top = self._pt_geom(p)
        cy = (TOP + CK / 2 + 2 + k * CK) if top else (TOP + H - CK / 2 - 2 - k * CK)
        return QPointF(x + PW / 2, cy)

    def _draw_play(self, qp: QPainter, steps: list, color: str, dashed: bool, lateral: float) -> None:
        """Flèches du pion de départ (haut de pile) vers l'emplacement d'arrivée (haut de pile)."""
        import math
        cnt = {i: self.pos.mine[i - 1] for i in range(1, 25)}
        cnt[25] = self.pos.mine[24]
        cnt[0] = 0
        for s, d in steps:
            src_k = max(cnt.get(s, 1) - 1, 0)
            a = self._slot(s, src_k)
            b = self._slot(d, cnt.get(d, 0))
            cnt[s] = cnt.get(s, 1) - 1
            cnt[d] = cnt.get(d, 0) + 1
            # jamais horizontal : pente minimale, l'arrivée est décalée vers le centre du plateau
            mid = TOP + H / 2
            need = max(CK * 1.4, abs(b.x() - a.x()) * 0.45)
            if abs(b.y() - a.y()) < need:
                toward_mid = 1 if b.y() < mid else -1
                b = QPointF(b.x(), a.y() + toward_mid * need)
            dx, dy = b.x() - a.x(), b.y() - a.y()
            n = math.hypot(dx, dy) or 1.0
            ux, uy = dx / n, dy / n
            off = QPointF(-uy * lateral, ux * lateral)
            a, b = a + off, b + off
            # démarre/finit au bord des pions
            a = QPointF(a.x() + ux * CK * 0.35, a.y() + uy * CK * 0.35)
            b = QPointF(b.x() - ux * CK * 0.35, b.y() - uy * CK * 0.35)
            self._arrow(qp, a, b, color, dashed)

    def _arrow(self, qp: QPainter, a: QPointF, b: QPointF, color: str, dashed: bool) -> None:
        import math
        c = QColor(color)
        qp.setPen(QPen(c, 5, Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        qp.drawLine(a, b)
        ang = math.atan2(b.y() - a.y(), b.x() - a.x())
        L = 20
        p1 = QPointF(b.x() - L * math.cos(ang - 0.4), b.y() - L * math.sin(ang - 0.4))
        p2 = QPointF(b.x() - L * math.cos(ang + 0.4), b.y() - L * math.sin(ang + 0.4))
        qp.setPen(QPen(c, 1))
        qp.setBrush(QBrush(c))
        qp.drawPolygon(QPolygonF([b, p1, p2]))
