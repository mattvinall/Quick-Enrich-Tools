# Company + Location Website Finder

Find the exact company website by matching name and location. Upload a CSV
with company names plus their city or state, and the pipeline returns the
verified domain for each row. Adding location dramatically improves match
accuracy versus name-only lookups.

## User flow

1. Drag-and-drop a CSV onto the upload zone.
2. Map the `company_name` and `location` columns (auto-detected from headers).
3. Confirm email for delivery.
4. Submit; live SSE progress updates as rows process.
5. Download the result CSV (or receive it via email if Resend is configured).

## Backend

- **Route:** `/tools/company-location-finder`
- **Router:** `backend/app/routers/upload.py`
- **Pipeline worker:** `backend/app/workers/pipeline.py`
- **Discovery phase (Phase 0):** none — input is the uploaded CSV.
- **Services touched:** Serper

## Notable design decisions

- The original Product 1 (`website-finder`, now legacy) had no location column. This tool exists because matching by name alone produced too many false positives for companies with common names; adding city/state is a cheap, large accuracy win.
- Backend pays for the Serper key (set in `backend/.env`); users do not need their own.

## Key files

- Frontend page: `frontend/src/app/tools/company-location-finder/page.tsx`
- Backend router: `backend/app/routers/upload.py`
- Pipeline worker: `backend/app/workers/pipeline.py`
- Search service: `backend/app/services/serper.py`
