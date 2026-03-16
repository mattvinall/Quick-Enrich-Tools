'use client';

import { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Download, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { getDownloadUrl } from '@/lib/api';
import ClayPushModal from './ClayPushModal';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

interface ResultRow {
  index: number;
  company_name: string;
  location?: string;
  domain?: string;
  website?: string;
  confidence?: number;
  status: string;
  contacts?: { title: string; first_name: string; last_name: string; email: string; phone: string; linkedin_url: string }[];
  // contact enrichment fields
  contact_name?: string;
  contact_title?: string;
  contact_email?: string;
  contact_linkedin?: string;
}

interface PreviewResponse {
  rows: ResultRow[];
  status: string;
}

interface ResultsPanelProps {
  jobId: string;
  token: string;
  totalRows: number;
  foundCount: number;
  enrichedCount: number;
}

type FilterTab = 'all' | 'found' | 'not_found';
type SortKey = keyof ResultRow;
type SortDir = 'asc' | 'desc';

function getStatusBadgeVariant(
  status: string,
): 'success' | 'destructive' | 'secondary' | 'outline' {
  if (['normalized', 'enriched', 'found'].includes(status)) return 'success';
  if (['not_found', 'blocked', 'failed'].includes(status)) return 'destructive';
  if (status === 'pending' || status === 'processing') return 'secondary';
  return 'outline';
}

function formatStatus(status: string): string {
  return status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function ConfidenceBar({ value }: { value: number | undefined }) {
  if (value === undefined) return <span className="text-text-secondary text-xs">—</span>;
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 rounded-full bg-gray-100 overflow-hidden">
        <div
          className={cn(
            'h-full rounded-full',
            pct >= 80 ? 'bg-green-500' : pct >= 50 ? 'bg-amber-400' : 'bg-red-400',
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-text-secondary">{pct}%</span>
    </div>
  );
}

const statVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.4, ease: 'easeOut' },
  }),
};

const tableVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: 'easeOut', delay: 0.4 } },
};

export default function ResultsPanel({
  jobId,
  token,
  totalRows,
  foundCount,
  enrichedCount,
}: ResultsPanelProps) {
  const [rows, setRows] = useState<ResultRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [showClay, setShowClay] = useState(false);

  const [filterTab, setFilterTab] = useState<FilterTab>('all');
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('index');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const matchRate = totalRows > 0 ? Math.round((foundCount / totalRows) * 100) : 0;
  const downloadUrl = getDownloadUrl(jobId, token);

  // Determine whether enrichment columns are present
  const hasEnrichment = enrichedCount > 0;

  useEffect(() => {
    async function fetchRows() {
      try {
        const res = await fetch(`${API_URL}/api/v1/jobs/${jobId}/preview?limit=1000`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) return;
        const data = (await res.json()) as PreviewResponse;
        setRows(data.rows ?? []);
      } catch {
        // silently fail — download link still works
      } finally {
        setLoading(false);
      }
    }
    fetchRows();
  }, [jobId, token]);

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  }

  const filteredRows = useMemo(() => {
    let result = rows;

    if (filterTab === 'found') {
      result = result.filter((r) => ['normalized', 'enriched', 'found'].includes(r.status));
    } else if (filterTab === 'not_found') {
      result = result.filter((r) => ['not_found', 'blocked', 'failed'].includes(r.status));
    }

    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter((r) => r.company_name?.toLowerCase().includes(q));
    }

    result = [...result].sort((a, b) => {
      const av = a[sortKey] ?? '';
      const bv = b[sortKey] ?? '';
      const cmp = String(av).localeCompare(String(bv), undefined, { numeric: true });
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return result;
  }, [rows, filterTab, search, sortKey, sortDir]);

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) {
      return <span className="ml-1 text-gray-300 select-none">↕</span>;
    }
    return (
      <span className="ml-1 text-primary select-none">{sortDir === 'asc' ? '↑' : '↓'}</span>
    );
  }

  const stats = [
    {
      label: 'Total Rows',
      value: totalRows,
      color: 'text-text-primary',
      bg: 'bg-gray-50',
      border: 'border-gray-200',
    },
    {
      label: 'Websites Found',
      value: foundCount,
      color: 'text-green-600',
      bg: 'bg-green-50',
      border: 'border-green-200',
    },
    {
      label: 'Match Rate',
      value: `${matchRate}%`,
      color: 'text-blue-600',
      bg: 'bg-blue-50',
      border: 'border-blue-200',
    },
    ...(hasEnrichment
      ? [
          {
            label: 'Contacts Enriched',
            value: enrichedCount,
            color: 'text-purple-600',
            bg: 'bg-purple-50',
            border: 'border-purple-200',
          },
        ]
      : []),
  ];

  const filterTabs: { key: FilterTab; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'found', label: 'Found' },
    { key: 'not_found', label: 'Not Found' },
  ];

  return (
    <div className="space-y-8">
      {/* Success header */}
      <div className="flex flex-col items-center text-center gap-4">
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: 'spring', stiffness: 260, damping: 18 }}
          className="flex items-center justify-center w-16 h-16 rounded-full bg-green-100 shadow-sm"
        >
          <svg
            className="w-8 h-8 text-green-600"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2.5}
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15, duration: 0.4 }}
          className="space-y-1"
        >
          <h2 className="text-2xl font-bold text-text-primary">Processing Complete!</h2>
          <p className="text-text-secondary text-sm">
            Your enriched data is ready to download below.
          </p>
        </motion.div>
      </div>

      {/* Stats grid */}
      <div
        className={cn(
          'grid gap-3',
          stats.length === 4 ? 'grid-cols-2 sm:grid-cols-4' : 'grid-cols-3',
        )}
      >
        {stats.map((stat, i) => (
          <motion.div
            key={stat.label}
            custom={i}
            variants={statVariants}
            initial="hidden"
            animate="visible"
            className={cn(
              'rounded-xl border p-4 text-center',
              stat.bg,
              stat.border,
            )}
          >
            <p className={cn('text-2xl font-bold tabular-nums', stat.color)}>{stat.value}</p>
            <p className="text-xs text-text-secondary mt-1 font-medium">{stat.label}</p>
          </motion.div>
        ))}
      </div>

      {/* Action buttons */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.35 }}
        className="flex flex-col sm:flex-row gap-3"
      >
        <Button asChild className="flex-1 gap-2">
          <a href={downloadUrl} download>
            <Download className="w-4 h-4" />
            Download CSV
          </a>
        </Button>
        <Button
          variant="outline"
          className="flex-1"
          onClick={() => setShowClay(true)}
        >
          Push to Clay
        </Button>
      </motion.div>

      {/* Results table */}
      <motion.div
        variants={tableVariants}
        initial="hidden"
        animate="visible"
        className="space-y-3"
      >
        {/* Filter + search row */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
          {/* Tabs */}
          <div className="flex rounded-lg border border-border overflow-hidden text-sm bg-white shrink-0">
            {filterTabs.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setFilterTab(tab.key)}
                className={cn(
                  'px-4 py-2 font-medium transition-colors',
                  filterTab === tab.key
                    ? 'bg-primary text-white'
                    : 'text-text-secondary hover:bg-gray-50',
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <Input
            placeholder="Search by company name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-xs"
          />

          <span className="text-xs text-text-secondary ml-auto shrink-0">
            {filteredRows.length} of {rows.length} rows
          </span>
        </div>

        {/* Table */}
        <div className="rounded-xl border border-border overflow-hidden bg-white">
          {loading ? (
            <div className="flex items-center justify-center h-32 text-sm text-text-secondary">
              Loading results…
            </div>
          ) : rows.length === 0 ? (
            <div className="flex items-center justify-center h-32 text-sm text-text-secondary">
              No results available.
            </div>
          ) : (
            <div className="overflow-x-auto overflow-y-auto max-h-[480px]">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 sticky top-0 z-10 border-b border-border">
                  <tr>
                    {(
                      [
                        { key: 'company_name', label: 'Company' },
                        { key: 'location', label: 'Location' },
                        { key: 'website', label: 'Website' },
                        { key: 'confidence', label: 'Confidence' },
                        { key: 'status', label: 'Status' },
                        ...(hasEnrichment
                          ? [
                              { key: 'contact_name', label: 'Contact' },
                              { key: 'contact_title', label: 'Title' },
                              { key: 'contact_email', label: 'Email' },
                            ]
                          : []),
                      ] as { key: SortKey; label: string }[]
                    ).map((col) => (
                      <th
                        key={String(col.key)}
                        scope="col"
                        onClick={() => handleSort(col.key)}
                        className="px-4 py-3 text-left text-xs font-semibold text-text-secondary whitespace-nowrap cursor-pointer hover:text-text-primary select-none transition-colors"
                      >
                        {col.label}
                        <SortIcon col={col.key} />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  <AnimatePresence mode="wait">
                    {filteredRows.length === 0 ? (
                      <tr>
                        <td
                          colSpan={hasEnrichment ? 8 : 5}
                          className="px-4 py-8 text-center text-sm text-text-secondary"
                        >
                          No rows match your filter.
                        </td>
                      </tr>
                    ) : (
                      filteredRows.map((row, i) => (
                        <motion.tr
                          key={row.index}
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ delay: Math.min(i * 0.02, 0.3) }}
                          className="hover:bg-gray-50 transition-colors"
                        >
                          <td className="px-4 py-3 font-medium text-text-primary max-w-[180px] truncate">
                            {row.company_name}
                          </td>
                          <td className="px-4 py-3 text-text-secondary max-w-[140px] truncate">
                            {row.location ?? '—'}
                          </td>
                          <td className="px-4 py-3 max-w-[200px]">
                            {(row.domain || row.website) ? (
                              <a
                                href={`https://${row.domain || row.website}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-primary hover:underline flex items-center gap-1 truncate"
                              >
                                <span className="truncate">{row.domain || row.website}</span>
                                <ExternalLink className="w-3 h-3 shrink-0" />
                              </a>
                            ) : (
                              <span className="text-text-secondary">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <ConfidenceBar value={row.confidence} />
                          </td>
                          <td className="px-4 py-3">
                            <Badge variant={getStatusBadgeVariant(row.status)}>
                              {formatStatus(row.status)}
                            </Badge>
                          </td>
                          {hasEnrichment && (
                            <>
                              <td className="px-4 py-3 text-text-primary max-w-[140px] truncate">
                                {row.contact_name ?? '—'}
                              </td>
                              <td className="px-4 py-3 text-text-secondary max-w-[140px] truncate">
                                {row.contact_title ?? '—'}
                              </td>
                              <td className="px-4 py-3 text-text-secondary max-w-[180px] truncate">
                                {row.contact_email ?? '—'}
                              </td>
                            </>
                          )}
                        </motion.tr>
                      ))
                    )}
                  </AnimatePresence>
                </tbody>
              </table>
            </div>
          )}
        </div>
      </motion.div>

      {/* Footer note */}
      <p className="text-center text-xs text-text-secondary pb-2">
        Results have been emailed to your address.
      </p>

      <ClayPushModal
        jobId={jobId}
        token={token}
        open={showClay}
        onClose={() => setShowClay(false)}
      />
    </div>
  );
}
