from pathlib import Path

import pytest

from airwave_csv.csv_store import CsvValidationError, analyze, store_export


def write_csv(path: Path, n: int, encoding: str = "utf-8"):
    rows = ["Name,Model"] + [f"device-{i},AP-535" for i in range(n)]
    path.write_bytes(("\n".join(rows) + "\n").encode(encoding))


def test_save_keeps_original_content_and_latest(tmp_path):
    staged = tmp_path / "dl.part"
    write_csv(staged, 3)
    original = staged.read_bytes()
    saved = store_export(staged, tmp_path, expected_rows=3)
    assert saved.rows == 3
    assert saved.size == len(original)
    assert saved.path.read_bytes() == original
    assert (tmp_path / "latest.csv").read_bytes() == original
    assert not staged.exists()
    assert not saved.warning_drop


def test_bad_csv_is_rejected_and_latest_kept(tmp_path):
    latest = tmp_path / "latest.csv"
    write_csv(latest, 2)
    original = latest.read_bytes()
    bad = tmp_path / "dl.part"
    bad.write_text("<!doctype html><html>Login</html>", encoding="utf-8")
    with pytest.raises(CsvValidationError):
        store_export(bad, tmp_path, expected_rows=2)
    assert latest.read_bytes() == original
    assert bad.exists()


def test_zero_rows_rejected(tmp_path):
    file = tmp_path / "empty.csv"
    file.write_text("Name,Model\n", encoding="utf-8")
    with pytest.raises(CsvValidationError):
        analyze(file)


def test_header_malformed_rejected(tmp_path):
    file = tmp_path / "bad.csv"
    file.write_text("Name,Model\nap1\n", encoding="utf-8")
    with pytest.raises(CsvValidationError):
        analyze(file)


def test_expected_count_mismatch_prevents_commit(tmp_path):
    file = tmp_path / "dl.part"
    write_csv(file, 2)
    with pytest.raises(CsvValidationError):
        store_export(file, tmp_path, expected_rows=3)
    assert not (tmp_path / "latest.csv").exists()


def test_large_drop_preserves_last_good(tmp_path):
    latest = tmp_path / "latest.csv"
    write_csv(latest, 10)
    snapshot = latest.read_bytes()
    file = tmp_path / "dl.part"
    write_csv(file, 5)
    saved = store_export(file, tmp_path, expected_rows=5, drop_warning_percent=10)
    assert saved.warning_drop
    assert saved.path.exists()
    assert latest.read_bytes() == snapshot


def test_korean_windows_encoding(tmp_path):
    file = tmp_path / "cp949.csv"
    file.write_bytes("이름,모델\n장비1,AP-535\n".encode("cp949"))
    assert analyze(file).rows == 1


def test_multiline_quoted_cell(tmp_path):
    file = tmp_path / "quoted.csv"
    file.write_text('Name,Note\nap1,"line1\nline2"\n', encoding="utf-8")
    assert analyze(file).rows == 1
