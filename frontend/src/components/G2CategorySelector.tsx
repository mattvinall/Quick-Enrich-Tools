'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Search, X, Layers, ChevronDown } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { getG2Categories, G2Category } from '@/lib/api';

const MAX_PER_CATEGORY_OPTIONS = [50, 100, 250, 500] as const;

interface G2CategorySelectorProps {
  selectedSlugs: string[];
  onSelectionChange: (slugs: string[]) => void;
  maxPerCategory: number;
  onMaxPerCategoryChange: (v: number) => void;
}

export default function G2CategorySelector({
  selectedSlugs,
  onSelectionChange,
  maxPerCategory,
  onMaxPerCategoryChange,
}: G2CategorySelectorProps) {
  const [categories, setCategories] = useState<G2Category[]>([]);
  const [parents, setParents] = useState<string[]>([]);
  const [search, setSearch] = useState('');
  const [activeParent, setActiveParent] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);

  async function loadCategories() {
    setLoading(true);
    setError('');
    try {
      const data = await getG2Categories();
      setCategories(data.categories);
      setParents(data.parents);
    } catch {
      setError('Failed to load categories. Please check your connection.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCategories();
  }, []);

  // Filter categories
  const filtered = useMemo(() => {
    let result = categories;
    if (activeParent) {
      result = result.filter((c) => c.parent === activeParent);
    }
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      result = result.filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          c.slug.includes(q) ||
          c.parent.toLowerCase().includes(q),
      );
    }
    return result;
  }, [categories, activeParent, search]);

  // Group by parent for display
  const grouped = useMemo(() => {
    const map: Record<string, G2Category[]> = {};
    for (const cat of filtered) {
      (map[cat.parent] ??= []).push(cat);
    }
    return Object.entries(map).sort(([a], [b]) => a.localeCompare(b));
  }, [filtered]);

  function toggleCategory(slug: string) {
    if (selectedSlugs.includes(slug)) {
      onSelectionChange(selectedSlugs.filter((s) => s !== slug));
    } else {
      onSelectionChange([...selectedSlugs, slug]);
    }
  }

  function removeCategory(slug: string) {
    onSelectionChange(selectedSlugs.filter((s) => s !== slug));
  }

  const selectedCategories = categories.filter((c) => selectedSlugs.includes(c.slug));

  return (
    <div className="space-y-4">
      {/* Selected chips */}
      {selectedSlugs.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-text-primary">
              {selectedSlugs.length} {selectedSlugs.length === 1 ? 'category' : 'categories'} selected
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <AnimatePresence mode="popLayout">
              {selectedCategories.map((cat) => (
                <motion.div
                  key={cat.slug}
                  layout
                  initial={{ scale: 0.8, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={{ scale: 0.8, opacity: 0 }}
                  transition={{ duration: 0.15 }}
                >
                  <Badge variant="secondary" className="gap-1 pr-1.5 pl-2.5 py-1">
                    {cat.name}
                    <button
                      type="button"
                      onClick={() => removeCategory(cat.slug)}
                      aria-label={`Remove ${cat.name}`}
                      className="ml-0.5 rounded-full p-0.5 hover:bg-gray-300 transition-colors"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <input
          ref={searchRef}
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search categories..."
          className="w-full pl-9 pr-3 py-2 text-sm border border-border rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
        />
      </div>

      {/* Parent filter tabs */}
      <div className="flex flex-wrap gap-1.5">
        <button
          type="button"
          onClick={() => setActiveParent('')}
          className={cn(
            'px-3 py-1 text-xs font-medium rounded-full border transition-colors',
            !activeParent
              ? 'bg-primary text-white border-primary'
              : 'bg-white text-text-secondary border-border hover:border-primary/40',
          )}
        >
          All
        </button>
        {parents.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setActiveParent(activeParent === p ? '' : p)}
            className={cn(
              'px-3 py-1 text-xs font-medium rounded-full border transition-colors',
              activeParent === p
                ? 'bg-primary text-white border-primary'
                : 'bg-white text-text-secondary border-border hover:border-primary/40',
            )}
          >
            {p}
          </button>
        ))}
      </div>

      {/* Category list */}
      <div className="border border-border rounded-lg overflow-hidden max-h-[320px] overflow-y-auto bg-white">
        {loading ? (
          <div className="flex items-center justify-center h-24 text-sm text-text-secondary">
            Loading categories...
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-24 gap-2">
            <p className="text-sm text-red-600">{error}</p>
            <button
              type="button"
              onClick={loadCategories}
              className="text-sm font-medium text-primary hover:underline"
            >
              Retry
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex items-center justify-center h-24 text-sm text-text-secondary">
            No categories match your search.
          </div>
        ) : (
          grouped.map(([parent, cats]) => (
            <div key={parent}>
              <div className="sticky top-0 z-10 px-3 py-1.5 bg-gray-50 border-b border-border">
                <span className="text-xs font-semibold text-text-secondary uppercase tracking-wide">
                  {parent}
                </span>
              </div>
              {cats.map((cat) => {
                const isSelected = selectedSlugs.includes(cat.slug);
                return (
                  <label
                    key={cat.slug}
                    className={cn(
                      'flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-gray-50/80 transition-colors border-b border-border/50 last:border-b-0',
                      isSelected && 'bg-primary/5',
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleCategory(cat.slug)}
                      className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary/50 cursor-pointer shrink-0"
                    />
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium text-text-primary">{cat.name}</span>
                    </div>
                  </label>
                );
              })}
            </div>
          ))
        )}
      </div>

      {/* Max per category */}
      <div className="flex items-center justify-between gap-4 pt-1">
        <div className="space-y-0.5">
          <label className="text-xs font-semibold text-text-primary">Max companies per category</label>
          <p className="text-xs text-text-secondary">Limit how many companies to discover from each category.</p>
        </div>
        <select
          value={maxPerCategory}
          onChange={(e) => onMaxPerCategoryChange(Number(e.target.value))}
          className={cn(
            'w-20 shrink-0 px-2.5 py-1.5 text-sm rounded-md',
            'border border-border bg-white text-text-primary',
            'focus:outline-none focus:ring-2 focus:ring-primary/40',
          )}
        >
          {MAX_PER_CATEGORY_OPTIONS.map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </div>
    </div>
  );
}
