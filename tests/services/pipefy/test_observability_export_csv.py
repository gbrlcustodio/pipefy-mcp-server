"""Unit tests for observability export CSV helpers."""

import io

import pytest
from openpyxl import Workbook

from pipefy_mcp.services.pipefy.observability_export_csv import (
    is_allowed_pipefy_export_download_url,
    xlsx_first_sheet_to_csv_limited,
)


def _minimal_xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Jobs"
    ws.append(["col_a", "col_b"])
    ws.append([1, 2])
    ws.append(["x", "y"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.unit
def test_is_allowed_pipefy_https_storage_url():
    url = "https://app.pipefy.com/storage/v1/signed/foo.xlsx?sig=1"
    assert is_allowed_pipefy_export_download_url(url) is True


@pytest.mark.unit
def test_is_allowed_rejects_http():
    assert is_allowed_pipefy_export_download_url("http://app.pipefy.com/x") is False


@pytest.mark.unit
def test_is_allowed_rejects_non_pipefy_host():
    assert is_allowed_pipefy_export_download_url("https://evil.com/x") is False


@pytest.mark.unit
def test_xlsx_first_sheet_to_csv():
    data = _minimal_xlsx_bytes()
    csv_text, rows, title, truncated = xlsx_first_sheet_to_csv_limited(
        data, max_output_chars=10_000
    )
    assert title == "Jobs"
    assert truncated is False
    assert rows == 3
    assert "col_a,col_b" in csv_text
    assert "1,2" in csv_text


@pytest.mark.unit
def test_xlsx_csv_truncated_by_char_cap():
    data = _minimal_xlsx_bytes()
    csv_text, rows, _title, truncated = xlsx_first_sheet_to_csv_limited(
        data, max_output_chars=5
    )
    assert truncated is True
    assert rows < 3
    assert "truncated" in csv_text.lower()


@pytest.mark.unit
def test_xlsx_first_sheet_rejects_zero_max_chars():
    with pytest.raises(ValueError, match="at least 1"):
        xlsx_first_sheet_to_csv_limited(b"", max_output_chars=0)
