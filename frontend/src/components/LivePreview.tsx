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
  if (['found', 'normalized', 'enriched'].includes(status)) return 'success';
  if (['not_found'].includes(status)) return 'destructive';
  if (['blocked'].includes(status)) return 'warning';
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
  };
  return map[status] ?? status;
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
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Track which row indices have already been animated
  const seenIndicesRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    async function fetchPreview() {
      try {
        const res = await fetch(
          `${API_URL}/api/v1/jobs/${jobId}/preview?limit=50`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (!res.ok) return;

        const data: ApiPreviewResponse = await res.json();
        setRows(data.rows ?? []);

        if (TERMINAL_STATUSES.has(data.status)) {
          setIsDone(true);
          if (intervalRef.current !== null) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
        }
      } catch {
        // network error — keep polling
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
                    Company
                  </th>
                  <th className="px-4 py-2.5 text-left text-xs font-semibold text-text-secondary uppercase tracking-wide hidden sm:table-cell">
                    Location
                  </th>
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
                      <td className="px-4 py-2.5 text-text-secondary truncate max-w-[120px] hidden sm:table-cell">
                        {row.location ?? (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 max-w-[200px] hidden md:table-cell">
                        {row.website ? (
                          <a
                            href={row.website}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary hover:underline truncate block text-xs"
                          >
                            {row.website.replace(/^https?:\/\//, '')}
                          </a>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge variant={statusBadgeVariant(row.status)}>
                          {statusLabel(row.status)}
                        </Badge>
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
