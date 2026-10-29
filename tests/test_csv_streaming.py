"""CSV 파일 내용·구조는 동일하게 검증하되 전체 바이트를 메모리에 올리지 않습니다."""

from __future__ import annotations

from pathlib import Path

import pytest

from airwave_csv.csv_store import CsvValidationError, analyze, store_export


def test_large_csv_verification_does_not_call_read_bytes(tmp_path, monkeypatch):
    path = tmp_path / "large.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write("Name,Model\n")
        for index in range(25000):
            stream.write(f"ap-{index},AP-535\n")
    original = Path.read_bytes

    def fail_full_read(self):
        if self == path:
            raise AssertionError("CSV 전체 파일을 read_bytes()로 메모리에 올리면 안 됩니다.")
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", fail_full_read)
    info = analyze(path)
    assert info.rows == 25000
    assert info.headers == ("Name", "Model")
    assert info.size == path.stat().st_size


@pytest.mark.parametrize("encoding", ["utf-8-sig", "cp949", "utf-16"])
def test_csv_streaming_preserves_korean_encodings(tmp_path, encoding):
    path = tmp_path / (encoding + ".csv")
    path.write_bytes("이름,모델\n장비-1,AP-535\n".encode(encoding))
    info = analyze(path)
    assert info.rows == 1
    assert info.headers == ("이름", "모델")


def test_csv_streaming_falls_back_on_late_cp949_character(tmp_path):
    path = tmp_path / "late.csv"
    path.write_bytes(("Name,Model\n" + "ap1,AP-535\n" * 5000 +
                      "장비,AP-535\n").encode("cp949"))
    info = analyze(path)
    assert info.rows == 5001


def test_multiline_quote_and_bad_column_count_remain_unchanged(tmp_path):
    good = tmp_path / "quoted.csv"
    good.write_text('Name,Note\nap1,"line one\nline two"\n', encoding="utf-8")
    assert analyze(good).rows == 1
    bad = tmp_path / "bad.csv"
    bad.write_text("Name,Model\nap1,AP-535\nap2\n", encoding="utf-8")
    with pytest.raises(CsvValidationError):
        analyze(bad)


def test_csv_export_keeps_downloaded_bytes_original(tmp_path):
    source = tmp_path / "download.part"
    raw = "이름,모델\n장비-1,AP-535\n".encode("cp949")
    source.write_bytes(raw)
    export = store_export(source, tmp_path / "out", expected_rows=1)
    assert export.path.read_bytes() == raw
    assert (tmp_path / "out" / "latest.csv").read_bytes() == raw
