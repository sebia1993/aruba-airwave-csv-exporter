"""CSV 구조/총건수 검증 및 기존 정상본 보호."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import io
import os
from pathlib import Path
import shutil
from uuid import uuid4


class CsvValidationError(Exception):
    pass


@dataclass(frozen=True)
class CsvInfo:
    rows: int
    headers: tuple[str, ...]
    size: int


@dataclass(frozen=True)
class SavedExport:
    path: Path
    rows: int
    size: int
    warning_drop: bool


def analyze(path: Path) -> CsvInfo:
    if not path.is_file() or path.stat().st_size == 0:
        raise CsvValidationError("비어 있는 다운로드 파일입니다.")
    data = path.read_bytes()
    prefix = data.lstrip()[:200].lower()
    if (b"<html" in prefix or b"<!doctype html" in prefix
            or prefix.startswith((b"{", b"["))):
        raise CsvValidationError("CSV 대신 HTML 또는 JSON 오류 페이지가 다운로드됐습니다.")
    text = None
    for encoding in (("utf-16",) if data.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-8-sig", "cp949")):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None or "\0" in text:
        raise CsvValidationError("지원하지 않는 CSV 인코딩/형식입니다.")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    try:
        records = csv.reader(io.StringIO(text, newline=""), dialect=dialect)
        header = next(records, ())
        if len(header) < 2 or not all(cell.strip() for cell in header):
            raise CsvValidationError("CSV 헤더가 누락되었거나 비정상입니다.")
        count = 0
        for row in records:
            if not any(cell.strip() for cell in row):
                continue
            if len(row) != len(header):
                raise CsvValidationError("CSV 데이터의 열 개수가 일치하지 않습니다.")
            count += 1
    except (csv.Error, UnicodeError) as exc:
        raise CsvValidationError("CSV를 해석할 수 없습니다.") from exc
    if count == 0:
        raise CsvValidationError("장비 데이터가 0건입니다.")
    return CsvInfo(count, tuple(header), len(data))


def store_export(
    staged: Path, destination: Path, *, expected_rows: int, drop_warning_percent: int = 10
) -> SavedExport:
    """실패/감소 경고 시 latest.csv를 덮지 않습니다. staged는 호출자가 정리합니다."""
    current = analyze(staged)
    if expected_rows < 1 or current.rows != expected_rows:
        raise CsvValidationError("화면 총건수와 CSV 장비 건수가 일치하지 않습니다.")
    destination.mkdir(parents=True, exist_ok=True)
    latest = destination / "latest.csv"
    previous = None
    if latest.exists():
        try:
            previous = analyze(latest)
        except CsvValidationError:
            raise CsvValidationError("기존 latest.csv가 손상되어 갱신을 중단했습니다.") from None
    warning = bool(
        previous and previous.rows > 0
        and current.rows < previous.rows
        and (previous.rows - current.rows) * 100
        >= previous.rows * drop_warning_percent
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    final = destination / ("AirWave_Devices_" + stamp + ".csv")
    os.replace(staged, final)
    if not warning:
        temporary = destination / (".latest-" + uuid4().hex + ".part")
        try:
            shutil.copyfile(final, temporary)
            os.replace(temporary, latest)
        finally:
            temporary.unlink(missing_ok=True)
    return SavedExport(final, current.rows, current.size, warning)
