-- Update jobs status check constraint to support Product 3 statuses
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;

ALTER TABLE jobs ADD CONSTRAINT jobs_status_check CHECK (
    status IN (
        -- Shared
        'pending', 'completed', 'failed',
        -- Product 2 (Company Location Finder)
        'parsing', 'searching', 'verifying', 'normalizing', 'enriching', 'delivering',
        -- Product 3 (Company Intel)
        'resolving', 'crawling', 'extracting', 'crawled', 'extracted'
    )
);
