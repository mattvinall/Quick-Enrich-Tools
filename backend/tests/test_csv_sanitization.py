"""Tests for CSV-injection sanitization in intel.py and g2.py row builders.

Each contact cell that could be chosen by an attacker (phone, mobile,
linkedin_url, and text fields) must be passed through _sanitize_csv so that
values beginning with =, +, -, @, \\t, or \\r are prefixed with a leading
apostrophe. Without this, Excel/Numbers will execute formulas on CSV open.
"""

from types import SimpleNamespace

from app.routers.g2 import _extract_g2_rows, _sanitize_csv as _sanitize_csv_g2
from app.routers.intel import _extract_intel_rows, _sanitize_csv as _sanitize_csv_intel


# ---------------------------------------------------------------------------
# _sanitize_csv primitive
# ---------------------------------------------------------------------------

def test_sanitize_csv_prefixes_formula_chars() -> None:
    for prefix in ("=", "+", "-", "@", "\t", "\r"):
        value = f"{prefix}cmd|'/C calc'!A0"
        assert _sanitize_csv_intel(value).startswith("'"), f"intel: {prefix!r} not sanitized"
        assert _sanitize_csv_g2(value).startswith("'"), f"g2: {prefix!r} not sanitized"


def test_sanitize_csv_passes_safe_values_through() -> None:
    assert _sanitize_csv_intel("Acme Inc") == "Acme Inc"
    assert _sanitize_csv_g2("+15551234") == "'+15551234"  # + must trigger
    assert _sanitize_csv_intel("") == ""


# ---------------------------------------------------------------------------
# intel.py row builder
# ---------------------------------------------------------------------------

def _make_result(contacts: list[dict], *, normalized_domain: str = "acme.com") -> SimpleNamespace:
    """Build an object that quacks like JobResult for the row builders."""
    return SimpleNamespace(
        input_data={"input": "acme.com", "g2_category": "crm", "g2_url": "https://g2.com/crm", "g2_rating": 4.5, "g2_review_count": 100},
        extracted_data={},
        normalized_domain=normalized_domain,
        raw_domain=None,
        contacts=contacts,
        status="success",
    )


def test_intel_row_sanitizes_phone_and_linkedin() -> None:
    contact = {
        "title": "CEO",
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane@acme.com",
        "phone": "=cmd|'/C calc'!A0",
        "linkedin_url": "+123-HACK",
    }
    result = _make_result([contact])
    rows = _extract_intel_rows(result, options={"company_people": True})
    assert len(rows) == 1
    row = rows[0]
    # Last two cells are phone and linkedin_url
    phone_cell = row[-2]
    linkedin_cell = row[-1]
    assert phone_cell.startswith("'"), f"phone not sanitized: {phone_cell!r}"
    assert linkedin_cell.startswith("'"), f"linkedin not sanitized: {linkedin_cell!r}"
    assert phone_cell == "'=cmd|'/C calc'!A0"
    assert linkedin_cell == "'+123-HACK"


def test_intel_row_benign_phone_unchanged() -> None:
    contact = {
        "title": "CEO",
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane@acme.com",
        "phone": "5551234567",
        "linkedin_url": "https://linkedin.com/in/jane",
    }
    result = _make_result([contact])
    rows = _extract_intel_rows(result, options={"company_people": True})
    row = rows[0]
    assert row[-2] == "5551234567"
    assert row[-1] == "https://linkedin.com/in/jane"


# ---------------------------------------------------------------------------
# g2.py row builder
# ---------------------------------------------------------------------------

def test_g2_row_sanitizes_phone_mobile_and_linkedin() -> None:
    contact = {
        "title": "CEO",
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane@acme.com",
        "phone": "=cmd|'/C calc'!A0",
        "mobile": "@dangerous",
        "linkedin_url": "+123-HACK",
    }
    result = _make_result([contact])
    rows = _extract_g2_rows(result, options={"company_people": True})
    assert len(rows) == 1
    row = rows[0]
    # Last three cells are phone, mobile, linkedin_url
    phone_cell = row[-3]
    mobile_cell = row[-2]
    linkedin_cell = row[-1]
    assert phone_cell.startswith("'"), f"phone not sanitized: {phone_cell!r}"
    assert mobile_cell.startswith("'"), f"mobile not sanitized: {mobile_cell!r}"
    assert linkedin_cell.startswith("'"), f"linkedin not sanitized: {linkedin_cell!r}"
    assert phone_cell == "'=cmd|'/C calc'!A0"
    assert mobile_cell == "'@dangerous"
    assert linkedin_cell == "'+123-HACK"


def test_g2_row_benign_values_unchanged() -> None:
    contact = {
        "title": "CEO",
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane@acme.com",
        "phone": "5551234567",
        "mobile": "5559876543",
        "linkedin_url": "https://linkedin.com/in/jane",
    }
    result = _make_result([contact])
    rows = _extract_g2_rows(result, options={"company_people": True})
    row = rows[0]
    assert row[-3] == "5551234567"
    assert row[-2] == "5559876543"
    assert row[-1] == "https://linkedin.com/in/jane"
