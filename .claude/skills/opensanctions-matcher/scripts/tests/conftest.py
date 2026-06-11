import shutil
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def names_txt() -> Path:
    return FIXTURES / "names.txt"


@pytest.fixture
def simple_csv() -> Path:
    return FIXTURES / "targets.simple.csv"


@pytest.fixture
def ftm_json() -> Path:
    return FIXTURES / "entities.ftm.json"


@pytest.fixture
def dataset_dir(tmp_path: Path, names_txt: Path, simple_csv: Path, ftm_json: Path) -> Path:
    """Copy all fixture files into a temp dir."""
    shutil.copy(names_txt, tmp_path / "names.txt")
    shutil.copy(simple_csv, tmp_path / "targets.simple.csv")
    shutil.copy(ftm_json, tmp_path / "entities.ftm.json")
    return tmp_path
