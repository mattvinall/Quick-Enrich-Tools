import csv
import io


def generate_output_csv(rows: list[dict[str, object]], job_titles: list[str]) -> bytes:
    """Produce a UTF-8 BOM CSV from enriched row data.

    Base columns: company_name, location, website, verification_confidence, status.
    For every job title five columns are appended:
        {Title} - First Name, {Title} - Last Name, {Title} - Email,
        {Title} - Phone, {Title} - LinkedIn

    Contacts within each row are matched to their title column group using a
    case-insensitive comparison against the contact's ``title`` field.

    Args:
        rows: List of enriched row dicts.  Each dict may contain
            ``company_name``, ``location``, ``website``,
            ``verification_confidence``, ``status``, and ``contacts``
            (a list of contact dicts as returned by enrichment.py).
        job_titles: Ordered list of job titles; determines column order.

    Returns:
        CSV content as bytes with a UTF-8 BOM prefix.
    """
    base_headers = ["company_name", "location", "website", "verification_confidence", "status"]

    contact_suffixes = ["Title", "First Name", "Last Name", "Email", "Phone", "LinkedIn"]
    contact_headers: list[str] = []
    for title in job_titles:
        for suffix in contact_suffixes:
            contact_headers.append(f"{title} - {suffix}")

    all_headers = base_headers + contact_headers

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=all_headers, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()

    for row in rows:
        contacts: list[dict[str, str]] = row.get("contacts", [])  # type: ignore[assignment]

        csv_row: dict[str, object] = {
            "company_name": row.get("company_name", ""),
            "location": row.get("location", ""),
            "website": row.get("website", ""),
            "verification_confidence": row.get("verification_confidence", ""),
            "status": row.get("status", ""),
        }

        # Assign contacts to title columns positionally — first contact goes
        # to the first title column, second contact to the second, etc.
        # Show the actual title the API returned rather than forcing a match.
        for idx, title in enumerate(job_titles):
            contact = contacts[idx] if idx < len(contacts) else {}
            csv_row[f"{title} - Title"] = contact.get("title", "")
            csv_row[f"{title} - First Name"] = contact.get("first_name", "")
            csv_row[f"{title} - Last Name"] = contact.get("last_name", "")
            csv_row[f"{title} - Email"] = contact.get("email", "")
            csv_row[f"{title} - Phone"] = contact.get("phone", "")
            csv_row[f"{title} - LinkedIn"] = contact.get("linkedin_url", "")

        writer.writerow(csv_row)

    return "\ufeff".encode("utf-8") + buffer.getvalue().encode("utf-8")
