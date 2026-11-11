"""Fenêtre principale PyQt6 (style macOS, voir theme.py). Passe uniquement par TrainerService."""
from __future__ import annotations

import re
import threading
from pathlib import Path

from PyQt6.QtCore import QElapsedTimer, QFileSystemWatcher, QRectF, QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPalette
from PyQt6.QtWidgets import (QAbstractItemView, QStyledItemDelegate, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                             QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMainWindow, QMessageBox, QStatusBar, QPlainTextEdit, QTextBrowser, QProgressBar, QPushButton, QSpinBox, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from ..config.settings import ConfigError, Settings, default_config_path, load_settings, save_settings
from ..domain.board import Position, apply_step
from ..analysis.coach import NEAR_GOOD, user_loss
from ..analysis.format import analysis_text, move_text
from ..engine.gnubg_adapter import EngineError
from ..services.api import TrainerService
from . import theme
from .board_widget import BoardWidget

KIND = {"move": "Coup", "cube": "Cube"}
CLASS_LABEL = {"doubtful": "Douteux", "bad": "Mauvais", "very bad": "Très mauvais"}
STATE = {"new": "nouveau", "in_progress": "raté (à refaire)", "correct": "réussi", "skipped": "passé"}
GREEN, RED, GRAY = "#248A3D", "#D70015", "#8E8E93"  # succès / erreur / neutre (texte blanc >= 4.5:1)
ORANGE = "#C75F00"  # « presque bon » (texte blanc lisible)
OUTCOME = {"first_try": "réussi du 1er coup", "retry": "réussi après erreur", "failed": "échec",
           "skipped": "passé", "unanswered": "non traité"}
OUTCOME_ICON = {"first_try": "OK", "retry": "OK~", "failed": "KO", "skipped": "--", "unanswered": "  "}
CUBE_LABEL = {"double": "Doubler", "no_double": "Ne pas doubler", "take": "Prendre", "pass": "Passer"}


class ExerciseDelegate(QStyledItemDelegate):
    """Garde la couleur de texte de l'item (blanc sur vert/rouge) même sélectionné ou survolé."""

    def paint(self, painter, option, index) -> None:
        bg = index.data(Qt.ItemDataRole.BackgroundRole)
        if bg is not None and bg.style() != Qt.BrushStyle.NoBrush:
            painter.save()
            painter.setRenderHint(painter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(QRectF(option.rect).adjusted(1, 1, -1, -1), 6, 6)
            painter.restore()
        super().paint(painter, option, index)

    def initStyleOption(self, option, index) -> None:  # noqa: N802
        super().initStyleOption(option, index)
        fg = index.data(Qt.ItemDataRole.ForegroundRole)
        if fg is not None and index.data(Qt.ItemDataRole.BackgroundRole) is not None:
            brush = QBrush(fg) if not isinstance(fg, QBrush) else fg
            for grp in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive, QPalette.ColorGroup.Disabled):
                for role in (QPalette.ColorRole.Text, QPalette.ColorRole.HighlightedText, QPalette.ColorRole.WindowText):
                    option.palette.setBrush(grp, role, brush)


class ScanWorker(QThread):
    progress = pyqtSignal(str, int, int)
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, svc: TrainerService, paths: list[Path] | None, retry_failed: bool = False) -> None:
        super().__init__()
        self.svc, self.paths, self.retry_failed = svc, paths, retry_failed
        self.cancel = threading.Event()

    def run(self) -> None:
        try:
            r = self.svc.scan_sources(self.paths, analyze=True, progress=lambda a, b, c: self.progress.emit(a, b, c),
                                      cancel=self.cancel, retry_failed=self.retry_failed)
            self.finished_ok.emit(r)
        except (EngineError, ConfigError) as e:
            self.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"{type(e).__name__}: {e}")


def _bar(pct: float, width: int = 20) -> str:
    n = round(width * pct / 100)
    return "#" * n + "." * (width - n)


class SummaryDialog(QDialog):
    """Résumé de session : un tableau (total / coups / cube) avec réussites au 1er coup, échecs et pourcentages."""

    def __init__(self, sm: dict, prev: dict | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Résultat de la session")
        lay = QVBoxLayout(self)
        t = QLabel(f"Session terminée : {sm['score_pct']:.0f} % réussis du premier coup")
        theme.set_role(t, "title")
        lay.addWidget(t)
        zero = {"total": 0, "first_try": 0, "failed": 0, "answered": 0}
        kinds = sm["by_kind"]
        rows = [("Total", {k: sum(g[k] for g in kinds.values()) for k in zero}),
                ("Coups", kinds.get("move", zero)), ("Cube", kinds.get("cube", zero))]
        cols = ["Type", "Effectués", "Réussis 1er coup", "%", "Échecs", "%"]
        tbl = QTableWidget(len(rows), len(cols))
        tbl.setHorizontalHeaderLabels(cols)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        pct = lambda n, d: f"{100 * n / d:.0f} %" if d else "-"
        for r, (name, g) in enumerate(rows):
            n = g["answered"]
            vals = [name, n, g["first_try"], pct(g["first_try"], n), g["failed"], pct(g["failed"], n)]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter if c else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if r == 0:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                if c in (2, 3) and n:
                    it.setForeground(QBrush(QColor(GREEN)))
                elif c in (4, 5) and g["failed"]:
                    it.setForeground(QBrush(QColor(RED)))
                tbl.setItem(r, c, it)
        tf = tbl.font()
        tf.setPixelSize(20)
        tbl.setFont(tf)
        tbl.horizontalHeader().setFont(tf)
        tbl.setStyleSheet("QHeaderView::section { font-size: 18px; font-weight: 600; }")
        tbl.verticalHeader().setDefaultSectionSize(46)
        tbl.horizontalHeader().setFixedHeight(46)
        tbl.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tbl.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tbl.resizeColumnsToContents()
        for c in range(len(cols)):
            tbl.setColumnWidth(c, tbl.columnWidth(c) + 32)
        w = sum(tbl.columnWidth(c) for c in range(len(cols))) + 2 * tbl.frameWidth() + 2
        h = tbl.horizontalHeader().height() + sum(tbl.rowHeight(i) for i in range(len(rows))) + 2 * tbl.frameWidth() + 2
        tbl.setFixedSize(w, h)
        lay.addWidget(tbl)
        lay.addWidget(_vs_match_table_widget(sm, tf, pct))
        notes = ["Pourcentages calculés sur les exercices effectués."]
        extra = [f"{OUTCOME[k]} : {sm[k]}" for k in ("retry", "skipped", "unanswered") if sm[k]]
        if extra:
            notes.append("Hors tableau : " + ", ".join(extra) + ".")
        if prev:
            d = sm["score_pct"] - prev["score_pct"]
            notes.append(f"Session précédente : {prev['score_pct']:.0f} %  ({'+' if d >= 0 else ''}{d:.0f} points)")
        nl = QLabel("\n".join(notes))
        nl.setWordWrap(True)
        nf = nl.font()
        nf.setPixelSize(16)
        nl.setFont(nf)
        lay.addWidget(nl)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)
        # ne jamais dépasser l'écran
        scr = (parent.screen() if parent else QApplication.primaryScreen()).availableGeometry()
        self.setMaximumSize(int(scr.width() * 0.9), int(scr.height() * 0.9))
        self.adjustSize()
        self.resize(min(self.width(), self.maximumWidth()), min(self.height(), self.maximumHeight()))


def _vs_match_table_widget(sm: dict, tf, pct) -> QWidget:
    """Votre réponse comparée au coup joué en match (même si ce n'est pas le meilleur coup)."""
    box = QWidget()
    bl = QVBoxLayout(box)
    bl.setContentsMargins(0, 8, 0, 0)
    title = QLabel("Comparaison avec le coup joué en match")
    theme.set_role(title, "headline")
    bl.addWidget(title)
    vs = sm.get("vs_match", {})
    z = {"better": 0, "same": 0, "worse": 0, "unknown": 0, "gain": 0.0, "gain_n": 0}
    parts = {"move": vs.get("move", z), "cube": vs.get("cube", z)}
    tot = {k: sum(g[k] for g in parts.values()) for k in z}
    rows = [("Total", tot), ("Coups", parts["move"]), ("Cube", parts["cube"])]
    cols = ["Type", "Mieux", "Identique", "Moins bien", "Amélioration", "Gain moyen"]
    t = QTableWidget(len(rows), len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    t.setFont(tf)
    t.setStyleSheet("QHeaderView::section { font-size: 17px; font-weight: 600; }")
    t.verticalHeader().setDefaultSectionSize(38)
    t.horizontalHeader().setFixedHeight(38)
    for r, (name, g) in enumerate(rows):
        n = g["better"] + g["same"] + g["worse"]
        gain = f"{g['gain'] / g['gain_n']:+.3f}" if g["gain_n"] else "-"
        vals = [name, g["better"], g["same"], g["worse"], pct(g["better"], n), gain]
        for c, v in enumerate(vals):
            it = QTableWidgetItem(str(v))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter if c else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            f = it.font()
            f.setBold(r == 0)
            it.setFont(f)
            if c in (1, 4) and g["better"]:
                it.setForeground(QBrush(QColor(GREEN)))
            elif c == 3 and g["worse"]:
                it.setForeground(QBrush(QColor(RED)))
            t.setItem(r, c, it)
    t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    t.resizeColumnsToContents()
    for c in range(len(cols)):
        t.setColumnWidth(c, t.columnWidth(c) + 32)
    t.setFixedSize(sum(t.columnWidth(c) for c in range(len(cols))) + 2 * t.frameWidth() + 2,
                   t.horizontalHeader().height() + sum(t.rowHeight(i) for i in range(len(rows))) + 2 * t.frameWidth() + 2)
    bl.addWidget(t)
    note = QLabel("Mieux / Moins bien : votre réponse comparée au coup joué en match (même si ce n'est pas le meilleur). "
                  "Amélioration = part de « Mieux » ; gain moyen = équité gagnée par coup.")
    note.setWordWrap(True)
    note.setMaximumWidth(t.width())
    bl.addWidget(note)
    return box


class HistoryDialog(QDialog):
    def __init__(self, sessions: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Historique des sessions")
        self.resize(900, 420)
        lay = QVBoxLayout(self)
        cols = ["Date", "Statut", "Exos", "Traités", "1er coup", "Après erreur", "Échecs", "Passés", "Score", "Progression"]
        t = QTableWidget(len(sessions), len(cols))
        t.setHorizontalHeaderLabels(cols)
        st = {"finished": "terminée", "running": "en cours", "abandoned": "interrompue"}
        for r, sm in enumerate(reversed(sessions)):
            vals = [sm["started"].replace("T", " ")[:16], st[sm["status"]], sm["total"], sm["answered"], sm["first_try"],
                    sm["retry"], sm["failed"], sm["skipped"], f"{sm['score_pct']:.0f} %", _bar(sm["score_pct"])]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                t.setItem(r, c, it)
        t.resizeColumnsToContents()
        lay.addWidget(t)
        if not sessions:
            lay.addWidget(QLabel("Aucune session enregistrée."))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class SettingsDialog(QDialog):
    def __init__(self, s: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Paramètres")
        self.s = s
        f = QFormLayout(self)
        self.mat = QLineEdit(s.mat_directory)
        b = QPushButton("…")
        b.clicked.connect(self._pick)
        row = QHBoxLayout()
        row.addWidget(self.mat)
        row.addWidget(b)
        f.addRow("Répertoire .mat", row)
        self.sub = QCheckBox("Inclure les sous-répertoires")
        self.sub.setChecked(s.include_subdirectories)
        f.addRow(self.sub)
        self.db = QLineEdit(s.database_path)
        f.addRow("Base SQLite", self.db)
        self.exe = QLineEdit(s.engine_executable)
        f.addRow("Exécutable gnubg", self.exe)
        self.plies = QSpinBox()
        self.plies.setRange(0, 4)
        self.plies.setValue(s.engine_plies)
        f.addRow("Profondeur (plies)", self.plies)
        self.workers = QSpinBox()
        self.workers.setRange(1, 32)
        self.workers.setValue(s.engine_workers)
        f.addRow("Analyses en parallèle", self.workers)
        self.reveal = QCheckBox("Montrer la correction après une erreur")
        self.reveal.setChecked(s.reveal_correction_after_incorrect)
        f.addRow(self.reveal)
        self.reset_requested = False
        self.clear_sessions_requested = False
        self.keep_sessions = True
        grp_s = QGroupBox("Historique des sessions")
        sl = QVBoxLayout(grp_s)
        sl.addWidget(QLabel("Supprime toutes les sessions d'entraînement passées et leurs résultats.\n"
                            "Les exercices et leur état (réussi / raté) sont conservés. Une sauvegarde de la base est créée."))
        b_sess = QPushButton("Vider l'historique des sessions…")
        theme.set_role(b_sess, "destructive")
        b_sess.clicked.connect(self._clear_sessions)
        sl.addWidget(b_sess)
        f.addRow(grp_s)
        grp = QGroupBox("Réinitialisation")
        gl = QVBoxLayout(grp)
        gl.addWidget(QLabel("Vide la base (sources, matchs, analyses, exercices, progression) puis relance le scan.\n"
                            "Les fichiers .mat ne sont pas touchés. Une sauvegarde de la base est créée."))
        self.chk_keep = QCheckBox("Conserver l'historique des sessions d'entraînement")
        self.chk_keep.setChecked(True)
        gl.addWidget(self.chk_keep)
        b_reset = QPushButton("Vider la base et refaire le scan…")
        b_reset.clicked.connect(self._reset)
        gl.addWidget(b_reset)
        f.addRow(grp)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def _clear_sessions(self) -> None:
        if QMessageBox.question(self, "Vider l'historique",
                                "Toutes les sessions d'entraînement et leurs résultats seront supprimés "
                                "(la session en cours sera abandonnée). Continuer ?") != QMessageBox.StandardButton.Yes:
            return
        self.clear_sessions_requested = True
        self._ok()

    def _reset(self) -> None:
        if not self.mat.text().strip():
            QMessageBox.warning(self, "Réinitialisation", "Configurez d'abord le répertoire .mat : le scan doit pouvoir être relancé.")
            return
        if QMessageBox.question(self, "Vider la base",
                                "Toutes les analyses et exercices seront supprimés, puis le répertoire sera rescanné "
                                "(plusieurs dizaines de minutes à plusieurs heures selon le nombre de fichiers).\n\nContinuer ?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.reset_requested = True
        self.keep_sessions = self.chk_keep.isChecked()
        self._ok()

    def _pick(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Répertoire .mat", self.mat.text())
        if d:
            self.mat.setText(d)

    def _ok(self) -> None:
        s = self.s
        s.mat_directory, s.include_subdirectories = self.mat.text().strip(), self.sub.isChecked()
        s.database_path, s.engine_executable = self.db.text().strip(), self.exe.text().strip()
        s.engine_plies, s.engine_workers = self.plies.value(), self.workers.value()
        s.reveal_correction_after_incorrect = self.reveal.isChecked()
        try:
            save_settings(s)
        except ConfigError as e:
            self.reset_requested = False
            QMessageBox.warning(self, "Configuration invalide", str(e))
            return
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.setWindowTitle("Entraîneur de backgammon")
        self.settings = settings
        self.svc = TrainerService(settings)
        self.worker: ScanWorker | None = None
        self.single: str | None = None
        self.items: list[dict] = []
        self.ex: dict | None = None
        self.done: list[tuple[int, int, int]] = []
        self.start_pos: Position | None = None
        self.cur_pos: Position | None = None
        self.sel: int | None = None
        self.finished_ex = False
        self.session_id: int | None = None
        self._auto_session = False
        self._silent = False
        self._rescan = False
        self._players_before: list[str] | str | None = None  # sélection des joueurs avant « fichier unique »
        self.session_items: list[dict] = []
        self.outcomes: dict[int, str] = {}
        self._build()
        self.refresh_players()
        self.reload_list()
        QTimer.singleShot(500, self._startup_scan)

    # ---------- construction ----------
    def _build(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        root.setObjectName("content")
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.sidebar = QFrame()  # matériau « sidebar » (translucide)
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(300)
        left = QVBoxLayout(self.sidebar)
        left.setContentsMargins(16, 12, 16, 12)
        left.setSpacing(6)
        lay.addWidget(self.sidebar, 0)
        self.lbl_dir = QLabel()
        self.lbl_dir.setWordWrap(True)
        left.addWidget(self.lbl_dir)
        r = QHBoxLayout()
        self.btn_scan = QPushButton("Scanner le répertoire")
        self.btn_scan.clicked.connect(self.scan_dir)
        btn_set = QPushButton("Paramètres")
        btn_set.clicked.connect(self.open_settings)
        r.addWidget(self.btn_scan)
        r.addWidget(btn_set)
        left.addLayout(r)
        self.btn_rescan = QPushButton("Relancer le scan")
        self.btn_rescan.setToolTip("Reprend uniquement les fichiers pas encore analysés (nouveaux, interrompus ou en échec)")
        self.btn_rescan.clicked.connect(self.rescan_pending)
        left.addWidget(self.btn_rescan)
        r2 = QHBoxLayout()
        self.btn_single = QPushButton("Fichier unique…")
        self.btn_single.clicked.connect(self.pick_single)
        self.btn_exit_single = QPushButton("Quitter fichier unique")
        self.btn_exit_single.clicked.connect(self.exit_single)
        self.btn_exit_single.setVisible(False)
        r2.addWidget(self.btn_single)
        r2.addWidget(self.btn_exit_single)
        left.addLayout(r2)
        self.lbl_single = QLabel()
        self.lbl_single.setWordWrap(True)
        left.addWidget(self.lbl_single)
        self.chk_never = QCheckBox("Session : seulement les exercices jamais faits")
        self.chk_never.setChecked(True)
        self.chk_never.setToolTip("N'inclut que les exercices que vous n'avez encore jamais traités")
        self.chk_hard = QCheckBox("Session : seulement ceux où j'échoue (> 50 %)")
        self.chk_hard.setToolTip("N'inclut que les exercices déjà proposés où vous ne réussissez pas du 1er coup "
                                 "dans plus de 50 % des cas")
        self.chk_never.toggled.connect(lambda on: on and self.chk_hard.setChecked(False))
        self.chk_hard.toggled.connect(lambda on: on and self.chk_never.setChecked(False))
        left.addWidget(self.chk_never)
        left.addWidget(self.chk_hard)
        rs = QHBoxLayout()
        self.btn_session = QPushButton("Nouvelle session")
        self.btn_session.clicked.connect(self.start_session)
        self.btn_end = QPushButton("Terminer la session")
        self.btn_end.clicked.connect(self.end_session)
        self.btn_end.setVisible(False)
        btn_hist = QPushButton("Historique")
        btn_hist.clicked.connect(self.show_history)
        rs.addWidget(self.btn_session)
        rs.addWidget(self.btn_end)
        rs.addWidget(btn_hist)
        left.addLayout(rs)
        self.lbl_session = QLabel()
        theme.set_role(self.lbl_session, "headline")
        left.addWidget(self.lbl_session)
        self._clock = QElapsedTimer()
        self._tick = QTimer(self)
        self._tick.setInterval(500)
        self._tick.timeout.connect(self._update_work)
        self._phase, self._n, self._total = "import", 0, 0
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.setTextVisible(True)
        self.lbl_work = QLabel()
        self.btn_cancel = QPushButton("Arrêter")
        self.btn_cancel.setToolTip("Arrête le scan tout de suite ; il reprendra à la prochaine ouverture ou au prochain scan")
        self.btn_cancel.clicked.connect(self.cancel_scan)
        sb.addWidget(self.progress)
        sb.addWidget(self.lbl_work, 1)
        sb.addPermanentWidget(self.btn_cancel)
        self.progress.setVisible(False)
        self.lbl_work.setVisible(False)
        self.btn_cancel.setVisible(False)
        # surveillance du dossier : nouveaux fichiers analysés automatiquement (après 5 s de calme)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self._dir_changed)
        self.watcher.fileChanged.connect(self._dir_changed)
        self._watch_timer = QTimer(self)
        self._watch_timer.setSingleShot(True)
        self._watch_timer.setInterval(5000)
        self._watch_timer.timeout.connect(self._auto_scan)

        self.grp_filters = g = QGroupBox("Filtres")
        gl = QVBoxLayout(g)
        self.chk_move = QCheckBox("Coups")
        self.chk_cube = QCheckBox("Cube")
        self.chk_move.setChecked(True)
        self.chk_cube.setChecked(True)
        for c in (self.chk_move, self.chk_cube):
            c.toggled.connect(self.reload_list)
            gl.addWidget(c)
        gl.addWidget(QLabel("Type d'erreur :"))
        self.chk_class: dict[str, QCheckBox] = {}
        for k in ("doubtful", "bad", "very bad"):
            c = QCheckBox(CLASS_LABEL[k])
            c.setChecked(True)
            c.toggled.connect(self.reload_list)
            self.chk_class[k] = c
            gl.addWidget(c)
        gl.addWidget(QLabel("Joueurs (erreurs de) :"))
        self.players = QListWidget()
        self.players.setMaximumHeight(84)
        self.players.itemChanged.connect(lambda *_: self.reload_list())
        gl.addWidget(self.players)
        pr = QHBoxLayout()
        b_all = QPushButton("Tous")
        b_none = QPushButton("Aucun")
        b_all.clicked.connect(lambda: self._set_players(True))
        b_none.clicked.connect(lambda: self._set_players(False))
        pr.addWidget(b_all)
        pr.addWidget(b_none)
        gl.addLayout(pr)
        self.cmb_state = QComboBox()
        self.cmb_state.addItem("Tous les états", None)
        self.cmb_state.addItem("À faire (nouveau, en cours, passé)", ["new", "in_progress", "skipped"])
        self.cmb_state.addItem("Réussis", ["correct"])
        self.cmb_state.currentIndexChanged.connect(self.reload_list)
        gl.addWidget(self.cmb_state)
        self.cmb_order = QComboBox()
        for lab, k in (("Ordre : par partie", "match"), ("Ordre : plus grosse perte", "loss"), ("Ordre : aléatoire", "random")):
            self.cmb_order.addItem(lab, k)
        self.cmb_order.currentIndexChanged.connect(self.reload_list)
        gl.addWidget(self.cmb_order)
        left.addWidget(g)
        self.lst = QListWidget()
        self.lst.setItemDelegate(ExerciseDelegate(self.lst))
        self.lst.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.lst.currentRowChanged.connect(self.on_row)
        self.lst.setMinimumHeight(150)
        left.addWidget(self.lst, 1)
        self.lbl_count = QLabel()
        left.addWidget(self.lbl_count)

        # colonne centrale : plateau (maximisé) ; colonne droite : retour, statistiques, coach
        main = QHBoxLayout()
        main.setContentsMargins(12, 10, 12, 10)
        main.setSpacing(12)
        lay.addLayout(main, 1)
        right = QVBoxLayout()
        right.setSpacing(6)
        main.addLayout(right, 1)
        info = QVBoxLayout()
        info.setSpacing(8)
        self.analysis_panel = QWidget()
        self.analysis_panel.setFixedWidth(460)
        info.setContentsMargins(0, 0, 0, 0)
        self.analysis_panel.setLayout(info)
        main.addWidget(self.analysis_panel, 0)
        self.lbl_info = QLabel("Aucun exercice")
        self.lbl_info.setWordWrap(True)
        theme.set_role(self.lbl_info, "title")
        top = QHBoxLayout()
        self.btn_side = QPushButton("\u25c0 Menu")
        self.btn_side.setCheckable(True)
        self.btn_side.setChecked(True)
        self.btn_side.setToolTip("Replier / déplier le menu de gauche (Ctrl+M) : agrandit le plateau")
        self.btn_side.setShortcut("Ctrl+M")
        self.btn_side.toggled.connect(self._toggle_side)
        top.addWidget(self.btn_side, 0)
        top.addWidget(self.lbl_info, 1)
        right.addLayout(top)
        self.lbl_ctx = QLabel()
        right.addWidget(self.lbl_ctx)
        self.board = BoardWidget()
        self.board.pointClicked.connect(self.on_point)
        self.board.diceClicked.connect(self.swap_dice)
        right.addWidget(self.board, 1)
        self.lbl_fb = QLabel()
        self.lbl_fb.setWordWrap(True)
        self.lbl_fb.setMinimumHeight(60)
        theme.set_role(self.lbl_fb, "solution")
        self.lbl_fb.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        info.addWidget(self.lbl_fb)
        self.chk_match = QCheckBox("Afficher le coup joué en match (flèches grises)")
        self.chk_match.setChecked(self.settings.show_match_move)
        self.chk_match.toggled.connect(self._toggle_match)
        info.addWidget(self.chk_match)
        self.chk_pips = QCheckBox("Afficher le pip count")
        self.chk_pips.setChecked(self.settings.show_pips)
        self.chk_pips.toggled.connect(self._toggle_pips)
        self.board.set_show_pips(self.settings.show_pips)
        info.addWidget(self.chk_pips)
        self.stats = QPlainTextEdit()
        self.stats.setReadOnly(True)
        self.stats.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.stats.setMaximumHeight(300)
        f = QFont("monospace")
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setPixelSize(16)
        self.stats.setFont(f)
        self.stats.setMinimumHeight(0)
        self.stats.setVisible(False)
        info.addWidget(self.stats, 0)
        self.coach = QTextBrowser()
        self.coach.setMinimumHeight(0)
        cf = self.coach.font()
        cf.setPixelSize(18)
        self.coach.setFont(cf)
        self.coach.setVisible(False)
        info.addWidget(self.coach, 1)
        info.addStretch(0)
        row = QHBoxLayout()
        self.btn_undo = QPushButton("Annuler")
        self.btn_reset = QPushButton("Recommencer")
        self.btn_ok = QPushButton("Valider")
        self.btn_reveal = QPushButton("Voir la correction")
        self.btn_skip = QPushButton("Passer")
        self.btn_prev = QPushButton("< Précédent")
        self.btn_next = QPushButton("Suivant >")
        self.btn_undo.clicked.connect(self.undo)
        self.btn_reset.clicked.connect(self.reset)
        self.btn_ok.clicked.connect(self.validate)
        self.btn_reveal.clicked.connect(self.show_correction)
        self.btn_skip.clicked.connect(self.skip)
        self.btn_prev.clicked.connect(lambda: self.step(-1))
        self.btn_next.clicked.connect(lambda: self.step(1))
        for b in (self.btn_reset, self.btn_reveal, self.btn_skip, self.btn_prev, self.btn_next):
            row.addWidget(b)
        self.board.attach_move_buttons(self.btn_undo, self.btn_ok)  # sur le plateau, pas dans la barre du bas
        right.addLayout(row)
        for b in (self.btn_session, self.btn_ok, self.btn_undo):
            theme.set_role(b, "primary")
        for b in (self.btn_cancel, self.btn_end):
            theme.set_role(b, "destructive")
        self._accessibility()
        self._update_dir_label()
        self._enable(False)

    def _accessibility(self) -> None:
        """Noms accessibles (VoiceOver / lecteurs d'écran) pour les contrôles sans libellé explicite."""
        for w, n in ((self.lst, "Liste des exercices"), (self.players, "Joueurs"), (self.board, "Plateau de backgammon"),
                     (self.stats, "Statistiques de l'analyse"), (self.coach, "Conseils du coach"), (self.lbl_fb, "Retour de correction"),
                     (self.progress, "Progression du scan"), (self.cmb_state, "Filtre par état"),
                     (self.cmb_order, "Ordre des exercices")):
            w.setAccessibleName(n)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _update_dir_label(self) -> None:
        self.lbl_dir.setText(f"Répertoire : {self.settings.mat_directory or '(non configuré)'}")

    # ---------- filtres / liste ----------
    def refresh_players(self, check_new: bool = False) -> None:
        known = {self.players.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.players.count())}
        checked = {self.players.item(i).text().rsplit(" (", 1)[0] for i in range(self.players.count())
                   if self.players.item(i).checkState() == Qt.CheckState.Checked}
        first = self.players.count() == 0
        sel = set(self.settings.selected_players)
        self.players.blockSignals(True)
        self.players.clear()
        for p in self.svc.list_players():
            it = QListWidgetItem(f"{p['name']} ({p['count']})")
            it.setData(Qt.ItemDataRole.UserRole, p["name"])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            on = (p["name"] in sel) if first and sel else (p["name"] in checked if not first else not sel or p["name"] in sel)
            if not first and not checked:
                on = True
            if check_new and p["name"] not in known:
                on = True
            it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
            self.players.addItem(it)
        self.players.blockSignals(False)

    def _apply_players(self, names: set[str] | None) -> None:
        """Coche exactement ``names`` (None = tous), sans recharger la liste."""
        self.players.blockSignals(True)
        for i in range(self.players.count()):
            it = self.players.item(i)
            on = names is None or it.data(Qt.ItemDataRole.UserRole) in names
            it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        self.players.blockSignals(False)

    def _filter_single_players(self) -> None:
        """Mode fichier unique : ne garde cochés que les joueurs du fichier."""
        if not self.single:
            return
        names = {e["player_name"] for e in self.svc.list_exercises(source_path=self.single)}
        if names:
            self._apply_players(names)

    def _restore_players(self) -> None:
        """Rétablit la sélection de joueurs d'avant le mode fichier unique."""
        before, self._players_before = self._players_before, None
        if before is None:
            return
        self._apply_players(None if before == "ALL" else set(before))

    def _set_players(self, on: bool) -> None:
        self.players.blockSignals(True)
        for i in range(self.players.count()):
            self.players.item(i).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        self.players.blockSignals(False)
        self.reload_list()

    def _checked_players(self) -> list[str]:
        return [self.players.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.players.count())
                if self.players.item(i).checkState() == Qt.CheckState.Checked]

    def _checked_classes(self) -> list[str]:
        return [k for k, c in self.chk_class.items() if c.isChecked()]

    def reload_list(self, *_a) -> None:
        kinds = tuple(k for k, c in (("move", self.chk_move), ("cube", self.chk_cube)) if c.isChecked())
        allp = self.players.count()
        chosen = self._checked_players()
        prev_id = self.ex["id"] if self.ex else None
        if self.session_id:
            self.items = self.session_items
        elif allp and not chosen:
            self.items = []
        elif not kinds or not self._checked_classes():
            self.items = []
        else:
            self.items = self.svc.list_exercises(
                kinds=kinds, players=chosen if len(chosen) < allp else None,
                states=self.cmb_state.currentData(), source_path=self.single, order=self.cmb_order.currentData(),
                classes=self._checked_classes() if len(self._checked_classes()) < len(self.chk_class) else None)
        self.lst.blockSignals(True)
        self.lst.clear()
        for i in range(len(self.items)):
            self.lst.addItem("")
            self._paint_item(i)
        self.lst.blockSignals(False)
        self.lbl_count.setText(f"{len(self.items)} exercice(s)")
        if self.items:
            idx = next((i for i, e in enumerate(self.items) if e["id"] == prev_id), 0)
            self.lst.setCurrentRow(idx)
            self.load(idx)
        else:
            self.ex = None
            self._enable(False)
            self.board.set_state(Position.initial())
            self.board.pos = None
            self.board.set_dice(None)
            self.board.update()
            self.lbl_info.setText("Aucun exercice")
            self.board.set_prompt(None)
            self.board.set_cube_buttons([])
            self.lbl_ctx.setText("")
            self.lbl_fb.setText(self._empty_reason())

    def _append_new(self) -> None:
        """Pendant un scan : ajoute à la liste les nouveaux exercices, sans toucher à l'exercice en cours."""
        if self.session_id:
            return
        had = bool(self.items)
        self.refresh_players(check_new=True)
        if not had:
            self.reload_list()
            return
        kinds = tuple(k for k, c in (("move", self.chk_move), ("cube", self.chk_cube)) if c.isChecked())
        chosen, allp = self._checked_players(), self.players.count()
        if not kinds or not self._checked_classes() or (allp and not chosen):
            return
        fresh = self.svc.list_exercises(
            kinds=kinds, players=chosen if len(chosen) < allp else None,
            states=self.cmb_state.currentData(), source_path=self.single, order=self.cmb_order.currentData(),
            classes=self._checked_classes() if len(self._checked_classes()) < len(self.chk_class) else None)
        known = {e["id"] for e in self.items}
        new = [e for e in fresh if e["id"] not in known]
        if not new:
            return
        self.lst.blockSignals(True)
        for e in new:
            self.items.append(e)
            self.lst.addItem("")
            self._paint_item(len(self.items) - 1)
        self.lst.blockSignals(False)
        self.lbl_count.setText(f"{len(self.items)} exercice(s)")
        self._refresh_buttons()

    def _empty_reason(self) -> str:
        if self.worker and self.worker.isRunning():
            return "Analyse en cours : les exercices apparaissent dans la liste au fur et à mesure (voir la barre de progression à gauche)."
        if self.single:
            st = self.svc.source_status(self.single)
            return {
                "not_imported": "Fichier non importé : lancez l'analyse.",
                "unsupported": f"Fichier invalide : {st.get('error')}",
                "not_analyzed": "Fichier importé mais non analysé.",
                "analysis_failed": f"Échec de l'analyse : {st.get('error')}",
                "no_errors": "Analyse terminée : aucune erreur (douteux, mauvais ou très mauvais) dans ce fichier.",
                "ready": "Aucun exercice ne correspond aux filtres.",
            }[st["state"]]
        if not self.settings.mat_directory:
            return "Configurez un répertoire dans Paramètres puis lancez un scan."
        if self.players.count() == 0:
            return "Aucun exercice en base : lancez un scan du répertoire (analyse non faite ou sans erreur)."
        return "Aucun exercice ne correspond aux filtres."

    def on_row(self, row: int) -> None:
        if 0 <= row < len(self.items):
            self.load(row)

    def step(self, d: int) -> None:
        r = self.lst.currentRow() + d
        if 0 <= r < len(self.items):
            self.lst.setCurrentRow(r)
        else:
            self.lbl_fb.setText("Fin de la série." if d > 0 else "Début de la série.")

    # ---------- exercice ----------
    def _enable(self, on: bool) -> None:
        for b in (self.btn_undo, self.btn_reset, self.btn_ok, self.btn_reveal, self.btn_skip):
            b.setEnabled(on)
        if not on:
            self.btn_undo.setVisible(False)
            self.btn_ok.setVisible(False)
        self.btn_prev.setEnabled(on and self.lst.currentRow() > 0)
        self.btn_next.setEnabled(on and self.lst.currentRow() < len(self.items) - 1)

    def load(self, row: int) -> None:
        self.ex = self.svc.get_exercise(self.items[row]["id"])
        e = self.ex
        self.finished_ex = False
        self.done, self.sel = [], None
        self.start_pos = Position.from_dict(e["position"])
        self.cur_pos = self.start_pos
        who = e["player_name"]
        self.lbl_info.setText(f"{KIND[e['kind']]} {self._cls(e)}- {who} (noirs, au trait) - exercice {row + 1}/{len(self.items)}")
        sc = f"Score : {e['score_me']} - {e['score_opp']} (match en {e['match_length']})" if e["match_length"] else ""
        if e["crawford"]:
            sc += "  Crawford"
        cube = {"me": "cube à vous", "opp": "cube à l'adversaire", None: "cube au centre"}[e["cube_owner"]]
        self.lbl_ctx.setText(f"{sc}   Cube : {e['cube_value']} ({cube})   Partie {e['game_index'] + 1}")
        self._feedback("")
        self.stats.setVisible(False)
        self.coach.setVisible(False)
        self.board.set_arrows([])
        self.board.set_dice(e["dice"] if e["kind"] == "move" else None)
        self.board.set_state(self.start_pos, e["cube_value"], e["cube_owner"], e["offered_cube"])
        self.board.set_cube_buttons([])
        self.board.set_prompt(None)
        if e["kind"] == "move":
            self.lbl_fb.setText("Cliquez un pion puis sa destination. Cliquez la zone « Sortis » pour sortir un pion.")
        else:
            q = "Doublez-vous ?" if "double" in e["extra"]["options"] else f"Votre adversaire double à {e['offered_cube']}."
            self.board.set_prompt(q)
            self.lbl_fb.setText("Choisissez une action.")
            self.board.set_cube_buttons([(CUBE_LABEL[o], lambda o=o: self.answer_cube(o)) for o in e["extra"]["options"]])
        self._enable(True)
        self._refresh_buttons()
        if self.session_id and self.svc.is_locked(self.session_id, e["id"]):
            self._show_locked()

    def _cube_buttons(self, on: bool) -> None:
        self.board.set_cube_buttons_enabled(on)

    def _show_locked(self) -> None:
        """Exercice déjà validé dans la session : affichage en lecture seule du résultat."""
        e = self.ex
        ans = self.svc.session_answer(self.session_id, e["id"])
        rev = self.svc.reveal(e["id"])
        self.finished_ex = True
        self._cube_buttons(False)
        mine = ""
        if ans and ans["answer"]:
            a = ans["answer"]
            mine = "Votre réponse : " + (move_text(a["steps"]) if "steps" in a else CUBE_LABEL.get(a["action"], a["action"])) + "\n"
        if ans is None:
            self._feedback("Correction consultée : exercice terminé (échec).\n" + self._describe(rev))
        else:
            near = self._near(rev, ans["answer"], ans["correct"])
            conf = self.svc.conflict(e["id"], ans["answer"], ans["correct"])
            head = "CORRECT" if ans["correct"] else (f"PRESQUE BON (écart {near:.3f})" if near is not None else "INCORRECT")
            if conf:
                head = "MITIGÉ\n" + conf
            self._feedback(head + "\n" + mine + self._describe(rev),
                           self._mixed_color(bool(ans["correct"])) if conf else (GREEN if ans["correct"] else self._near_color(near)))
        self._arrows(rev, ans["answer"].get("steps") if ans and ans["answer"] else None, bool(ans and ans["correct"]))
        self._show_stats(rev, ans["answer"].get("steps") if ans and ans["answer"] else None)
        self._show_coach(ans["answer"] if ans else None)
        self._refresh_buttons()

    def _show_stats(self, rev: dict, answer: list | None = None) -> None:
        txt = analysis_text(rev.get("analysis"), rev.get("plies"), answer)
        self.stats.setPlainText(txt)
        # hauteur ajustée au contenu (le plateau garde la place), plafonnée
        lines = txt.count("\n") + 1
        self.stats.setFixedHeight(min(300, lines * self.stats.fontMetrics().lineSpacing() + 34))
        self.stats.setVisible(True)

    def _toggle_side(self, on: bool) -> None:
        self.sidebar.setVisible(on)
        self.btn_side.setText("\u25c0 Menu" if on else "\u25b6 Menu")

    def _show_coach(self, answer: dict | None) -> None:
        """Explication par les règles de REGLES_BACKGAMMON.md (bonnes et mauvaises décisions)."""
        items = self.svc.coach(self.ex["id"], answer)
        if not items:
            self.coach.setVisible(False)
            return
        col = {"ok": "#1f8a4c", "bad": "#c0392b", "info": "#555555"}
        mark = {"ok": "&#10003; ", "bad": "&#10007; ", "info": ""}
        h = ["<h3>Coach - pourquoi ?</h3>"]
        for k, t in items:
            t = t.replace("&", "&amp;").replace("<", "&lt;")
            t = re.sub(r"(Écart d'équité de [0-9.]+)", r"<b>\1</b>", t)
            h.append(f"<p style='color:{col[k]}; margin:6px 0; font-size:18px'>{mark[k]}{t}</p>")
        self.coach.setHtml("".join(h))
        self.coach.setVisible(True)

    def _opts(self) -> set:
        return self.svc.legal_next(self.ex["id"], self.done) if self.ex and self.ex["kind"] == "move" else set()

    def _refresh_buttons(self) -> None:
        mv = bool(self.ex and self.ex["kind"] == "move")
        self.btn_reset.setVisible(mv)
        complete = mv and bool(self.done) and not self._opts()
        # Annuler : dès qu'un dé est joué ; Valider : quand les deux dés (ou les 4 d'un double) sont joués
        self.btn_undo.setVisible(mv and bool(self.done) and not self.finished_ex)
        self.btn_ok.setVisible(bool(complete) and not self.finished_ex)
        self.btn_ok.setEnabled(complete and not self.finished_ex)
        self.btn_undo.setEnabled(bool(self.done) and not self.finished_ex)
        if self.session_id:
            self.btn_reset.setEnabled(bool(self.done) and not self.finished_ex)
            self.btn_reveal.setEnabled(bool(self.ex) and not self.finished_ex)
            self.btn_skip.setEnabled(bool(self.ex) and not self.finished_ex)
        else:
            self.btn_reset.setEnabled(bool(self.done) or self.finished_ex)
        self.btn_prev.setEnabled(self.lst.currentRow() > 0)
        self.btn_next.setEnabled(self.lst.currentRow() < len(self.items) - 1)

    def on_point(self, p: int) -> None:
        if not self.ex or self.ex["kind"] != "move" or self.finished_ex:
            return
        opts = self._opts()
        srcs = {s for s, _d, _ in opts}
        if p in srcs:
            cands = [o for o in opts if o[0] == p]
            first = self.ex["dice"][0]
            step = next((o for o in cands if o[2] == first), cands[0])
            self.cur_pos = apply_step(self.cur_pos, (step[0], step[1]))
            self.done.append(step)
            self.sel = None
            self.board.set_state(self.cur_pos, self.ex["cube_value"], self.ex["cube_owner"])
            self._after_step()
        else:
            self.sel = None
            self.board.set_selection(None, set())
            if p != 0 and opts:
                self.lbl_fb.setText("Sélection impossible ici (pas de pion jouable ou coup illégal).")

    def swap_dice(self) -> None:
        if not self.ex or self.ex["kind"] != "move" or self.finished_ex:
            return
        a, b = self.ex["dice"]
        self.ex["dice"] = type(self.ex["dice"])((b, a))
        self.board.set_dice(self.ex["dice"], [d for _s, _d, d in self.done])

    def _after_step(self) -> None:
        left = self._opts()
        self.board.set_dice(self.ex["dice"], [d for _s, _d, d in self.done])
        self.lbl_fb.setText("Coup complet : validez." if not left else f"{len(self.done)} pas joué(s).")
        self._refresh_buttons()

    def undo(self) -> None:
        if self.done and not self.finished_ex:
            self.done.pop()
            p = self.start_pos
            for s, d, _ in self.done:
                p = apply_step(p, (s, d))
            self.cur_pos, self.sel = p, None
            self.board.set_state(p, self.ex["cube_value"], self.ex["cube_owner"])
            self._after_step()

    def reset(self) -> None:
        if self.ex:
            self.load(self.lst.currentRow())

    def validate(self) -> None:
        r = self.svc.submit_attempt(self.ex["id"], {"steps": [[s, d] for s, d, _ in self.done]}, self.session_id)
        self._result(r)

    def answer_cube(self, opt: str) -> None:
        self._last_cube = opt
        self._result(self.svc.submit_attempt(self.ex["id"], {"action": opt}, self.session_id))

    def _result(self, r) -> None:
        if r.locked:
            self._feedback(r.message, RED)
            return
        self.finished_ex = True
        if not r.legal:
            self.finished_ex = False
            self._feedback(r.message, RED)
            self._refresh_buttons()
            return
        near = None
        if r.reveal and self.ex["kind"] == "move":
            near = self._near(r.reveal, {"steps": [[a, b] for a, b, _ in self.done]}, r.correct)
        txt = "CORRECT" if r.correct else (f"PRESQUE BON (écart {near:.3f})" if near is not None else "INCORRECT")
        conf = None
        if r.reveal:
            conf = self.svc.conflict(self.ex["id"], {"steps": [[a, b] for a, b, _ in self.done]} if self.ex["kind"] == "move"
                                     else {"action": self._last_cube}, r.correct)
        if conf:
            txt = "MITIGÉ\n" + conf
        if r.reveal:
            txt += "\n" + self._describe(r.reveal)
            self._arrows(r.reveal, [[a, b] for a, b, _ in self.done], r.correct)
            self._show_stats(r.reveal, [[a, b] for a, b, _ in self.done] or None)
            self._show_coach({"steps": [[a, b] for a, b, _ in self.done]} if self.ex["kind"] == "move"
                             else {"action": self._last_cube})
        elif not r.correct:
            txt += " - cliquez « Recommencer » pour réessayer ou « Voir la correction »."
        if self.session_id:
            txt += "\nRéponse enregistrée : elle ne peut plus être modifiée dans cette session."
            self._cube_buttons(False)
        self._feedback(txt, self._mixed_color(bool(r.correct)) if conf else (GREEN if r.correct else self._near_color(near)))
        self._sync_item()
        self._update_session_label()
        self._refresh_buttons()
        if not self.session_id:
            self.btn_reset.setEnabled(True)
        elif all(o != "unanswered" for o in self.outcomes.values()):
            self.btn_next.setEnabled(False)
            self.lbl_fb.setText(self.lbl_fb.text() + "\nDernier exercice traité : cliquez « Terminer la session » pour voir le résultat.")

    def _near(self, rev: dict, answer: dict | None, correct: bool) -> float | None:
        """Perte d'équité si votre coup est « presque bon » (faux mais très proche du meilleur), sinon None."""
        if correct or not answer or "steps" not in answer:
            return None
        d = user_loss(rev.get("analysis"), answer["steps"])
        return d if d is not None and d < NEAR_GOOD else None

    @staticmethod
    def _mixed_color(engine_ok: bool) -> str:
        """Verdict mitigé : moitié vert / moitié orange ; commence par le vert si le moteur valide, par l'orange sinon."""
        a, b = (GREEN, ORANGE) if engine_ok else (ORANGE, GREEN)
        return f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {a}, stop:0.50 {a}, stop:1 {b})"

    @staticmethod
    def _near_color(near: float | None) -> str:
        """Rouge si pas « presque bon » ; sinon dégradé vert -> orange, le vert dominant (plus l'écart est faible, plus il domine)."""
        if near is None:
            return RED
        g = 0.75 - 0.25 * min(1.0, near / NEAR_GOOD)  # fin du vert : 75 % (écart nul) -> 50 %
        return f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {GREEN}, stop:{g:.2f} {GREEN}, stop:1 {ORANGE})"

    def _feedback(self, text: str, color: str | None = None) -> None:
        self.lbl_fb.setText(text)
        self.lbl_fb.setStyleSheet(f"background: {color}; color: white; font-weight: 600; padding: 12px 14px; border-radius: 8px;" if color else "")

    def _describe(self, rev: dict) -> str:
        if self.ex["kind"] == "move":
            f = lambda mv: " ".join(f"{'bar' if a == 25 else a}/{'off' if b == 0 else b}" for a, b in mv)
            best = "  ou  ".join(f(m) for m in rev["best"])
            return f"Meilleur : {best}\nJoué en match : {f(rev['played'])} (perte {rev['loss']:.3f}). Flèches : vert = meilleur, rouge pointillé = votre réponse, gris = joué en match (option)."
        return f"Meilleur : {CUBE_LABEL[rev['best']]}. Joué en match : {CUBE_LABEL[rev['played']]}."

    def _arrows(self, rev: dict, answer: list | None = None, correct: bool = False) -> None:
        """Vert = meilleur coup ; rouge pointillé = votre réponse (si fausse) ; gris = coup joué en match (option)."""
        if self.ex["kind"] != "move":
            return
        self._arrow_ctx = (rev, answer, correct)
        self.board.set_state(self.start_pos, self.ex["cube_value"], self.ex["cube_owner"])
        arrows = [(rev["best"][0], GREEN, False)]
        if answer and not correct:
            arrows.append(([tuple(x) for x in answer], RED, True))
        if self.chk_match.isChecked():
            arrows.append((rev["played"], GRAY, False))
        self.board.set_arrows(arrows)

    def _toggle_pips(self, on: bool) -> None:
        self.settings.show_pips = on
        self.board.set_show_pips(on)
        try:
            save_settings(self.settings)
        except ConfigError:
            pass

    def _toggle_match(self, on: bool) -> None:
        self.settings.show_match_move = on
        try:
            save_settings(self.settings)
        except ConfigError:
            pass
        if getattr(self, "_arrow_ctx", None) and self.finished_ex and self.ex:
            self._arrows(*self._arrow_ctx)

    def show_correction(self) -> None:
        if not self.ex or self.finished_ex:
            return
        if self.session_id:
            if QMessageBox.question(self, "Voir la correction",
                                    "Voir la correction termine cet exercice : il sera compté comme un échec et ne pourra plus être modifié. Continuer ?") \
                    != QMessageBox.StandardButton.Yes:
                return
            self.svc.record_reveal(self.session_id, self.ex["id"])
            self._sync_item()
            self._update_session_label()
            self._cube_buttons(False)
        rev = self.svc.reveal(self.ex["id"])
        self.finished_ex = True
        self._feedback(self._describe(rev))
        self._arrows(rev)
        self._show_stats(rev)
        self._show_coach(None)
        self._refresh_buttons()
        if not self.session_id:
            self.btn_reset.setEnabled(True)

    def skip(self) -> None:
        if self.ex:
            if self.session_id and self.svc.is_locked(self.session_id, self.ex["id"]):
                self.step(1)
                return
            if self.items[self.lst.currentRow()]["state"] != "correct":
                self.svc.set_exercise_status(self.ex["id"], "skipped")
            if self.session_id:
                self.svc.record_skip(self.session_id, self.ex["id"])
            self._sync_item()
            self._update_session_label()
            self.step(1)

    def _sync_item(self) -> None:
        row = self.lst.currentRow()
        fresh = self.svc.list_exercises(kinds=(self.ex["kind"],), source_path=self.single)
        st = next((e for e in fresh if e["id"] == self.ex["id"]), None)
        if st and 0 <= row < len(self.items):
            self.items[row] = {**self.items[row], "state": st["state"], "attempts": st["attempts"]}
        if self.session_id:
            self.outcomes = self.svc.session_outcomes(self.session_id)
        if 0 <= row < len(self.items):
            self._paint_item(row)

    @staticmethod
    def _cls(e: dict) -> str:
        c = CLASS_LABEL.get(e.get("classification") or "")
        return f"({c.lower()}) " if c else ""

    def _paint_item(self, row: int) -> None:
        e = self.items[row]
        it = self.lst.item(row)
        if self.session_id:
            o = self.outcomes.get(e["id"], "unanswered")
            lock = "  [verrouillé]" if o in ("first_try", "retry", "failed") else ""
            lab = {"first_try": "RÉUSSI", "retry": "RÉUSSI", "failed": "ERREUR", "skipped": "passé", "unanswered": ""}[o]
            it.setText(f"{row + 1}. {KIND[e['kind']]} {self._cls(e)}- {e['player_name']}  {lab}{lock}".rstrip())
            bg = {"first_try": GREEN, "retry": GREEN, "failed": RED}.get(o)
            it.setBackground(QBrush(QColor(bg)) if bg else QBrush())
            it.setForeground(QColor("white") if bg else (QColor("#86868B") if o == "skipped" else QBrush()))
        else:
            it.setText(f"{row + 1}. {KIND[e['kind']]} {self._cls(e)}- {e['player_name']} [{STATE[e['state']]}]")
            bg = {"correct": GREEN, "in_progress": RED}.get(e["state"])
            it.setBackground(QBrush(QColor(bg)) if bg else QBrush())
            it.setForeground(QColor("white") if bg else (QColor("#86868B") if e["state"] == "skipped" else QBrush()))

    # ---------- sessions ----------
    def _filters(self) -> dict:
        return {"kinds": [k for k, c in (("move", self.chk_move), ("cube", self.chk_cube)) if c.isChecked()],
                "players": self._checked_players(), "states": self.cmb_state.currentData(),
                "order": self.cmb_order.currentData(), "single": self.single,
                "classes": self._checked_classes()}

    def start_session(self, _checked=False, ask: bool = True) -> None:
        if self.session_id:
            if ask and QMessageBox.question(self, "Session en cours", "Abandonner la session en cours et en démarrer une nouvelle ?") \
                    != QMessageBox.StandardButton.Yes:
                return
            self.svc.finish_session(self.session_id)
            self.session_id = None
            self.reload_list()
        if not self.items:
            if not ask:
                return
            QMessageBox.information(self, "Session", "Aucun exercice dans la liste : modifiez les filtres ou lancez un scan.")
            return
        pool = [dict(e) for e in self.items]
        if self.chk_never.isChecked() or self.chk_hard.isChecked():
            hist = self.svc.exercise_history()
            if self.chk_never.isChecked():
                pool = [e for e in pool if e["state"] == "new" and e["logical_key"] not in hist]
                why = "jamais faits"
            else:
                pool = [e for e in pool if hist.get(e["logical_key"], (0, 0))[0] > 0
                        and hist[e["logical_key"]][1] / hist[e["logical_key"]][0] > 0.5]
                why = "où vous échouez dans plus de 50 % des cas"
            if not pool:
                if ask:
                    QMessageBox.information(self, "Session", f"Aucun exercice {why} dans la liste actuelle "
                                            "(vérifiez les filtres ou décochez l'option).")
                return
        self.session_items = pool
        self.session_id = self.svc.start_session(self.session_items, self._filters())
        self.outcomes = self.svc.session_outcomes(self.session_id)
        self.grp_filters.setEnabled(False)
        self.btn_session.setVisible(False)
        self.chk_never.setVisible(False)
        self.chk_hard.setVisible(False)
        self.btn_end.setVisible(True)
        self._update_session_label()
        self.reload_list()
        self.lst.setCurrentRow(0)
        self.load(0)

    def _update_session_label(self) -> None:
        if not self.session_id:
            self.lbl_session.setText("")
            return
        n = len(self.outcomes)
        done = sum(1 for o in self.outcomes.values() if o != "unanswered")
        ok = sum(1 for o in self.outcomes.values() if o == "first_try")
        self.lbl_session.setText(f"Session : {done}/{n} traités, {ok} réussis du 1er coup")

    def end_session(self, _checked=False, ask: bool = True) -> None:
        if not self.session_id:
            return
        left = sum(1 for o in self.outcomes.values() if o == "unanswered")
        if ask and left and QMessageBox.question(
                self, "Terminer", f"{left} exercice(s) non traité(s). Terminer la session quand même ?") != QMessageBox.StandardButton.Yes:
            return
        sid = self.session_id
        sm = self.svc.finish_session(sid)
        prev = next((x for x in reversed(self.svc.list_sessions()) if x["id"] != sid and x["status"] == "finished"), None)
        self.session_id, self.session_items, self.outcomes = None, [], {}
        self.grp_filters.setEnabled(True)
        self.btn_session.setVisible(True)
        self.chk_never.setVisible(True)
        self.chk_hard.setVisible(True)
        self.btn_end.setVisible(False)
        self._update_session_label()
        SummaryDialog(sm, prev, self).exec()
        self._restore_players()
        self.reload_list()

    def show_history(self) -> None:
        HistoryDialog(self.svc.list_sessions(), self).exec()

    # ---------- scan / fichier unique ----------
    def open_settings(self) -> None:
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Paramètres", "Un scan est en cours : attendez sa fin ou annulez-le.")
            return
        dlg = SettingsDialog(self.settings, self)
        if not dlg.exec():
            return
        self.svc = TrainerService(self.settings)
        self._update_dir_label()
        if dlg.clear_sessions_requested and not dlg.reset_requested:
            self.session_id, self.session_items, self.outcomes = None, [], {}
            self.grp_filters.setEnabled(True)
            self.btn_session.setVisible(True)
            self.chk_never.setVisible(True)
            self.chk_hard.setVisible(True)
            self.btn_end.setVisible(False)
            try:
                info = self.svc.clear_sessions()
            except Exception as e:  # noqa: BLE001
                QMessageBox.critical(self, "Historique des sessions", f"Échec : {e}")
                return
            self._update_session_label()
            self.reload_list()
            self._feedback(f"Historique vidé : {info['sessions']} session(s) supprimée(s) (sauvegarde : {info['backup']}).")
            return
        if dlg.reset_requested:
            if self.session_id:
                self.svc.finish_session(self.session_id)
                self.session_id, self.session_items, self.outcomes = None, [], {}
                self.grp_filters.setEnabled(True)
                self.btn_session.setVisible(True)
                self.chk_never.setVisible(True)
                self.chk_hard.setVisible(True)
                self.btn_end.setVisible(False)
                self._update_session_label()
            try:
                info = self.svc.reset_database(keep_sessions=dlg.keep_sessions)
            except Exception as e:  # noqa: BLE001
                QMessageBox.critical(self, "Réinitialisation", f"Échec : {e}")
                return
            self.single = None
            self.btn_exit_single.setVisible(False)
            self.lbl_single.setText("")
            self.refresh_players()
            self.reload_list()
            self._feedback(f"Base vidée (sauvegarde : {info['backup']}). Scan en cours...")
            self.scan_dir()
            return
        self.refresh_players()
        self.reload_list()

    def scan_dir(self) -> None:
        try:
            self.settings.check_mat_directory()
        except ConfigError as e:
            QMessageBox.warning(self, "Configuration", str(e))
            return
        self._start_scan(None)

    def rescan_pending(self) -> None:
        """Relance le scan : seuls les fichiers pas encore analysés sont traités (les échecs sont retentés)."""
        try:
            self.settings.check_mat_directory()
        except ConfigError as e:
            QMessageBox.warning(self, "Configuration", str(e))
            return
        self._start_scan(None, retry_failed=True)

    def pick_single(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Fichier .mat", self.settings.mat_directory, "Fichiers .mat (*.mat *.MAT)")
        if not f:
            return
        if self.session_id and QMessageBox.question(
                self, "Session en cours", "Une session est en cours. L'abandonner pour ouvrir ce fichier ?") != QMessageBox.StandardButton.Yes:
            return
        if self.session_id:
            self.end_session(ask=False)
        if self._players_before is None:
            chosen = self._checked_players()
            self._players_before = "ALL" if len(chosen) == self.players.count() else chosen
        self.single = f
        self._auto_session = True
        self.btn_exit_single.setVisible(True)
        self.lbl_single.setText(f"Mode fichier unique : {Path(f).name}")
        self._start_scan([Path(f)])

    def exit_single(self) -> None:
        if self.session_id:
            if QMessageBox.question(self, "Session en cours", "Quitter le mode fichier unique termine la session en cours. Continuer ?") \
                    != QMessageBox.StandardButton.Yes:
                return
            self.end_session(ask=False)
        self._auto_session = False
        self.single = None
        self.btn_exit_single.setVisible(False)
        self.lbl_single.setText("")
        self._restore_players()
        self.reload_list()

    def _start_scan(self, paths, silent: bool = False, retry_failed: bool = False) -> None:
        if self.worker and self.worker.isRunning():
            return
        self._silent = silent
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self._phase, self._n, self._total = "import", 0, 0
        self._clock.start()
        self._tick.start()
        self._update_work()
        self.lbl_work.setVisible(True)
        if not self.items and not silent:
            self.lbl_fb.setText("Analyse en cours : les exercices apparaissent dans la liste au fur et à mesure.")
        self.btn_cancel.setVisible(True)
        self.btn_cancel.setEnabled(True)
        self.btn_scan.setEnabled(False)
        self.btn_rescan.setEnabled(False)
        self.btn_single.setEnabled(False)
        self.worker = ScanWorker(self.svc, paths, retry_failed)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.start()

    def _on_progress(self, phase: str, n: int, total: int) -> None:
        self._phase, self._n, self._total = phase, n, total
        if phase == "analyse" and n > 0:
            self._append_new()  # une analyse vient de se terminer : ses exercices apparaissent tout de suite
        if phase == "annulation":
            self.progress.setRange(0, max(total, 1))
            self.progress.setValue(n)
            self.progress.setFormat("%v/%m")
        elif phase == "import":
            self.progress.setRange(0, max(total, 1))
            self.progress.setValue(n)
            self.progress.setFormat("import %v/%m")
        elif total == 0:
            self.progress.setRange(0, 1)
            self.progress.setValue(1)
            self.progress.setFormat("rien à analyser")
        elif n < total:
            # gnubg ne donne pas d'avancement interne : barre animée tant que des analyses tournent
            self.progress.setRange(0, 0) if n == 0 else (self.progress.setRange(0, total), self.progress.setValue(n))
            self.progress.setFormat("analyse %v/%m")
        else:
            self.progress.setRange(0, total)
            self.progress.setValue(total)
        self._update_work()

    def _update_work(self) -> None:
        if self._phase == "annulation":
            self.lbl_work.setText("Arrêt en cours...")
            return
        secs = self._clock.elapsed() // 1000 if self._clock.isValid() else 0
        t = f"{secs // 60:02d}:{secs % 60:02d}"
        if self._phase == "import":
            msg = f"Lecture des fichiers {self._n}/{self._total}"
        elif self._total == 0:
            msg = "Tout est déjà analysé"
        else:
            msg = f"Analyse gnubg {self._n}/{self._total} fichier(s) - {self.svc.scan_exercises} exercice(s) créés, {len(self.items)} dans la liste"
        self.lbl_work.setText(f"{msg} - {t}")

    # ---------- scan automatique ----------
    def _startup_scan(self) -> None:
        """Au démarrage : reprise silencieuse des fichiers interrompus + nouveaux fichiers."""
        try:
            self.svc.recover_interrupted()
            self.settings.check_mat_directory()
        except Exception:  # noqa: BLE001 - répertoire non configuré : rien à faire
            return
        self._update_watch()
        self._start_scan(None, silent=True)

    def _update_watch(self) -> None:
        old = self.watcher.directories() + self.watcher.files()
        if old:
            self.watcher.removePaths(old)
        try:
            root = self.settings.check_mat_directory()
        except Exception:  # noqa: BLE001
            return
        dirs = [str(root)]
        if self.settings.include_subdirectories:
            dirs += [str(d) for d in root.rglob("*") if d.is_dir()]
        self.watcher.addPaths(dirs)

    def _dir_changed(self, _path: str) -> None:
        self._watch_timer.start()  # relancé à chaque modification : on attend 5 s de calme

    def _auto_scan(self) -> None:
        if self.worker and self.worker.isRunning():
            self._rescan = True  # repris à la fin du scan en cours
            return
        self._update_watch()
        self._start_scan(None, silent=True)

    def closeEvent(self, e) -> None:  # noqa: N802
        """Arrête proprement un scan en cours ; il reprendra à la prochaine ouverture."""
        if self.worker and self.worker.isRunning():
            self.worker.cancel.set()
            self.worker.wait(8000)
        super().closeEvent(e)

    def cancel_scan(self) -> None:
        if self.worker:
            self.worker.cancel.set()
            self.btn_cancel.setEnabled(False)
            self.lbl_work.setText("Arrêt en cours... le scan reprendra à la prochaine ouverture.")

    def _end_scan(self) -> None:
        self._tick.stop()
        self.lbl_work.setVisible(False)
        self.progress.setVisible(False)
        self.btn_cancel.setVisible(False)
        self.btn_scan.setEnabled(True)
        self.btn_rescan.setEnabled(True)
        self.btn_single.setEnabled(True)

    def _on_done(self, report) -> None:
        self._end_scan()
        fails = [f for f in report.files if f.error]
        if getattr(self, "_silent", False):
            self._silent = False
            self._append_new()
            self._filter_single_players()
            if fails:
                self.statusBar().showMessage(f"Scan : {len(fails)} fichier(s) en échec ({fails[0].error[:80]})", 8000)
            elif any(f.analyzed for f in report.files):
                self.statusBar().showMessage(f"Scan terminé : {sum(f.exercises for f in report.files)} nouveau(x) exercice(s)", 8000)
            if self._rescan:
                self._rescan = False
                self._auto_scan()
            return
        self.refresh_players()
        self._filter_single_players()
        self.reload_list()
        msg = f"Scan terminé : {len(report.files)} fichier(s), {sum(f.exercises for f in report.files)} nouvel(le)s erreur(s)."
        if report.files and report.up_to_date and not any(f.analyzed for f in report.files):
            msg = "Tout est à jour."
        if fails:
            msg += f" {len(fails)} échec(s) : {fails[0].error[:150]}"
        if not self.items:
            msg += "\n" + self.lbl_fb.text()
        self.lbl_fb.setText(msg)
        if self._auto_session:
            # plus de session automatique : l'utilisateur choisit d'abord ses filtres (types d'erreur, coups/cube...)
            self._auto_session = False
            if self.single and self.items:
                self.lbl_fb.setText(msg + "\nChoisissez les types d'erreur et de décision dans les filtres, "
                                    "puis cliquez « Nouvelle session ».")

    def _on_fail(self, msg: str) -> None:
        self._auto_session = False
        self._end_scan()
        if getattr(self, "_silent", False):
            self._silent = False
            self.statusBar().showMessage(f"Scan impossible : {msg[:120]}", 10000)
            return
        QMessageBox.critical(self, "Échec du scan", msg)
        self.reload_list()
