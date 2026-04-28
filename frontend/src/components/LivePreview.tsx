'use client';

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, TableProperties } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface PreviewRow {
  index: number;
  company_name: string;
  location?: string;
  domain?: string;
  website?: string;
  status: string;
}

interface ApiPreviewResponse {
  rows: PreviewRow[];
  status: string;
}

interface LivePreviewProps {
  jobId: string;
  token: string;
  isProcessing: boolean;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const TERMINAL_STATUSES = new Set(['completed', 'failed']);

type BadgeVariant = 'success' | 'destructive' | 'warning' | 'secondary';

function statusBadgeVariant(status: string): BadgeVariant {
  if (['found', 'normalized', 'enriched', 'extracted', 'crawled', 'g2_scraped'].includes(status)) return 'success';
  if (['not_found', 'scrape_failed'].includes(status)) return 'destructive';
  if (['blocked', 'extract_failed'].includes(status)) return 'warning';
  return 'secondary';
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    found: 'Found',
    normalized: 'Normalized',
    enriched: 'Enriched',
    not_found: 'Not Found',
    blocked: 'Blocked',
    pending: 'Pending',
    searched: 'Searched',
    verified: 'Verified',
    resolved: 'Resolved',
    crawled: 'Crawled',
    extracted: 'Extracted',
    extract_failed: 'No intel',
    scrape_failed: 'Scrape Failed',
    g2_scraped: 'G2 Scraped',
  };
  return map[status] ?? status.charAt(0).toUpperCase() + status.slice(1);
}

// Loading dots animation for empty state
function LoadingDots() {
  return (
    <span className="inline-flex items-center gap-0.5 ml-1">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="w-1 h-1 rounded-full bg-gray-400 block"
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{
            repeat: Infinity,
            duration: 1.2,
            delay: i * 0.2,
            ease: 'easeInOut',
          }}
        />
      ))}
    </span>
  );
}

const rowVariants = {
  hidden: { opacity: 0, y: 6 },
  visible: { opacity: 1, y: 0 },
};

const listVariants = {
  visible: {
    transition: {
      staggerChildren: 0.05,
    },
  },
};

export default function LivePreview({ jobId, token, isProcessing }: LivePreviewProps) {
  const [rows, setRows] = useState<PreviewRow[]>([]);
  const [isDone, setIsDone] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [pulsingIndices, setPulsingIndices] = useState<Set<number>>(new Set());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Track which row indices have already been animated
  const seenIndicesRef = useRef<Set<number>>(new Set());
  // Track last-seen status per index to detect changes
  const lastStatusRef = useRef<Map<number, string>>(new Map());

  useEffect(() => {
    async function fetchPreview() {
      try {
        const res = await fetch(
          `${API_URL}/api/v1/jobs/${jobId}/preview?limit=200`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (!res.ok) {
          setPreviewError(
            `Failed to load live preview (HTTP ${res.status}).`,
          );
          return;
        }

        setPreviewError(null);
        const data: ApiPreviewResponse = await res.json();
        const incoming = data.rows ?? [];

        const changed = new Set<number>();
        for (const row of incoming) {
          const prev = lastStatusRef.current.get(row.index);
          if (prev !== undefined && prev !== row.status) {
            changed.add(row.index);
          }
          lastStatusRef.current.set(row.index, row.status);
        }
        if (changed.size > 0) {
          setPulsingIndices(changed);
          setTimeout(() => setPulsingIndices(new Set()), 900);
        }

        setRows(incoming);

        if (TERMINAL_STATUSES.has(data.status)) {
          setIsDone(true);
          if (intervalRef.current !== null) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setPreviewError(`Failed to load live preview: ${message}`);
      }
    }

    // Only poll while processing
    if (!isProcessing && !isDone) {
      // Still do an initial fetch in case we have results
      fetchPreview();
      return;
    }

    fetchPreview();

    if (isProcessing && !isDone) {
      intervalRef.current = setInterval(fetchPreview, 5000);
    }

    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [jobId, token, isProcessing, isDone]);

  // Determine which rows are newly added for animation purposes
  const newRows = rows.filter((r) => !seenIndicesRef.current.has(r.index));
  newRows.forEach((r) => seenIndicesRef.current.add(r.index));
  const hasNewRows = newRows.length > 0;

  // Hide location column if no rows have location data (P3 doesn't use location)
  const hasLocationData = rows.some((r) => r.location);

  return (
    <Card className="overflow-hidden">
      <CardHeader className="py-4 px-5 border-b border-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TableProperties className="w-4 h-4 text-text-secondary" />
            <CardTitle className="text-base">Live Results</CardTitle>
            {rows.length > 0 && (
              <span className="text-xs text-text-secondary font-normal tabular-nums">
                ({rows.length})
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {isDone ? (
              <Badge variant="success">Complete</Badge>
            ) : isProcessing ? (
              <div className="flex items-center gap-1.5 text-xs text-text-secondary">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" />
                <span>Live</span>
              </div>
            ) : null}
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-0">
        {previewError && (
          <div className="border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-600">
            {previewError}
          </div>
        )}
        {rows.length === 0 ? (
          /* Empty state */
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center h-32 gap-2 text-sm text-text-secondary"
          >
            <div className="flex items-center">
              <span>Waiting for results</span>
              <LoadingDots />
            </div>
            <p className="text-xs text-gray-400">Results will appear as rows are processed</p>
          </motion.div>
        ) : (
          <div className="overflow-y-auto max-h-[400px]">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-gray-50 border-b border-border">
                <tr>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide w-10">
                    #
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide">
                    {hasLocationData ? 'Company' : 'Input'}
                  </th>
                  {hasLocationData && (
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide hidden sm:table-cell">
                    Location
                  </th>
                  )}
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide hidden md:table-cell">
                    Website
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide">
                    Status
                  </th>
                </tr>
              </thead>

              <AnimatePresence initial={hasNewRows}>
                <motion.tbody
                  className="divide-y divide-border bg-white"
                  variants={listVariants}
                  initial="hidden"
                  animate="visible"
                >
                  {rows.map((row) => (
                    <motion.tr
                      key={row.index}
                      variants={rowVariants}
                      transition={{ duration: 0.25, ease: 'easeOut' }}
                      className={cn(
                        'hover:bg-gray-50/80 transition-colors duration-100',
                      )}
                    >
                      <td className="px-4 py-2.5 text-text-secondary tabular-nums text-xs">
                        {row.index}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className="font-medium text-text-primary truncate block max-w-[160px]">
                          {row.company_name}
                        </span>
                      </td>
                      {hasLocationData && (
                      <td className="px-4 py-2.5 text-text-secondary truncate max-w-[120px] hidden sm:table-cell">
                        {row.location ?? (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                      )}
                      <td className="px-4 py-2.5 max-w-[200px] hidden md:table-cell">
                        {(row.domain || row.website) ? (
                          <a
                            href={`https://${row.domain || row.website}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary hover:underline truncate block text-xs"
                          >
                            {(row.domain || row.website || '').replace(/^https?:\/\//, '')}
                          </a>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <motion.div
                          key={`${row.index}-${row.status}`}
                          initial={pulsingIndices.has(row.index)
                            ? { scale: 0.92, opacity: 0.6 }
                            : false}
                          animate={{ scale: 1, opacity: 1 }}
                          transition={{ duration: 0.35, ease: 'easeOut' }}
                          className="inline-block"
                        >
                          <Badge variant={statusBadgeVariant(row.status)}>
                            {statusLabel(row.status)}
                          </Badge>
                        </motion.div>
                      </td>
                    </motion.tr>
                  ))}
                </motion.tbody>
              </AnimatePresence>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
