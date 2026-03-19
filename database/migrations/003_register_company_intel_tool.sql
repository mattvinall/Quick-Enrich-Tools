INSERT INTO tools (id, slug, name, description, is_active)
VALUES (
  gen_random_uuid(),
  'company-intel',
  'Company/People Intel by URL',
  'Extract business intelligence from company websites. Upload URLs or company names to get industry, contacts, target market, and more.',
  true
)
ON CONFLICT (slug) DO NOTHING;
