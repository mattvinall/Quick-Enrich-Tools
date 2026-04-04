-- Register People Intel tool
INSERT INTO tools (id, slug, name, description, is_active)
VALUES (
    gen_random_uuid(),
    'people-intel',
    'People Intel by Name',
    'Upload names and company names to find LinkedIn profiles and extract business intelligence.',
    true
)
ON CONFLICT (slug) DO NOTHING;

-- Add linkedin_searching status to jobs check constraint
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
        'g2_scraping',
        -- Product 7 (People Intel)
        'linkedin_searching'
    )
);
