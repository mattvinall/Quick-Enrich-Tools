import pytest


@pytest.fixture
def sample_csv_rows() -> list[dict[str, str]]:
    """Five representative company/location rows for pipeline tests."""
    return [
        {"company": "Stripe", "location": "San Francisco, CA"},
        {"company": "Shopify", "location": "Ottawa, ON, Canada"},
        {"company": "Monzo", "location": "London, UK"},
        {"company": "Nubank", "location": "São Paulo, Brazil"},
        {"company": "Revolut", "location": "London, UK"},
    ]


@pytest.fixture
def blocked_domains() -> list[str]:
    """Common free / disposable e-mail domains that should be rejected."""
    return [
        "gmail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "icloud.com",
        "aol.com",
        "protonmail.com",
        "mailinator.com",
        "guerrillamail.com",
        "tempmail.com",
        "throwaway.email",
        "sharklasers.com",
        "yopmail.com",
    ]
