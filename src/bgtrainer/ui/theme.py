"""Thème macOS (Sonoma/Ventura) : palettes clair/sombre, QSS, polices, ombres, animations, vibrancy.

Usage :
    style = AppleStyleSheet(app)
    style.apply_system_theme()      # suit le thème macOS et le met à jour en direct
    # ou style.apply_light_theme() / style.apply_dark_theme()

Aucune logique métier ici : uniquement de l'apparence.
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass, fields
from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QObject, QPropertyAnimation, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QFontDatabase, QGuiApplication, QPainter, QPalette, QPen, QPixmap)
from PyQt6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QWidget

QSS_PATH = Path(__file__).with_name("macos_style.qss")

# Ordre de préférence : SF si installée, sinon équivalents proches.
FONT_CANDIDATES = (".AppleSystemUIFont", "SF Pro Text", "SF Pro Display", "San Francisco", "Helvetica Neue",
                   "Inter", "Segoe UI", "Cantarell", "Noto Sans", "DejaVu Sans")


@dataclass(frozen=True)
class Palette:
    name: str
    window_bg: str
    content_bg: str
    sidebar_bg: str
    popup_bg: str
    input_bg: str
    list_bg: str
    text: str
    text_secondary: str
    text_disabled: str
    accent: str            # bordures, focus, sélection (#007AFF / #0A84FF)
    accent_text: str       # texte bleu sur fond clair/sombre (contraste >= 4.5)
    accent_strong: str     # fond des boutons primaires (texte blanc, contraste >= 4.5)
    accent_hover: str
    destructive: str
    separator: str
    row_separator: str
    border: str
    border_strong: str
    hover: str
    pressed: str
    list_hover: str
    selection: str
    track: str
    scroll: str
    scroll_hover: str
    # couleurs sémantiques (texte blanc dessus, contraste >= 4.5)
    success: str
    error: str
    # plateau
    board_ink: str
    board_paper: str
    board_alt: str
    is_dark: bool = False


LIGHT = Palette(
    name="light", window_bg="#F5F5F7", content_bg="#FFFFFF", sidebar_bg="rgba(240,240,245,0.8)",
    popup_bg="rgba(255,255,255,0.92)", input_bg="#FFFFFF", list_bg="#FFFFFF",
    text="#1D1D1F", text_secondary="#6E6E73", text_disabled="rgba(29,29,31,0.4)",
    accent="#007AFF", accent_text="#0062CC", accent_strong="#0066D6", accent_hover="#0058B8",
    destructive="#D70015", separator="rgba(0,0,0,0.1)", row_separator="rgba(0,0,0,0.08)",
    border="rgba(0,0,0,0.15)", border_strong="rgba(0,0,0,0.3)", hover="rgba(0,0,0,0.05)", pressed="rgba(0,0,0,0.1)",
    list_hover="rgba(0,0,0,0.04)", selection="rgba(0,122,255,0.15)", track="rgba(0,0,0,0.12)",
    scroll="rgba(0,0,0,0.25)", scroll_hover="rgba(0,0,0,0.4)",
    success="#248A3D", error="#D70015",
    board_ink="#1D1D1F", board_paper="#FFFFFF", board_alt="#D2D2D7",
)

DARK = Palette(
    name="dark", window_bg="#1E1E1E", content_bg="#1E1E1E", sidebar_bg="rgba(44,44,46,0.8)",
    popup_bg="rgba(44,44,46,0.92)", input_bg="#2C2C2E", list_bg="#2C2C2E",
    text="#F5F5F7", text_secondary="#98989D", text_disabled="rgba(245,245,247,0.4)",
    accent="#0A84FF", accent_text="#64AEFF", accent_strong="#0070E0", accent_hover="#1A8CFF",
    destructive="#FF6961", separator="rgba(255,255,255,0.1)", row_separator="rgba(255,255,255,0.08)",
    border="rgba(255,255,255,0.15)", border_strong="rgba(255,255,255,0.35)", hover="rgba(255,255,255,0.1)",
    pressed="rgba(255,255,255,0.16)", list_hover="rgba(255,255,255,0.06)", selection="rgba(10,132,255,0.3)",
    track="rgba(255,255,255,0.16)", scroll="rgba(255,255,255,0.3)", scroll_hover="rgba(255,255,255,0.5)",
    success="#248A3D", error="#D70015",
    board_ink="#F5F5F7", board_paper="#2C2C2E", board_alt="#48484A", is_dark=True,
)

_current: Palette = LIGHT


def current() -> Palette:
    """Palette active (lue par le plateau QPainter à chaque repaint)."""
    return _current


# ---------- polices ----------
def system_font_family() -> str:
    have = set(QFontDatabase.families())
    for f in FONT_CANDIDATES:
        if f in have:
            return f
    return QGuiApplication.font().family()


def make_font(px: int = 13, weight: int = 400, spacing: float = 0.0) -> QFont:
    f = QFont(system_font_family())
    f.setPixelSize(px)
    f.setWeight(QFont.Weight(weight))
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


def set_role(w: QWidget, role: str) -> None:
    """Rôle visuel (primary, destructive, secondary, title, headline, dice...) lu par le QSS.
    Les rôles « titre » reçoivent aussi le letter-spacing -0.2px (non exprimable en QSS)."""
    w.setProperty("role", role)
    if role in ("title", "headline", "dice"):
        f = w.font()
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -0.2)
        w.setFont(f)
    st = w.style()
    if st is not None and w.isVisible():
        st.unpolish(w)
        st.polish(w)


# ---------- ombres & animations ----------
def add_shadow(w: QWidget, blur: int = 30, dy: int = 10, alpha: int = 50) -> QGraphicsDropShadowEffect:
    """Ombre douce (équivalent 0 10px 30px rgba(0,0,0,0.2)) pour éléments flottants."""
    fx = QGraphicsDropShadowEffect(w)
    fx.setBlurRadius(blur)
    fx.setOffset(0, dy)
    fx.setColor(QColor(0, 0, 0, alpha))
    w.setGraphicsEffect(fx)
    return fx


def fade_in(win: QWidget, ms: int = 220) -> QPropertyAnimation:
    """Ouverture : fade-in (opacité 0 -> 1) + léger zoom 0.95 -> 1.0 (la géométrie finale est conservée)."""
    final = win.geometry()
    w0, h0 = int(final.width() * 0.95), int(final.height() * 0.95)
    start = final.adjusted((final.width() - w0) // 2, (final.height() - h0) // 2,
                           -((final.width() - w0) // 2), -((final.height() - h0) // 2))
    win.setWindowOpacity(0.0)
    fade = QPropertyAnimation(win, b"windowOpacity", win)
    fade.setDuration(ms)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.setEasingCurve(QEasingCurve.Type.OutCubic)
    grow = QPropertyAnimation(win, b"geometry", win)
    grow.setDuration(ms)
    grow.setStartValue(start)
    grow.setEndValue(final)
    grow.setEasingCurve(QEasingCurve.Type.OutCubic)
    fade.finished.connect(lambda: win.setWindowOpacity(1.0))
    win._fx_anims = (fade, grow)  # références conservées
    fade.start()
    grow.start()
    return fade


# ---------- vibrancy native macOS (optionnel, PyObjC) ----------
def enable_native_vibrancy(win: QWidget, material: str = "sidebar") -> bool:
    """Insère un NSVisualEffectView derrière la fenêtre Qt. Retourne False hors macOS / sans PyObjC
    (les fonds rgba du QSS servent alors de simulation)."""
    if sys.platform != "darwin":
        return False
    try:
        import objc  # type: ignore
        from AppKit import (NSVisualEffectBlendingModeBehindWindow, NSVisualEffectMaterialSidebar,
                            NSVisualEffectMaterialWindowBackground, NSVisualEffectMaterialContentBackground,
                            NSVisualEffectStateActive, NSVisualEffectView, NSViewHeightSizable, NSViewWidthSizable,
                            NSWindowBelow)
        mats = {"sidebar": NSVisualEffectMaterialSidebar, "windowBackground": NSVisualEffectMaterialWindowBackground,
                "contentBackground": NSVisualEffectMaterialContentBackground}
        win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        nsview = objc.objc_object(c_void_p=int(win.winId()))
        effect = NSVisualEffectView.alloc().initWithFrame_(nsview.bounds())
        effect.setMaterial_(mats.get(material, NSVisualEffectMaterialSidebar))
        effect.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(NSVisualEffectStateActive)
        effect.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        nsview.addSubview_positioned_relativeTo_(effect, NSWindowBelow, None)
        win._vibrancy_view = effect
        return True
    except Exception:  # noqa: BLE001 - PyObjC absent ou API différente : on retombe sur la simulation
        win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        return False


# ---------- icônes générées (chevrons, coche) ----------
def _draw_icon(path: Path, kind: str, color: str, size: int = 20) -> None:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    s = size
    pts = {"down": [(0.28, 0.4), (0.5, 0.62), (0.72, 0.4)],
           "up": [(0.28, 0.6), (0.5, 0.38), (0.72, 0.6)],
           "check": [(0.24, 0.52), (0.42, 0.7), (0.76, 0.3)]}[kind]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        p.drawLine(QPointF(x1 * s, y1 * s), QPointF(x2 * s, y2 * s))
    p.end()
    pm.save(str(path), "PNG")


class AppleStyleSheet(QObject):
    """Applique le thème macOS à toute l'application (QSS + QPalette + police)."""

    themeChanged = pyqtSignal(str)

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self.app = app
        self._icons = Path(tempfile.mkdtemp(prefix="bgtrainer-icons-"))
        self._auto = False
        self._template = QSS_PATH.read_text(encoding="utf-8")
        app.setStyle("Fusion")  # rendu identique sur toutes les plateformes ; le QSS fait le reste
        app.setFont(make_font(13, 400))

    # --- API publique ---
    def apply_light_theme(self) -> None:
        self._auto = False
        self._apply(LIGHT)

    def apply_dark_theme(self) -> None:
        self._auto = False
        self._apply(DARK)

    def apply_system_theme(self) -> None:
        """Suit le thème macOS et bascule automatiquement s'il change."""
        self._auto = True
        hints = QGuiApplication.styleHints()
        try:
            hints.colorSchemeChanged.disconnect(self._on_scheme)
        except TypeError:
            pass
        hints.colorSchemeChanged.connect(self._on_scheme)
        self._on_scheme()

    @staticmethod
    def system_is_dark() -> bool:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark

    # --- interne ---
    def _on_scheme(self, *_) -> None:
        if self._auto:
            self._apply(DARK if self.system_is_dark() else LIGHT)

    def _qss(self, p: Palette) -> str:
        icon_color = p.text_secondary if not p.is_dark else "#98989D"
        for kind, name, col in (("down", "chevron_down", icon_color), ("up", "chevron_up", icon_color),
                                ("check", "check", "#FFFFFF")):
            _draw_icon(self._icons / f"{p.name}_{name}.png", kind, col)
        values = {f.name: getattr(p, f.name) for f in fields(p) if isinstance(getattr(p, f.name), str)}
        values["icon_chevron_down"] = (self._icons / f"{p.name}_chevron_down.png").as_posix()
        values["icon_chevron_up"] = (self._icons / f"{p.name}_chevron_up.png").as_posix()
        values["icon_check"] = (self._icons / f"{p.name}_check.png").as_posix()
        out = self._template
        for k, v in values.items():
            out = out.replace(f"@{k}@", v)
        return out

    def _qpalette(self, p: Palette) -> QPalette:
        pal = QPalette()
        text, base = QColor(p.text), QColor(p.input_bg)
        for role, col in ((QPalette.ColorRole.Window, QColor(p.window_bg)), (QPalette.ColorRole.WindowText, text),
                          (QPalette.ColorRole.Base, base), (QPalette.ColorRole.AlternateBase, base),
                          (QPalette.ColorRole.Text, text), (QPalette.ColorRole.Button, QColor(p.window_bg)),
                          (QPalette.ColorRole.ButtonText, text), (QPalette.ColorRole.ToolTipBase, base),
                          (QPalette.ColorRole.ToolTipText, text), (QPalette.ColorRole.Highlight, QColor(p.accent)),
                          (QPalette.ColorRole.HighlightedText, QColor("#FFFFFF")),
                          (QPalette.ColorRole.PlaceholderText, QColor(p.text_secondary))):
            pal.setColor(role, col)
        return pal

    def _apply(self, p: Palette) -> None:
        global _current
        _current = p
        self.app.setPalette(self._qpalette(p))
        self.app.setStyleSheet(self._qss(p))
        for w in self.app.topLevelWidgets():
            w.update()
            for child in w.findChildren(QWidget):
                child.update()
        self.themeChanged.emit(p.name)
