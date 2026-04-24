-- Add missing pipeline statuses for Maps Intel and Funded Companies tools.
--
-- Maps Intel sets job.status = 'maps_searching' during its Phase 0 Google Maps
-- discovery, and Funded Companies sets 'funding_discovering' during its news
-- discovery. Neither value was added to jobs_status_check, so UPDATEs from
-- these pipelines failed with CheckViolationError and jobs hung in 'pending'
-- with no error_message (the pipeline crash happened in a background task).
--
-- Observed symptom: maps and funding jobs stuck at status='pending',
-- started_at=NULL. Railway logs show:
--   CheckViolationError: new row for relation "jobs" violates check constraint "jobs_status_check"
--   ...status='maps_searching'
--
-- Fix: extend the constraint with both missing statuses. Includes all values
-- from migration 004 plus the tool-specific ones already shipped (g2_scraping,
-- linkedin_searching) so this constraint is the single source of truth.

ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;

ALTER TABLE jobs ADD CONSTRAINT jobs_status_check CHECK (
    status IN (
        -- Shared across all pipelines
        'pending', 'completed', 'failed',
        -- Product 2 (Company Location Finder)
        'parsing', 'searching', 'verifying', 'normalizing', 'enriching', 'delivering',
        -- Product 3 (Company / People Intel)
        'resolving', 'crawling', 'extracting', 'crawled', 'extracted',
        -- Product 4 (G2 Category -> Intel)
        'g2_scraping',
        -- Product 5 (Google Maps -> Intel)
        'maps_searching',
        -- Product 6 (Funded Companies Today)
        'funding_discovering',
        -- People search (LinkedIn)
        'linkedin_searching'
    )
);
