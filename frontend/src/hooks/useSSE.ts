'use client';

import { useState, useEffect, useRef } from 'react';

export interface JobProgress {
  status: string;
  processed_rows: number;
  total_rows: number;
  current_phase: string | null;
  phase_progress: Record<string, { done: number; total: number }>;
  found_count: number;
  enriched_count?: number;
  error?: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const TERMINAL_STATUSES = new Set(['completed', 'failed']);

export function useSSE(
  jobId: string | null,
  token: string | null,
): { progress: JobProgress | null; connected: boolean; authError: boolean } {
  const [progress, setProgress] = useState<JobProgress | null>(null);
  const [connected, setConnected] = useState(false);
  const [authError, setAuthError] = useState(false);

  const eventSourceRef = useRef<EventSource | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!jobId || !token) return;
    setAuthError(false);

    function isTerminal(p: JobProgress): boolean {
      return TERMINAL_STATUSES.has(p.status);
    }

    function stopPolling() {
      if (pollIntervalRef.current !== null) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    }

    function startPolling() {
      setConnected(false);

      async function poll() {
        try {
          const res = await fetch(`${API_URL}/api/v1/jobs/${jobId}`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (res.status === 401 || res.status === 403) {
            stopPolling();
            setAuthError(true);
            return;
          }
          if (!res.ok) return;
          const raw = await res.json();
          // Transform GET /jobs response to match SSE JobProgress shape
          const data: JobProgress = {
            status: raw.status,
            processed_rows: raw.processed_rows ?? 0,
            total_rows: raw.total_rows ?? 0,
            current_phase: raw.current_phase ?? null,
            phase_progress: raw.current_phase && raw.phase_progress != null
              ? { [raw.current_phase]: { done: Math.round(raw.phase_progress * (raw.total_rows ?? 0)), total: raw.total_rows ?? 0 } }
              : {},
            found_count: raw.processed_rows ?? 0,
            enriched_count: 0,
            error: raw.error_message,
          };
          setProgress(data);
          if (isTerminal(data)) {
            stopPolling();
          }
        } catch {
          // network error — keep polling
        }
      }

      poll();
      pollIntervalRef.current = setInterval(poll, 3000);
    }

    function closeEventSource() {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    }

    const es = new EventSource(
      `${API_URL}/api/v1/jobs/${jobId}/sse?token=${encodeURIComponent(token)}`,
    );
    eventSourceRef.current = es;

    es.onopen = () => {
      setConnected(true);
    };

    es.addEventListener('message', (e: MessageEvent) => {
      try {
        const data: JobProgress = JSON.parse(e.data as string);
        setProgress(data);
        if (isTerminal(data)) {
          closeEventSource();
          setConnected(false);
        }
      } catch {
        // malformed message — ignore
      }
    });

    es.onerror = () => {
      closeEventSource();
      setConnected(false);
      startPolling();
    };

    return () => {
      closeEventSource();
      stopPolling();
    };
  }, [jobId, token]);

  return { progress, connected, authError };
}
