'use client';

import { useState, useMemo } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ExternalLink, Loader2, RefreshCw, Search } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { discoverFunding, FundingCompany } from '@/lib/api';

const ROUND_FILTERS = ['All', 'Seed', 'Series A', 'Series B', 'Series C+', 'Growth', 'Unknown'] as const;
type RoundFilter = typeof ROUND_FILTERS[number];

const ROUND_BADGE_COLORS: Record<string, string> = {
  seed: 'bg-blue-100 text-blue-700',
  'series a': 'bg-green-100 text-green-700',
  'series b': 'bg-purple-100 text-purple-700',
  'series c': 'bg-orange-100 text-orange-700',
  'series c+': 'bg-orange-100 text-orange-700',
  'series d': 'bg-orange-100 text-orange-700',
  'series e': 'bg-orange-100 text-orange-700',
  growth: 'bg-amber-100 text-amber-700',
  unknown: 'bg-gray-100 text-gray-500',
};

function getRoundBadgeColor(round: string): string {
  const lower = round.toLowerCase().trim();
  if (ROUND_BADGE_COLORS[lower]) return ROUND_BADGE_COLORS[lower];
  // Series C and above -> orange
  if (lower.startsWith('series') && lower > 'series b') return 'bg-orange-100 text-orange-700';
  return 'bg-gray-100 text-gray-500';
}

function matchesFilter(round: string, filter: RoundFilter): boolean {
  if (filter === 'All') return true;
  const lower = round.toLowerCase().trim();
  if (filter === 'Unknown') return !lower || lower === 'unknown';
  if (filter === 'Series C+') {
    return (
      lower.startsWith('series') &&
      lower !== 'series a' &&
      lower !== 'series b'
    );
  }
  return lower === filter.toLowerCase();
}

interface FundingDiscoveryPanelProps {
  selectedCompanies: FundingCompany[];
  onSelectionChange: (companies: FundingCompany[]) => void;
  hours: number;
  onHoursChange: (h: number) => void;
  serperApiKey: string;
}

export default function FundingDiscoveryPanel({
  selectedCompanies,
  onSelectionChange,
  hours,
  onHoursChange,
  serperApiKey,
}: FundingDiscoveryPanelProps) {
  const [companies, setCompanies] = useState<FundingCompany[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeFilter, setActiveFilter] = useState<RoundFilter>('All');
  const [hasDiscovered, setHasDiscovered] = useState(false);

  async function loadCompanies() {
    if (!serperApiKey.trim()) return;
    setLoading(true);
    setError('');
    setHasDiscovered(true);
    try {
      const data = await discoverFunding(hours, serperApiKey.trim());
      setCompanies(data.companies);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to discover funded companies.');
    } finally {
      setLoading(false);
    }
  }

  const filtered = useMemo(() => {
    if (activeFilter === 'All') return companies;
    return companies.filter((c) => matchesFilter(c.funding_round, activeFilter));
  }, [companies, activeFilter]);

  // Track selected by company_name + source_url as key
  function companyKey(c: FundingCompany): string {
    return `${c.company_name}::${c.source_url}`;
  }

  const selectedKeys = useMemo(() => {
    const set = new Set(selectedCompanies.map(companyKey));
    return set;
  }, [selectedCompanies]);

  function isSelected(c: FundingCompany): boolean {
    return selectedKeys.has(companyKey(c));
  }

  function toggleCompany(c: FundingCompany) {
    const key = companyKey(c);
    if (selectedKeys.has(key)) {
      onSelectionChange(selectedCompanies.filter((sc) => companyKey(sc) !== key));
    } else {
      onSelectionChange([...selectedCompanies, c]);
    }
  }

  function selectAllVisible() {
    const existing = new Set(selectedCompanies.map(companyKey));
    const toAdd = filtered.filter((c) => !existing.has(companyKey(c)));
    onSelectionChange([...selectedCompanies, ...toAdd]);
  }

  function deselectAll() {
    onSelectionChange([]);
  }

  return (
    <div className="space-y-4">
      {/* Hours toggle + selection count */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-text-primary">Time range:</span>
          <div className="flex rounded-md border border-border overflow-hidden">
            {[
              { value: 24, label: '24h' },
              { value: 48, label: '48h' },
              { value: 72, label: '3d' },
              { value: 168, label: '7d' },
            ].map(({ value, label }) => (
              <button
                key={value}
                type="button"
                onClick={() => onHoursChange(value)}
                className={cn(
                  'px-3 py-1 text-xs font-medium transition-colors',
                  hours === value
                    ? 'bg-primary text-white'
                    : 'bg-white text-text-secondary hover:bg-gray-50',
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={loadCompanies}
            disabled={!serperApiKey.trim() || loading}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1 text-xs font-semibold rounded-md transition-colors',
              'bg-primary text-white hover:bg-primary/90',
              'disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed',
            )}
          >
            {loading ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Search className="w-3 h-3" />
            )}
            {hasDiscovered ? 'Refresh' : 'Discover'}
          </button>
        </div>

        {selectedCompanies.length > 0 && (
          <span className="text-xs font-semibold text-primary">
            {selectedCompanies.length} {selectedCompanies.length === 1 ? 'company' : 'companies'} selected
          </span>
        )}
      </div>

      {/* Filter pills */}
      <div className="flex flex-wrap gap-1.5">
        {ROUND_FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setActiveFilter(f)}
            className={cn(
              'px-3 py-1 text-xs font-medium rounded-full border transition-colors',
              activeFilter === f
                ? 'bg-primary text-white border-primary'
                : 'bg-white text-text-secondary border-border hover:border-primary/40',
            )}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Select / Deselect buttons */}
      {!loading && !error && filtered.length > 0 && (
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={selectAllVisible}
            className="text-xs font-medium text-primary hover:underline"
          >
            Select All Visible ({filtered.length})
          </button>
          {selectedCompanies.length > 0 && (
            <>
              <span className="text-xs text-gray-300">|</span>
              <button
                type="button"
                onClick={deselectAll}
                className="text-xs font-medium text-red-500 hover:underline"
              >
                Deselect All
              </button>
            </>
          )}
        </div>
      )}

      {/* Company list */}
      <div className="border border-border rounded-lg overflow-hidden max-h-[400px] overflow-y-auto bg-white">
        {!serperApiKey.trim() ? (
          <div className="flex flex-col items-center justify-center h-32 gap-1 px-4 text-center">
            <p className="text-sm font-medium text-text-primary">Serper API key required</p>
            <p className="text-xs text-text-secondary">
              Enter your Serper key below, then click Discover to find funded companies.
            </p>
          </div>
        ) : !hasDiscovered ? (
          <div className="flex flex-col items-center justify-center h-32 gap-1 px-4 text-center">
            <p className="text-sm font-medium text-text-primary">Ready to discover</p>
            <p className="text-xs text-text-secondary">
              Pick a time range and click Discover.
            </p>
          </div>
        ) : loading ? (
          <div className="flex items-center justify-center h-32 gap-2 text-sm text-text-secondary">
            <Loader2 className="w-4 h-4 animate-spin" />
            Discovering funded companies...
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-32 gap-2">
            <p className="text-sm text-red-600">{error}</p>
            <button
              type="button"
              onClick={loadCompanies}
              className="flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Retry
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-sm text-text-secondary">
            No companies match this filter.
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {filtered.map((company) => {
              const selected = isSelected(company);
              return (
                <motion.label
                  key={companyKey(company)}
                  layout
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                  className={cn(
                    'flex items-start gap-3 px-3 py-3 cursor-pointer hover:bg-gray-50/80 transition-colors border-b border-border/50 last:border-b-0',
                    selected && 'bg-primary/5',
                  )}
                >
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={() => toggleCompany(company)}
                    className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary/50 cursor-pointer shrink-0 mt-0.5"
                  />
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-text-primary">
                        {company.company_name}
                      </span>
                      <Badge
                        className={cn(
                          'text-[10px] px-2 py-0',
                          getRoundBadgeColor(company.funding_round),
                        )}
                      >
                        {company.funding_round || 'Unknown'}
                      </Badge>
                      {company.funding_amount && (
                        <span className="text-sm font-bold text-green-600">
                          {company.funding_amount}
                        </span>
                      )}
                    </div>
                    {company.lead_investor && (
                      <p className="text-xs text-text-secondary">
                        Lead: {company.lead_investor}
                      </p>
                    )}
                    {company.description_snippet && (
                      <p className="text-xs text-text-secondary line-clamp-2">
                        {company.description_snippet}
                      </p>
                    )}
                  </div>
                  {company.source_url && (
                    <a
                      href={company.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="shrink-0 text-gray-400 hover:text-primary transition-colors mt-0.5"
                      aria-label={`Source for ${company.company_name}`}
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  )}
                </motion.label>
              );
            })}
          </AnimatePresence>
        )}
      </div>
    </div>
  );
}
