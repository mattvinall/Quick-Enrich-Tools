const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

async function fetchAPI<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let message = `Request failed with status ${res.status}`;
    try {
      const body = await res.json() as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // ignore parse errors — use default message
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export interface EmailCaptureResponse {
  email_capture_id: string;
  token: string;
  message: string;
}

export function captureEmail(
  email: string,
  toolSlug: string,
  source?: string,
): Promise<EmailCaptureResponse> {
  return fetchAPI<EmailCaptureResponse>(`${API_URL}/api/v1/email-capture`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, tool_slug: toolSlug, source }),
  });
}

export interface UploadConfig {
  companyColumn: string;
  locationColumn: string;
  emailCaptureId: string;
  enrichContacts: boolean;
  jobTitles: string[];
  maxContacts: number;
}

export interface UploadResponse {
  job_id: string;
  total_rows: number;
  token: string;
}

export function uploadCSV(
  file: File,
  config: UploadConfig,
  token: string,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file);
  form.append('company_column', config.companyColumn);
  form.append('location_column', config.locationColumn);
  form.append('email_capture_id', config.emailCaptureId);
  form.append('enrich_contacts', String(config.enrichContacts));
  form.append('job_titles', JSON.stringify(config.jobTitles));
  form.append('max_contacts', String(config.maxContacts));

  return fetchAPI<UploadResponse>(`${API_URL}/api/v1/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
}

export interface JobStatusResponse {
  status: string;
  processed_rows: number;
  total_rows: number;
  current_phase: string | null;
  phase_progress: Record<string, { done: number; total: number }>;
  found_count: number;
  error?: string;
}

export function getJobStatus(
  jobId: string,
  token: string,
): Promise<JobStatusResponse> {
  return fetchAPI<JobStatusResponse>(`${API_URL}/api/v1/jobs/${jobId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getDownloadUrl(jobId: string, token: string): string {
  return `${API_URL}/api/v1/download/${jobId}?token=${encodeURIComponent(token)}`;
}

export interface ClayPushResponse {
  pushed_count: number;
}

export function pushToClay(
  jobId: string,
  webhookUrl: string,
  token: string,
): Promise<ClayPushResponse> {
  return fetchAPI<ClayPushResponse>(`${API_URL}/api/v1/clay-push/${jobId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ webhook_url: webhookUrl }),
  });
}

export interface ExtractionOptions {
  industry_description: boolean;
  target_market: boolean;
  company_people: boolean;
  homepage_raw_text: boolean;
}

export interface ExtractRequest {
  lines: string[];
  options: ExtractionOptions;
  quickenrich_api_key: string;
  serper_api_key: string;
  job_titles: string[];
  max_contacts: number;
}

export interface ExtractResponse {
  job_id: string;
  total_rows: number;
  token: string;
}

export function submitExtraction(
  body: ExtractRequest,
  token: string,
): Promise<ExtractResponse> {
  return fetchAPI<ExtractResponse>(`${API_URL}/api/v1/intel/extract`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
}

export function getIntelDownloadUrl(jobId: string, token: string): string {
  return `${API_URL}/api/v1/intel/download/${jobId}?token=${encodeURIComponent(token)}`;
}

// ── G2 Intel ────────────────────────────────────────────────────────

export interface G2Category {
  slug: string;
  name: string;
  parent: string;
  estimated_products: number;
}

export interface G2CategoriesResponse {
  categories: G2Category[];
  parents: string[];
  total: number;
}

export function getG2Categories(
  search?: string,
  parent?: string,
): Promise<G2CategoriesResponse> {
  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (parent) params.set('parent', parent);
  const qs = params.toString();
  return fetchAPI<G2CategoriesResponse>(
    `${API_URL}/api/v1/g2/categories${qs ? `?${qs}` : ''}`,
  );
}

export interface G2ExtractRequest {
  categories: string[];
  max_per_category: number;
  options: ExtractionOptions;
  quickenrich_api_key: string;
  serper_api_key: string;
  job_titles: string[];
  max_contacts: number;
}

export function submitG2Extraction(
  body: G2ExtractRequest,
  token: string,
): Promise<ExtractResponse> {
  return fetchAPI<ExtractResponse>(`${API_URL}/api/v1/g2/extract`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
}

export function getG2DownloadUrl(jobId: string, token: string): string {
  return `${API_URL}/api/v1/g2/download/${jobId}?token=${encodeURIComponent(token)}`;
}

// ── Maps Intel ─────────────────────────────────────────────────────

export interface MapsSearchItem {
  search_term: string;
  location: string;
}

export interface MapsExtractRequest {
  // Interactive mode (same location for all terms)
  search_terms?: string[];
  location?: string;
  // CSV mode (per-row locations) — overrides search_terms + location if present
  searches?: MapsSearchItem[];
  // Shared config
  max_per_search: number;
  options: ExtractionOptions;
  quickenrich_api_key: string;
  job_titles: string[];
  max_contacts: number;
}

export interface MapsExtractResponse {
  job_id: string;
  total_searches: number;
  token: string;
}

export function submitMapsExtraction(
  body: MapsExtractRequest,
  token: string,
): Promise<MapsExtractResponse> {
  return fetchAPI<MapsExtractResponse>(`${API_URL}/api/v1/maps/extract`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
}

export function getMapsDownloadUrl(jobId: string, token: string): string {
  return `${API_URL}/api/v1/maps/download/${jobId}?token=${encodeURIComponent(token)}`;
}

// ── Funding Intel ──────────────────────────────────────────────────

export interface FundingCompany {
  company_name: string;
  funding_amount: string | null;
  funding_round: string;
  lead_investor: string | null;
  description_snippet: string | null;
  source_url: string;
  source_name: string;
}

export interface FundingDiscoverResponse {
  companies: FundingCompany[];
  total: number;
  cached_at?: string;
}

export function discoverFunding(hours: number = 24): Promise<FundingDiscoverResponse> {
  return fetchAPI<FundingDiscoverResponse>(
    `${API_URL}/api/v1/funding/discover?hours=${hours}`,
  );
}

export interface FundingExtractRequest {
  companies: FundingCompany[];
  options: ExtractionOptions;
  quickenrich_api_key: string;
  job_titles: string[];
  max_contacts: number;
}

export function submitFundingExtraction(
  body: FundingExtractRequest,
  token: string,
): Promise<ExtractResponse> {
  return fetchAPI<ExtractResponse>(`${API_URL}/api/v1/funding/extract`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
}

export function getFundingDownloadUrl(jobId: string, token: string): string {
  return `${API_URL}/api/v1/funding/download/${jobId}?token=${encodeURIComponent(token)}`;
}
