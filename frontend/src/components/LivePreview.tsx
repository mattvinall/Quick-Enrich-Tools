'use client';

import { useState, useEffect, useRef } from 'react';

interface PreviewRow {
  index: number;
  company_name: string;
  location?: string;
  website?: string;
  status: string;
}

interface LivePreviewProps {
  jobId: string;
  token: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const TERMINAL_STATUSES = new Set(['completed', 'failed']);

function statusColor(status: string): string {
  if (['normalized', 'enriched'].includes(status)) return 'text-green-600';
  if (['not_found', 'blocked', 'failed'].includes(status)) return 'text-red-500';
  return 'text-gray-500';
}

export default function LivePreview({ jobId, token }: LivePreviewProps) {
  const [rows, setRows] = useState<PreviewRow[]>([]);
  const [done, setDone] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    async function fetchPreview() {
      try {
        const res = await fetch(
          `${API_URL}/api/v1/jobs/${jobId}/preview?limit=50`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (!res.ok) return;

        const data: { rows: PreviewRow[]; status: string } = await res.json();
        setRows(data.rows ?? []);

        if (TERMINAL_STATUSES.has(data.status)) {
          setDone(true);
          if (intervalRef.current !== null) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }
      } catch {
        // network error — keep polling
      }
    }

    fetchPreview();
    intervalRef.current = setInterval(fetchPreview, 5000);

    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [jobId, token]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-primary">
          Live Preview
        </h3>
        {done && (
          <span className="text-xs text-green-600 font-medium">Complete</span>
        )}
      </div>

      <div className="border border-border rounded-lg overflow-hidden">
        {rows.length === 0 ? (
          <div className="flex items-center justify-center h-20 text-sm text-text-secondary">
            Waiting for results...
          </div>
        ) : (
          <div className="overflow-y-auto max-h-80">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0 z-10">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-text-secondary w-10">
                    #
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-text-secondary">
                    Company
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-text-secondary">
                    Location
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-text-secondary">
                    Website
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-text-secondary">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border bg-white">
                {rows.map((row) => (
                  <tr key={row.index} className="hover:bg-gray-50 transition-colors">
                    <td className="px-3 py-2 text-text-secondary tabular-nums">
                      {row.index}
                    </td>
                    <td className="px-3 py-2 text-text-primary font-medium truncate max-w-[160px]">
                      {row.company_name}
                    </td>
                    <td className="px-3 py-2 text-text-secondary truncate max-w-[120px]">
                      {row.location ?? '—'}
                    </td>
                    <td className="px-3 py-2 max-w-[180px]">
                      {row.website ? (
                        <a
                          href={row.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary hover:underline truncate block"
                        >
                          {row.website}
                        </a>
                      ) : (
                        <span className="text-text-secondary">—</span>
                      )}
                    </td>
                    <td className={`px-3 py-2 font-medium ${statusColor(row.status)}`}>
                      {row.status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
