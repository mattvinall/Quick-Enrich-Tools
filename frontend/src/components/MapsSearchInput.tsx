'use client';

import { useState, useRef } from 'react';
import { MapPin, Search, Upload, X } from 'lucide-react';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import Papa from 'papaparse';

interface MapsSearchItem {
  search_term: string;
  location: string;
}

interface MapsSearchInputProps {
  searchTerms: string[];
  onSearchTermsChange: (terms: string[]) => void;
  location: string;
  onLocationChange: (loc: string) => void;
  maxPerSearch: number;
  onMaxPerSearchChange: (n: number) => void;
  csvSearches: MapsSearchItem[];
  onCsvSearchesChange: (searches: MapsSearchItem[]) => void;
}

// Backend now paginates /maps; safe to request up to 100 per term.
const MAX_OPTIONS = [20, 50, 100];

export default function MapsSearchInput({
  searchTerms,
  onSearchTermsChange,
  location,
  onLocationChange,
  maxPerSearch,
  onMaxPerSearchChange,
  csvSearches,
  onCsvSearchesChange,
}: MapsSearchInputProps) {
  const [mode, setMode] = useState<'interactive' | 'csv'>('interactive');
  const [rawText, setRawText] = useState(searchTerms.join('\n'));
  const [csvError, setCsvError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  function handleTextChange(value: string) {
    setRawText(value);
    const terms = value
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean);
    onSearchTermsChange(terms);
    // Clear CSV searches when switching to interactive
    if (csvSearches.length > 0) onCsvSearchesChange([]);
  }

  function handleCSVUpload(file: File) {
    setCsvError('');
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete(results) {
        const headers = results.meta.fields || [];
        const termCol = headers.find((h) => /search.?term|query|keyword|category/i.test(h));
        const locCol = headers.find((h) => /location|city|state|area|region/i.test(h));

        if (!termCol) {
          setCsvError('CSV must have a column matching "search_term", "query", "keyword", or "category".');
          return;
        }

        const terms: string[] = [];
        const locations = new Set<string>();
        const perRowSearches: MapsSearchItem[] = [];

        for (const row of results.data as Record<string, string>[]) {
          const term = (row[termCol] || '').trim();
          if (!term) continue;
          terms.push(term);
          const loc = locCol ? (row[locCol] || '').trim() : '';
          if (loc) locations.add(loc);
          if (locCol && loc) {
            perRowSearches.push({ search_term: term, location: loc });
          }
        }

        onSearchTermsChange(terms);
        setRawText(terms.join('\n'));

        if (locations.size === 1) {
          // All rows share same location — use interactive mode
          onLocationChange(Array.from(locations)[0]);
          onCsvSearchesChange([]);
        } else if (locations.size > 1 && perRowSearches.length > 0) {
          // Different locations per row — use CSV mode
          onCsvSearchesChange(perRowSearches);
        }
      },
      error() {
        setCsvError('Failed to parse CSV file.');
      },
    });
  }

  const estimatedTotal = searchTerms.length * maxPerSearch;

  return (
    <div className="space-y-5">
      {/* Mode toggle */}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setMode('interactive')}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
            mode === 'interactive'
              ? 'bg-primary text-white'
              : 'bg-gray-100 text-text-secondary hover:bg-gray-200',
          )}
        >
          <Search className="w-3.5 h-3.5" />
          Type searches
        </button>
        <button
          type="button"
          onClick={() => setMode('csv')}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
            mode === 'csv'
              ? 'bg-primary text-white'
              : 'bg-gray-100 text-text-secondary hover:bg-gray-200',
          )}
        >
          <Upload className="w-3.5 h-3.5" />
          Upload CSV
        </button>
      </div>

      {/* Search terms */}
      {mode === 'interactive' ? (
        <div className="space-y-2">
          <Label htmlFor="search-terms">Search terms (one per line)</Label>
          <Textarea
            id="search-terms"
            rows={5}
            placeholder={"plumber\nelectrician\nHVAC repair\nroofer"}
            value={rawText}
            onChange={(e) => handleTextChange(e.target.value)}
            className="font-mono text-sm"
          />
          {searchTerms.length > 0 && (
            <p className="text-xs text-text-secondary">
              {searchTerms.length} search {searchTerms.length === 1 ? 'term' : 'terms'}
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          <Label>Upload CSV with search terms</Label>
          <div
            className="border-2 border-dashed border-border rounded-lg p-6 text-center cursor-pointer hover:border-primary/40 transition-colors"
            onClick={() => fileRef.current?.click()}
          >
            <Upload className="w-6 h-6 mx-auto mb-2 text-text-secondary" />
            <p className="text-sm text-text-secondary">
              Click to upload CSV with <span className="font-medium">search_term</span> column
            </p>
            <p className="text-xs text-text-secondary mt-1">
              Optional: include a <span className="font-medium">location</span> column
            </p>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleCSVUpload(file);
            }}
          />
          {csvError && <p className="text-sm text-red-600">{csvError}</p>}
          {searchTerms.length > 0 && mode === 'csv' && (
            <div className="flex items-center gap-2 text-sm text-text-secondary bg-gray-50 rounded-md px-3 py-2">
              <span className="font-medium text-text-primary">{searchTerms.length}</span> search terms loaded from CSV
              {csvSearches.length > 0 && (
                <span className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded-full">
                  {new Set(csvSearches.map((s) => s.location)).size} locations
                </span>
              )}
              <button
                type="button"
                onClick={() => {
                  onSearchTermsChange([]);
                  onCsvSearchesChange([]);
                  setRawText('');
                  if (fileRef.current) fileRef.current.value = '';
                }}
                className="ml-auto text-text-secondary hover:text-red-500"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      )}

      {/* Location — only show if not using per-row CSV locations */}
      {csvSearches.length === 0 && (
        <div className="space-y-2">
          <Label htmlFor="location">
            <span className="flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5" />
              Location
            </span>
          </Label>
          <Input
            id="location"
            placeholder="Miami, FL"
            value={location}
            onChange={(e) => onLocationChange(e.target.value)}
          />
          <p className="text-xs text-text-secondary">
            City, state, or region to search in
          </p>
        </div>
      )}

      {csvSearches.length > 0 && (
        <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3">
          <p className="text-sm text-green-800">
            Using per-row locations from CSV ({new Set(csvSearches.map((s) => s.location)).size} unique locations)
          </p>
        </div>
      )}

      {/* Max per search */}
      {MAX_OPTIONS.length > 1 && (
        <div className="space-y-2">
          <Label htmlFor="max-per-search">Max results per search term</Label>
          <select
            id="max-per-search"
            value={maxPerSearch}
            onChange={(e) => onMaxPerSearchChange(Number(e.target.value))}
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            {MAX_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n} businesses
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Estimated total */}
      {searchTerms.length > 0 && (location || csvSearches.length > 0) && (
        <div className="bg-primary/5 border border-primary/20 rounded-lg px-4 py-3">
          <p className="text-sm text-text-primary">
            <span className="font-semibold">{searchTerms.length}</span>{' '}
            {searchTerms.length === 1 ? 'search' : 'searches'}
            {csvSearches.length > 0 ? (
              <> across <span className="font-semibold">{new Set(csvSearches.map((s) => s.location)).size}</span> locations</>
            ) : (
              <> in <span className="font-semibold">{location}</span></>
            )}
            {' = '}
            <span className="font-semibold text-primary">~{estimatedTotal.toLocaleString()}</span>{' '}
            estimated businesses
          </p>
        </div>
      )}
    </div>
  );
}
