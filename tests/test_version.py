import re
from pathlib import Path

import bgtrainer


def test_version_coherente():
    root = Path(__file__).resolve().parents[1]
    py = re.search(r'^version = "([^"]+)"', (root / "pyproject.toml").read_text(), re.M).group(1)
    assert bgtrainer.__version__ == py
    assert re.match(r"^\d+\.\d+\.\d+$", py)
    assert f"## [{py}]" in (root / "CHANGELOG.md").read_text()


def test_icone_presente():
    assert (Path(bgtrainer.__file__).parent / "ui" / "assets" / "icon.png").stat().st_size > 1000
