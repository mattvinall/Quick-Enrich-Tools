-- Register G2 Intel tool
INSERT INTO tools (id, slug, name, description, is_active)
VALUES (
    gen_random_uuid(),
    'g2-intel',
    'G2 Category to Company Intel',
    'Select G2 software categories to discover companies and extract business intelligence.',
    true
);

-- Add g2_scraping status to jobs check constraint
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;

ALTER TABLE jobs ADD CONSTRAINT jobs_status_check CHECK (
    status IN (
        -- Shared
        'pending', 'completed', 'failed',
        -- Product 2 (Company Location Finder)
        'parsing', 'searching', 'verifying', 'normalizing', 'enriching', 'delivering',
        -- Product 3 (Company Intel)
        'resolving', 'crawling', 'extracting', 'crawled', 'extracted',
        -- Product 4 (G2 Intel)
        'g2_scraping'
    )
);
