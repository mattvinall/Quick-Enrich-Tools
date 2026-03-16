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
