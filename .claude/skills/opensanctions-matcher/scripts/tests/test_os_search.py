import os
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from os_search import os_web_url, get_index_path, index_is_stale, fts_query, build_ftm_index, search_fts_ftm


def test_os_web_url_basic():
    url = os_web_url("il_mod_crypto", "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy")
    assert url == "https://www.opensanctions.org/search/?scope=il_mod_crypto&q=TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"


def test_os_web_url_encodes_spaces():
    url = os_web_url("eu_fsf", "Alexei Navalny")
    assert url == "https://www.opensanctions.org/search/?scope=eu_fsf&q=Alexei+Navalny"


def test_os_web_url_encodes_special_chars():
    url = os_web_url("default", "Müller & Co.")
    assert "M%C3%BCller" in url or "M%c3%bcller" in url
    assert "%26" in url or "&amp;" not in url


from os_search import search_names_txt


def test_search_names_txt_match(names_txt):
    result = search_names_txt(names_txt, ["TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"], rg_bin=None)
    assert "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy" in result
    assert result["TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"] == ["TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"]


def test_search_names_txt_no_match(names_txt):
    result = search_names_txt(names_txt, ["TD74QLHWar5AvRUy56T8yzQS7bxNNAmiZy"], rg_bin=None)
    assert result["TD74QLHWar5AvRUy56T8yzQS7bxNNAmiZy"] == []


def test_search_names_txt_skips_comments_and_blanks(tmp_path):
    f = tmp_path / "names.txt"
    f.write_text("# comment line\n\nTARGET_ADDR\n  \n")
    result = search_names_txt(f, ["TARGET_ADDR"], rg_bin=None)
    assert result["TARGET_ADDR"] == ["TARGET_ADDR"]
    result2 = search_names_txt(f, ["comment"], rg_bin=None)
    assert result2["comment"] == []


def test_search_names_txt_case_insensitive(names_txt):
    result = search_names_txt(names_txt, ["tufxua1q"], rg_bin=None)
    assert len(result["tufxua1q"]) >= 1


from os_search import search_csv, format_csv_entity


def test_search_csv_match(simple_csv):
    result = search_csv(simple_csv, ["TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"], rg_bin=None)
    assert "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy" in result
    rows = result["TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"]
    assert len(rows) == 1
    assert rows[0]["id"] == "Q123"
    assert rows[0]["schema"] == "CryptoWallet"


def test_search_csv_no_match(simple_csv):
    result = search_csv(simple_csv, ["TD74QLHWar5AvRUy56T8yzQS7bxNNAmiZy"], rg_bin=None)
    assert result["TD74QLHWar5AvRUy56T8yzQS7bxNNAmiZy"] == []


def test_search_csv_missing_columns(tmp_path):
    f = tmp_path / "targets.simple.csv"
    f.write_text("id,caption\nQ999,SomeTarget\n")
    result = search_csv(f, ["SomeTarget"], rg_bin=None)
    rows = result["SomeTarget"]
    assert rows[0]["id"] == "Q999"
    assert rows[0].get("schema", "") == ""  # missing column returns empty string


def test_format_csv_entity_basic(simple_csv):
    result = search_csv(simple_csv, ["TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"], rg_bin=None)
    row = result["TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"][0]
    output = format_csv_entity(row, "il_mod_crypto")
    assert "CryptoWallet" in output
    assert "Q123" in output
    assert "sanction" in output.lower()


def test_format_csv_entity_missing_columns():
    row = {"id": "Q999", "caption": "MinimalRow"}
    output = format_csv_entity(row, "test_dataset")
    assert "Q999" in output
    assert "MinimalRow" in output


import subprocess


def run_script(args: list[str]) -> subprocess.CompletedProcess:
    script = Path(__file__).parent.parent / "os_search.py"
    return subprocess.run(
        ["python3", str(script)] + args,
        capture_output=True, text=True
    )


def test_main_names_phase1_hit(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--targets", "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"])
    assert "FTS MATCH" in r.stdout
    assert "opensanctions.org/search" in r.stdout
    assert r.returncode == 0


def test_main_names_phase2_enrichment(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--targets", "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"])
    assert "CryptoWallet" in r.stdout
    assert "Q123" in r.stdout


def test_main_names_no_match(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--targets", "TD74QLHWar5AvRUy56T8yzQS7bxNNAmiZy"])
    assert "NO MATCH" in r.stdout
    assert r.returncode == 2


def test_main_backwards_compat_ftm(dataset_dir):
    # --dataset path/to/entities.ftm.json must still route to FtM path
    ftm = dataset_dir / "entities.ftm.json"
    ftm.write_text('{"id":"x","schema":"CryptoWallet","caption":"x","properties":{"publicKey":["TD74QLHWar5AvRUy56T8yzQS7bxNNAmiZy"]},"datasets":["test"],"first_seen":"2024-01-01","last_seen":"2026-01-01"}\n')
    r = run_script(["--dataset", str(ftm),
                    "--targets", "TD74QLHWar5AvRUy56T8yzQS7bxNNAmiZy"])
    assert "CryptoWallet" in r.stdout
    assert r.returncode == 0


def test_main_explicit_file_csv(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--file", "csv",
                    "--targets", "Alexei Navalny"])
    assert "Person" in r.stdout
    assert r.returncode == 0


def test_main_explicit_file_names(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--file", "names",
                    "--targets", "Hamas Finance Committee"])
    assert "FTS MATCH" in r.stdout


def test_get_index_path(tmp_path):
    source = tmp_path / "names.txt"
    source.touch()
    assert get_index_path(source) == tmp_path / "names.txt.fts5.db"


def test_index_is_stale_missing(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("name")
    index = tmp_path / "names.txt.fts5.db"
    assert index_is_stale(source, index) is True


def test_index_is_stale_fresh(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("name")
    index = tmp_path / "names.txt.fts5.db"
    index.touch()
    os.utime(index, (source.stat().st_mtime + 1, source.stat().st_mtime + 1))
    assert index_is_stale(source, index) is False


def test_index_is_stale_source_newer(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("name")
    index = tmp_path / "names.txt.fts5.db"
    index.touch()
    os.utime(source, (index.stat().st_mtime + 1, index.stat().st_mtime + 1))
    assert index_is_stale(source, index) is True


def test_fts_query_multiword():
    assert fts_query("Vladimir Putin") == '"Vladimir Putin"'


def test_fts_query_single_alnum():
    q = fts_query("Gazprom")
    assert q == "Gazprom OR Gazprom*"


def test_fts_query_crypto_address():
    addr = "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy"
    assert fts_query(addr) == addr


def test_fts_query_special_chars():
    # Non-alnum single token → quoted phrase (safe fallback)
    q = fts_query("Al-Qaeda")
    assert q.startswith('"') and q.endswith('"')


def test_index_is_stale_missing_source(tmp_path):
    """Regression test: index_is_stale should raise FileNotFoundError if source doesn't exist."""
    import pytest
    source = tmp_path / "nonexistent.txt"
    index = tmp_path / "nonexistent.txt.fts5.db"
    index.touch()
    with pytest.raises(FileNotFoundError):
        index_is_stale(source, index)


def test_fts_query_empty_raises():
    """Regression test: fts_query should raise ValueError for empty strings."""
    import pytest
    with pytest.raises(ValueError):
        fts_query("")
    with pytest.raises(ValueError):
        fts_query("   ")


import sqlite3
from os_search import build_names_index, ensure_index


def test_build_names_index_creates_db(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("# comment\n\nAlexei Navalny\nGazprom\n")
    index = tmp_path / "names.txt.fts5.db"
    build_names_index(source, index)
    assert index.exists()
    con = sqlite3.connect(index)
    names = [r[0] for r in con.execute("SELECT name FROM names").fetchall()]
    con.close()
    assert set(names) == {"Alexei Navalny", "Gazprom"}


def test_build_names_index_skips_comments(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("# this is a comment\nValidName\n  \n")
    index = tmp_path / "names.txt.fts5.db"
    build_names_index(source, index)
    con = sqlite3.connect(index)
    rows = con.execute("SELECT name FROM names").fetchall()
    con.close()
    assert len(rows) == 1 and rows[0][0] == "ValidName"


def test_ensure_index_builds_on_first_run(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("TestEntry\n")
    result = ensure_index(source, "names")
    assert result == tmp_path / "names.txt.fts5.db"
    assert result.exists()


def test_ensure_index_rebuilds_when_source_newer(tmp_path):
    import time
    source = tmp_path / "names.txt"
    source.write_text("OldEntry\n")
    index = ensure_index(source, "names")
    time.sleep(0.05)
    source.write_text("NewEntry\n")
    import os
    os.utime(source, None)
    # Force source to be newer than index
    os.utime(source, (index.stat().st_mtime + 1, index.stat().st_mtime + 1))
    ensure_index(source, "names")
    con = sqlite3.connect(index)
    rows = con.execute("SELECT name FROM names").fetchall()
    con.close()
    assert rows[0][0] == "NewEntry"


def test_ensure_index_reuses_fresh_index(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Entry\n")
    index = ensure_index(source, "names")
    mtime = index.stat().st_mtime
    ensure_index(source, "names")
    assert index.stat().st_mtime == mtime


from os_search import search_fts_names


def test_search_fts_names_hit(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Alexei Navalny\nGazprom\n")
    idx = ensure_index(source, "names")
    assert any("Navalny" in r for r in search_fts_names(idx, "Navalny"))


def test_search_fts_names_miss(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Alexei Navalny\n")
    idx = ensure_index(source, "names")
    assert search_fts_names(idx, "Putin") == []


def test_search_fts_names_multiword(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Alexei Navalny\nNavalny Foundation\n")
    idx = ensure_index(source, "names")
    assert any("Alexei Navalny" in r for r in search_fts_names(idx, "Alexei Navalny"))


def test_search_fts_names_case_insensitive(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Gazprom\n")
    idx = ensure_index(source, "names")
    assert len(search_fts_names(idx, "gazprom")) >= 1


def test_search_names_txt_fts_default(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Alexei Navalny\nGazprom\n")
    result = search_names_txt(source, ["Navalny"], rg_bin=None, use_fts=True)
    assert any("Navalny" in line for line in result["Navalny"])


def test_search_names_txt_no_fts_substring(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Alexei Navalny\nGazprom\n")
    result = search_names_txt(source, ["Nav"], rg_bin=None, use_fts=False)
    assert len(result["Nav"]) == 1  # substring "Nav" inside "Navalny"


import sqlite3 as _sqlite3_test
from os_search import build_csv_index, search_fts_csv


def test_build_csv_index_creates_db(tmp_path):
    source = tmp_path / "targets.simple.csv"
    source.write_text(
        "id,caption,schema,name,aliases,identifiers,sanctions,dataset,topics,first_seen,last_seen\n"
        "Q123,Alexei Navalny,Person,Alexei Navalny,Navalny,,EU FSF,eu_fsf,sanction,2022-03-01,2026-05-06\n"
    )
    index = tmp_path / "targets.simple.csv.fts5.db"
    build_csv_index(source, index)
    assert index.exists()
    con = _sqlite3_test.connect(index)
    rows = con.execute("SELECT id, caption FROM entities").fetchall()
    con.close()
    assert rows[0] == ("Q123", "Alexei Navalny")


def test_search_fts_csv_hit(simple_csv):
    idx = get_index_path(simple_csv)
    build_csv_index(simple_csv, idx)
    results = search_fts_csv(idx, "Navalny")
    assert len(results) == 1
    assert results[0]["id"] == "Q125"
    assert results[0]["schema"] == "Person"


def test_search_fts_csv_miss(simple_csv):
    idx = get_index_path(simple_csv)
    build_csv_index(simple_csv, idx)
    assert search_fts_csv(idx, "NonexistentEntity99999") == []


def test_search_fts_csv_deduplicates(simple_csv):
    idx = get_index_path(simple_csv)
    build_csv_index(simple_csv, idx)
    results = search_fts_csv(idx, "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy")
    assert [r["id"] for r in results].count("Q123") == 1


def test_search_csv_uses_fts_by_default(simple_csv):
    result = search_csv(simple_csv, ["Navalny"], rg_bin=None, use_fts=True)
    assert result["Navalny"][0]["id"] == "Q125"


def test_search_csv_no_fts_fallback(simple_csv):
    result = search_csv(simple_csv, ["Navalny"], rg_bin=None, use_fts=False)
    assert result["Navalny"][0]["id"] == "Q125"


def test_build_ftm_index_creates_db(ftm_json, tmp_path):
    index = tmp_path / "entities.ftm.json.fts5.db"
    build_ftm_index(ftm_json, index)
    assert index.exists()
    import sqlite3 as _sq
    con = _sq.connect(index)
    ids = [r[0] for r in con.execute("SELECT id FROM entities").fetchall()]
    con.close()
    assert set(ids) == {"Q200", "Q201", "Q202"}


def test_build_ftm_index_indexes_aliases(ftm_json, tmp_path):
    index = tmp_path / "entities.ftm.json.fts5.db"
    build_ftm_index(ftm_json, index)
    import sqlite3 as _sq
    con = _sq.connect(index)
    rows = con.execute(
        "SELECT id FROM entities WHERE entities MATCH 'HFC'"
    ).fetchall()
    con.close()
    assert ("Q202",) in rows


def test_search_fts_ftm_hit(ftm_json, tmp_path):
    index = tmp_path / "entities.ftm.json.fts5.db"
    build_ftm_index(ftm_json, index)
    results = search_fts_ftm(index, "Navalny")
    assert len(results) == 1 and results[0]["id"] == "Q201"


def test_search_fts_ftm_miss(ftm_json, tmp_path):
    index = tmp_path / "entities.ftm.json.fts5.db"
    build_ftm_index(ftm_json, index)
    assert search_fts_ftm(index, "NonexistentXYZ99999") == []


def test_search_target_uses_fts(ftm_json, tmp_path):
    shutil.copy(ftm_json, tmp_path / "entities.ftm.json")
    dataset = tmp_path / "entities.ftm.json"
    from os_search import search_target
    results = search_target("Navalny", dataset, schema_filter=None, rg_bin=None, use_fts=True)
    assert len(results) == 1 and results[0]["id"] == "Q201"


def test_search_target_schema_filter_with_fts(ftm_json, tmp_path):
    shutil.copy(ftm_json, tmp_path / "entities.ftm.json")
    dataset = tmp_path / "entities.ftm.json"
    from os_search import search_target
    assert search_target("Navalny", dataset, "Company", rg_bin=None, use_fts=True) == []
    assert search_target("Navalny", dataset, "Person", rg_bin=None, use_fts=True)[0]["id"] == "Q201"


def test_main_no_fts_uses_names_match_label(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--targets", "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy",
                    "--no-fts"])
    assert "NAMES MATCH" in r.stdout
    assert r.returncode == 0


def test_main_no_fts_still_returns_results(dataset_dir):
    r = run_script(["--dataset-dir", str(dataset_dir),
                    "--targets", "TUFXua1qzfCsFpcZEGXaU7oGFURqQ7RQpy",
                    "--no-fts"])
    assert r.returncode == 0
    assert "CryptoWallet" in r.stdout


from os_search import search_fuzzy


def test_search_fuzzy_names_finds_approximate(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Vladimir Putin\nVladimyr Pootin\nGazprom\n")
    idx = ensure_index(source, "names")
    fts_hits = set(search_fts_names(idx, "Vladimir Putin"))
    results = search_fuzzy(idx, "Vladimir Putin", threshold=70,
                           file_type="names", existing_ids=fts_hits)
    assert any(r["_fuzzy_match"] == "Vladimyr Pootin" for r in results)


def test_search_fuzzy_names_threshold(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Vladimir Putin\nXyzzy Completely Different\n")
    idx = ensure_index(source, "names")
    results = search_fuzzy(idx, "Vladimir Putin", threshold=95,
                           file_type="names", existing_ids=set())
    assert not any(r["_fuzzy_match"] == "Xyzzy Completely Different" for r in results)


def test_search_fuzzy_names_deduplicates(tmp_path):
    source = tmp_path / "names.txt"
    source.write_text("Vladimir Putin\n")
    idx = ensure_index(source, "names")
    results = search_fuzzy(idx, "Vladimir Putin", threshold=80,
                           file_type="names", existing_ids={"Vladimir Putin"})
    assert not any(r["_fuzzy_match"] == "Vladimir Putin" for r in results)


def test_search_fuzzy_csv_finds_approximate(simple_csv):
    idx = ensure_index(simple_csv, "csv")
    results = search_fuzzy(idx, "Aleksei Navalnyy", threshold=70,
                           file_type="csv", existing_ids=set())
    assert any("Navalny" in r.get("caption", "") for r in results)


def test_search_fuzzy_missing_rapidfuzz(tmp_path, monkeypatch, capsys):
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "rapidfuzz":
            raise ImportError("No module named 'rapidfuzz'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    source = tmp_path / "names.txt"
    source.write_text("Test\n")
    idx = ensure_index(source, "names")
    result = search_fuzzy(idx, "Test", 80, "names", existing_ids=set())
    assert result == []
    assert "pip install rapidfuzz" in capsys.readouterr().err
