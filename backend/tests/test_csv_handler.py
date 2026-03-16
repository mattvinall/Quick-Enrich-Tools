"""Tests for parse_csv_streaming in app.routers.upload."""

import textwrap

import pytest

from app.routers.upload import parse_csv_streaming


def _csv_bytes(content: str) -> bytes:
    return textwrap.dedent(content).encode("utf-8")


def _csv_bom_bytes(content: str) -> bytes:
    return textwrap.dedent(content).encode("utf-8-sig")


# ---------------------------------------------------------------------------
# test_parse_csv_basic
# ---------------------------------------------------------------------------

def test_parse_csv_basic() -> None:
    csv_content = """\
        company,location
        Stripe,San Francisco
        Shopify,Ottawa
    """
    rows = list(parse_csv_streaming(_csv_bytes(csv_content), "company", "location"))
    assert len(rows) == 2
    assert rows[0] == {"row_index": 0, "company_name": "Stripe", "location": "San Francisco"}
    assert rows[1] == {"row_index": 1, "company_name": "Shopify", "location": "Ottawa"}


# ---------------------------------------------------------------------------
# test_parse_csv_missing_location
# ---------------------------------------------------------------------------

def test_parse_csv_missing_location() -> None:
    """Rows where the location cell is empty should yield location=None."""
    csv_content = """\
        company,location
        Stripe,San Francisco
        Monzo,
    """
    rows = list(parse_csv_streaming(_csv_bytes(csv_content), "company", "location"))
    assert len(rows) == 2
    assert rows[0]["location"] == "San Francisco"
    assert rows[1]["location"] is None


# ---------------------------------------------------------------------------
# test_parse_csv_no_location_column
# ---------------------------------------------------------------------------

def test_parse_csv_no_location_column() -> None:
    """When location_col is None every row should have location=None."""
    csv_content = """\
        company
        Stripe
        Nubank
    """
    rows = list(parse_csv_streaming(_csv_bytes(csv_content), "company", None))
    assert len(rows) == 2
    for row in rows:
        assert row["location"] is None


# ---------------------------------------------------------------------------
# test_parse_csv_skips_empty_company
# ---------------------------------------------------------------------------

def test_parse_csv_skips_empty_company() -> None:
    """Rows with an empty company_name column must be skipped."""
    csv_content = """\
        company,location
        Stripe,San Francisco
        ,London
        Revolut,London
    """
    rows = list(parse_csv_streaming(_csv_bytes(csv_content), "company", "location"))
    assert len(rows) == 2
    company_names = [r["company_name"] for r in rows]
    assert "" not in company_names
    assert "Stripe" in company_names
    assert "Revolut" in company_names


# ---------------------------------------------------------------------------
# test_parse_csv_bom
# ---------------------------------------------------------------------------

def test_parse_csv_bom() -> None:
    """UTF-8-BOM encoded files must be parsed without a BOM prefix in headers."""
    csv_content = """\
        company,location
        Stripe,San Francisco
    """
    rows = list(parse_csv_streaming(_csv_bom_bytes(csv_content), "company", "location"))
    assert len(rows) == 1
    assert rows[0]["company_name"] == "Stripe"
    assert rows[0]["location"] == "San Francisco"
