import asyncio
import logging

import resend

from app.config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY = 2.0


async def send_results_email(to_email: str, download_url: str, job_stats: dict[str, int]) -> None:
    """Send a branded results email via Resend with retry.

    Args:
        to_email: Recipient email address.
        download_url: Pre-signed URL pointing to the output CSV.
        job_stats: Dict containing total_rows, websites_found keys.
    """
    if not settings.resend_api_key:
        logger.error("RESEND_API_KEY not configured — skipping email to %s", to_email)
        return

    resend.api_key = settings.resend_api_key

    total: int = job_stats.get("total_rows", 0)
    found: int = job_stats.get("websites_found", 0)
    contacts: int = job_stats.get("contacts_enriched", 0)
    match_rate: str = f"{round(found / total * 100)}%" if total else "0%"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Your QuickEnrich Results</title>
</head>
<body style="margin:0;padding:0;background:#f4f7fb;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f7fb;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="background:#2b7ec8;padding:32px 40px;">
              <h1 style="margin:0;color:#ffffff;font-size:24px;font-weight:700;letter-spacing:-0.5px;">
                QuickEnrich Results Ready
              </h1>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 40px;">
              <p style="margin:0 0 24px;color:#374151;font-size:15px;line-height:1.6;">
                Your enrichment job has finished. Here's a summary of what we found:
              </p>

              <!-- Stats -->
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="background:#f0f7ff;border-radius:6px;margin-bottom:32px;">
                <tr>
                  <td style="padding:20px 24px;">
                    <table width="100%" cellpadding="0" cellspacing="0">
                      <tr>
                        <td style="padding:6px 0;">
                          <span style="color:#6b7280;font-size:13px;">Total rows</span><br/>
                          <strong style="color:#111827;font-size:22px;">{total:,}</strong>
                        </td>
                        <td style="padding:6px 0;">
                          <span style="color:#6b7280;font-size:13px;">Websites found</span><br/>
                          <strong style="color:#111827;font-size:22px;">{found:,}</strong>
                        </td>
                        <td style="padding:6px 0;">
                          <span style="color:#6b7280;font-size:13px;">Match rate</span><br/>
                          <strong style="color:#2b7ec8;font-size:22px;">{match_rate}</strong>
                        </td>
                        <td style="padding:6px 0;">
                          <span style="color:#6b7280;font-size:13px;">Contacts found</span><br/>
                          <strong style="color:#111827;font-size:22px;">{contacts:,}</strong>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Download button -->
              <table cellpadding="0" cellspacing="0">
                <tr>
                  <td style="border-radius:6px;background:#2b7ec8;">
                    <a href="{download_url}"
                       style="display:inline-block;padding:14px 32px;color:#ffffff;font-size:15px;
                              font-weight:600;text-decoration:none;border-radius:6px;">
                      Download CSV
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#f9fafb;padding:24px 40px;border-top:1px solid #e5e7eb;">
              <p style="margin:0 0 6px;color:#9ca3af;font-size:12px;line-height:1.5;">
                This download link expires in 7 days.
              </p>
              <p style="margin:0;color:#9ca3af;font-size:12px;line-height:1.5;">
                Need more enrichments?
                <a href="https://quickenrich.io"
                   style="color:#2b7ec8;text-decoration:none;">Visit quickenrich.io</a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    params: resend.Emails.SendParams = {
        "from": "QuickEnrich Tools <noreply@pipeline.help>",
        "to": [to_email],
        "subject": f"Your QuickEnrich Results — {found}/{total} websites found",
        "html": html,
    }

    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            await asyncio.to_thread(resend.Emails.send, params)
            logger.info("Results email sent to %s (found=%d total=%d)", to_email, found, total)
            return
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                delay = _BASE_DELAY * (2 ** attempt)
                logger.warning("Email send attempt %d failed, retrying in %.0fs: %s", attempt + 1, delay, exc)
                await asyncio.sleep(delay)

    logger.error("Email delivery failed after %d attempts to %s: %s", _MAX_RETRIES, to_email, last_exc)
