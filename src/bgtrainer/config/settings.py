"""Configuration (JSON versionné, sans dépendance à PyQt)."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_VERSION = 1
ERROR_CLASSES = ("doubtful", "bad", "very bad")  # classes de skill gnubg, de la moins à la plus grave


class ConfigError(Exception):
    pass


def default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "backgammon-trainer" / "config.json"


def default_db_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "backgammon-trainer" / "trainer.sqlite3"


@dataclass
class Settings:
    config_version: int = CONFIG_VERSION
    mat_directory: str = ""
    include_subdirectories: bool = True
    database_path: str = field(default_factory=lambda: str(default_db_path()))
    scan_retry_failed: bool = True
    engine_executable: str = "gnubg"
    engine_timeout_seconds: int = 900
    engine_plies: int = 2
    engine_workers: int = max(1, min(8, (os.cpu_count() or 2) // 2))
    exercise_classes: list[str] = field(default_factory=lambda: list(ERROR_CLASSES))  # classes extraites à l'analyse
    near_equal_tolerance: float = 0.001
    reveal_correction_after_incorrect: bool = True
    show_pips: bool = False  # afficher le pip count
    show_match_move: bool = False  # flèches grises : coup joué lors du match
    selected_players: list[str] = field(default_factory=list)  # vide = tous

    def validate(self) -> None:
        if self.config_version != CONFIG_VERSION:
            raise ConfigError(f"config_version {self.config_version} non supportée (attendu {CONFIG_VERSION}).")
        if self.engine_plies not in (0, 1, 2, 3, 4):
            raise ConfigError("engine_plies doit être entre 0 et 4.")
        if self.engine_timeout_seconds <= 0 or self.engine_timeout_seconds > 86400:
            raise ConfigError("engine_timeout_seconds doit être dans ]0, 86400].")
        if self.engine_workers < 1:
            raise ConfigError("engine_workers doit être >= 1.")
        if self.near_equal_tolerance < 0:
            raise ConfigError("near_equal_tolerance doit être >= 0.")
        if not self.exercise_classes or any(c not in ERROR_CLASSES for c in self.exercise_classes):
            raise ConfigError(f"exercise_classes: valeurs admises {list(ERROR_CLASSES)} (au moins une).")
        if Path(os.path.expanduser(self.database_path)).is_dir():
            raise ConfigError("database_path désigne un répertoire, pas un fichier.")

    def check_mat_directory(self) -> Path:
        if not self.mat_directory:
            raise ConfigError("Aucun répertoire .mat configuré (mat_directory).")
        p = Path(os.path.expandvars(os.path.expanduser(self.mat_directory)))
        if not p.is_dir() or not os.access(p, os.R_OK):
            raise ConfigError(f"Répertoire .mat absent ou illisible : {p}")
        return p

    @property
    def db_file(self) -> Path:
        return Path(os.path.expandvars(os.path.expanduser(self.database_path)))


def load_settings(path: Path | None = None) -> Settings:
    path = path or default_config_path()
    if not path.exists():
        s = Settings()
        s.validate()
        return s
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path} : JSON invalide ({e})") from e
    old = data.pop("exercise_classification", None)  # ancien paramètre (une seule classe) : ignoré, toutes les classes sont extraites
    del old
    known = Settings.__dataclass_fields__
    unknown = set(data) - set(known)
    if unknown:
        raise ConfigError(f"{path} : paramètres inconnus {sorted(unknown)}")
    s = Settings(**data)
    s.validate()
    return s


def save_settings(s: Settings, path: Path | None = None) -> None:
    """Écriture atomique après validation."""
    s.validate()
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(s), indent=2, ensure_ascii=False))
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
