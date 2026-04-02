'use client';

import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Building2, Upload, ClipboardPaste, FileText, X, AlertCircle, ChevronRight } from 'lucide-react';
import Papa from 'papaparse';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';

import IntelInputPanel, { computeLineStats } from '@/components/IntelInputPanel';
import ExtractionSettings from '@/components/ExtractionSettings';
import EmailGate from '@/components/EmailGate';
import ProgressTracker from '@/components/ProgressTracker';
import LivePreview from '@/components/LivePreview';
import ResultsPanel from '@/components/ResultsPanel';
import { useSSE } from '@/hooks/useSSE';
import { captureEmail, submitExtraction, getIntelDownloadUrl } from '@/lib/api';

type Phase = 'input' | 'configure' | 'submit' | 'processing' | 'results';

const PHASE_ORDER: Phase[] = ['input', 'configure', 'submit', 'processing', 'results'];

const PIPELINE_PHASES = ['Resolve', 'Crawl', 'Extract', 'Enrich', 'Deliver'] as const;

const STEP_MAP: Partial<Record<Phase, { step: number; total: number; label: string }>> = {
  input:     { step: 1, total: 4, label: 'Upload your data' },
  configure: { step: 2, total: 4, label: 'Extraction settings' },
  submit:    { step: 3, total: 4, label: 'Enter your email' },
  processing:{ step: 4, total: 4, label: 'Processing' },
};

function phaseIndex(p: Phase): number {
  return PHASE_ORDER.indexOf(p);
}

export default function CompanyIntelPage() {
  const [phase, setPhase] = useState<Phase>('input');
  const [direction, setDirection] = useState<'forward' | 'back'>('forward');

  // Input — paste mode
  const [inputText, setInputText] = useState('');

  // Input — CSV mode
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvHeaders, setCsvHeaders] = useState<string[]>([]);
  const [csvRows, setCsvRows] = useState<Record<string, string>[]>([]);
  const [selectedColumn, setSelectedColumn] = useState('');
  const [csvError, setCsvError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [inputMode, setInputMode] = useState<'paste' | 'csv'>('paste');

  // Derived lines from either input mode
  const lines = useMemo(() => {
    if (inputMode === 'csv' && selectedColumn && csvRows.length > 0) {
      return csvRows.map(row => (row[selectedColumn] || '').trim()).filter(Boolean);
    }
    return inputText.split('\n').map(l => l.trim()).filter(Boolean);
  }, [inputMode, inputText, csvRows, selectedColumn]);

  const lineStats = useMemo(() => {
    const text = lines.join('\n');
    return computeLineStats(text);
  }, [lines]);

  // CSV parsing
  const handleCsvFile = useCallback((file: File) => {
    setCsvError('');
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setCsvError('Invalid file type. Please upload a .csv file.');
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setCsvError('File is too large. Maximum allowed size is 50MB.');
      return;
    }

    Papa.parse<Record<string, string>>(file, {
      header: true,
      skipEmptyLines: true,
      transformHeader: (h) => h.trim(),
      complete: (results) => {
        const headers = results.meta.fields ?? [];
        if (headers.length === 0) {
          setCsvError('CSV file appears to have no headers.');
          return;
        }
        if (results.data.length > 100_000) {
          setCsvError(`CSV has ${results.data.length.toLocaleString()} rows. Maximum is 100,000.`);
          return;
        }
        setCsvFile(file);
        setCsvHeaders(headers);
        setCsvRows(results.data);
        // Auto-select first column that looks like a URL/company column
        const urlCol = headers.find(h => /url|website|domain|link/i.test(h));
        const companyCol = headers.find(h => /company|name|org|business/i.test(h));
        setSelectedColumn(urlCol || companyCol || headers[0]);
      },
      error: () => {
        setCsvError('Failed to parse CSV file.');
      },
    });
  }, []);

  const handleRemoveCsv = () => {
    setCsvFile(null);
    setCsvHeaders([]);
    setCsvRows([]);
    setSelectedColumn('');
    setCsvError('');
  };

  // Extraction options
  const [industryDescription, setIndustryDescription] = useState(true);
  const [targetMarket, setTargetMarket] = useState(true);
  const [companyPeople, setCompanyPeople] = useState(true);
  const [homepageRawText, setHomepageRawText] = useState(false);

  // QuickEnrich API key
  const [quickenrichApiKey, setQuickenrichApiKey] = useState('');

  // Serper API key (for company name resolution)
  const [serperApiKey, setSerperApiKey] = useState('');

  // Contact config
  const [jobTitles, setJobTitles] = useState<string[]>(['CEO', 'Founder']);
  const [maxContacts, setMaxContacts] = useState(3);

  // Job state — restore from localStorage
  const [jobId, setJobId] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("qe_intel_job_id");
  });
  const [token, setToken] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("qe_intel_token");
  });

  // Submit state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  // Persist job session
  useEffect(() => {
    if (jobId && token) {
      localStorage.setItem("qe_intel_job_id", jobId);
      localStorage.setItem("qe_intel_token", token);
    }
  }, [jobId, token]);

  // Resume saved job on mount
  useEffect(() => {
    if (jobId && token && phase === "input") {
      setPhase("processing");
    }
  }, []);

  // SSE
  const { progress } = useSSE(
    phase === 'processing' ? jobId : null,
    phase === 'processing' ? token : null,
  );

  // Transition to results on completion
  useEffect(() => {
    if (phase === 'processing' && progress?.status === 'completed') {
      navigate('results');
    }
  }, [phase, progress?.status]);

  function navigate(next: Phase) {
    setDirection(phaseIndex(next) >= phaseIndex(phase) ? 'forward' : 'back');
    setPhase(next);
  }

  function clearSession() {
    localStorage.removeItem("qe_intel_job_id");
    localStorage.removeItem("qe_intel_token");
    setJobId(null);
    setToken(null);
  }

  // Validation
  const hasData = lineStats.total > 0;
  const hasOptions = industryDescription || targetMarket || companyPeople || homepageRawText;
  const canSubmit = hasData && hasOptions;

  async function handleEmailSubmit(email: string) {
    setIsSubmitting(true);
    setSubmitError('');

    try {
      const capture = await captureEmail(email, 'company-intel', 'company-intel-page');

      const result = await submitExtraction(
        {
          lines,
          options: {
            industry_description: industryDescription,
            target_market: targetMarket,
            company_people: companyPeople,
            homepage_raw_text: homepageRawText,
          },
          quickenrich_api_key: quickenrichApiKey,
          serper_api_key: serperApiKey,
          job_titles: companyPeople ? jobTitles : [],
          max_contacts: companyPeople ? maxContacts : 1,
        },
        capture.token,
      );

      setJobId(result.job_id);
      setToken(result.token);
      navigate('processing');
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  }

  const entering = direction === 'forward';
  const stepInfo = STEP_MAP[phase];

  return (
    <main className="min-h-screen bg-gradient-to-b from-gray-50 to-white py-8 px-4">
      <div className="max-w-4xl mx-auto space-y-6">

        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold tracking-tight text-text-primary">
            Company/People Intel by URL
          </h1>
          <p className="text-text-secondary max-w-xl mx-auto">
            Extract deep business intelligence from company websites
          </p>
        </div>

        {/* Step breadcrumb */}
        {stepInfo && (
          <div className="flex items-center gap-2 justify-center">
            <div className="flex items-center gap-1.5">
              {[1, 2, 3, 4].map((n) => (
                <div
                  key={n}
                  className={cn(
                    'rounded-full transition-all duration-300',
                    n === stepInfo.step
                      ? 'w-6 h-2.5 bg-primary'
                      : n < stepInfo.step
                      ? 'w-2.5 h-2.5 bg-primary/40'
                      : 'w-2.5 h-2.5 bg-gray-200',
                  )}
                />
              ))}
            </div>
            <span className="text-xs text-text-secondary font-medium">
              Step {stepInfo.step} of {stepInfo.total}:
            </span>
            <span className="text-xs text-text-primary font-semibold">{stepInfo.label}</span>
          </div>
        )}

        {/* Phase content */}
        <div className="relative overflow-hidden">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={phase}
              initial={{ opacity: 0, x: entering ? 48 : -48 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: entering ? -48 : 48 }}
              transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
              className="bg-white rounded-2xl border border-border shadow-sm p-6 sm:p-8"
            >
              {/* ---- PHASE: input (Step 1) ---- */}
              {phase === 'input' && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-lg font-semibold text-text-primary">Upload your data</h2>
                    <p className="text-sm text-text-secondary mt-0.5">
                      Paste a list of URLs or company names, or upload a CSV file.
                    </p>
                  </div>

                  <Tabs value={inputMode} onValueChange={(v) => setInputMode(v as 'paste' | 'csv')} className="w-full">
                    <TabsList className="mb-2">
                      <TabsTrigger value="paste" className="gap-2">
                        <ClipboardPaste className="h-4 w-4" />
                        Paste List
                      </TabsTrigger>
                      <TabsTrigger value="csv" className="gap-2">
                        <Upload className="h-4 w-4" />
                        Upload CSV
                      </TabsTrigger>
                    </TabsList>

                    <TabsContent value="paste">
                      <IntelInputPanel
                        value={inputText}
                        onChange={setInputText}
                        lineStats={lineStats}
                      />
                    </TabsContent>

                    <TabsContent value="csv">
                      <div className="space-y-3">
                        {csvFile ? (
                          <div className="space-y-3">
                            <div className="flex items-center gap-3 rounded-xl border border-border bg-white p-4 shadow-sm">
                              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                                <FileText className="h-5 w-5 text-primary" />
                              </div>
                              <div className="min-w-0 flex-1">
                                <p className="truncate text-sm font-medium text-text-primary">{csvFile.name}</p>
                                <p className="text-xs text-text-secondary">
                                  {csvRows.length.toLocaleString()} rows &middot; {csvHeaders.length} columns
                                </p>
                              </div>
                              <button type="button" onClick={handleRemoveCsv} aria-label="Remove file"
                                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-gray-400 hover:bg-gray-100 hover:text-gray-600">
                                <X className="h-4 w-4" />
                              </button>
                            </div>
                            <div className="space-y-1.5">
                              <label className="text-sm font-medium text-text-primary">
                                Which column contains the URLs or company names?
                              </label>
                              <select value={selectedColumn} onChange={(e) => setSelectedColumn(e.target.value)}
                                className="w-full px-3 py-2 text-sm border border-border rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50">
                                {csvHeaders.map((h) => (<option key={h} value={h}>{h}</option>))}
                              </select>
                              <p className="text-xs text-text-secondary">{lines.length.toLocaleString()} values found in this column</p>
                            </div>
                          </div>
                        ) : (
                          <div onDragOver={(e) => e.preventDefault()}
                            onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleCsvFile(f); }}
                            onClick={() => fileInputRef.current?.click()} role="button" tabIndex={0}
                            onKeyDown={(e) => e.key === 'Enter' && fileInputRef.current?.click()}
                            className="group flex cursor-pointer flex-col items-center justify-center gap-4 rounded-xl border-2 border-dashed border-border px-8 py-12 text-center hover:border-primary/60 hover:bg-gray-50/60 transition-colors">
                            <input ref={fileInputRef} type="file" accept=".csv" className="hidden"
                              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleCsvFile(f); e.target.value = ''; }} />
                            <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-gray-100 text-gray-400 group-hover:bg-primary/10 group-hover:text-primary transition-colors">
                              <Upload className="h-6 w-6" />
                            </div>
                            <div className="space-y-1">
                              <p className="text-sm font-semibold text-text-primary">Drag & drop your CSV file</p>
                              <p className="text-sm text-text-secondary">or <span className="font-medium text-primary underline underline-offset-2">click to browse</span></p>
                              <p className="text-xs text-gray-400">.csv only &mdash; max 50MB</p>
                            </div>
                          </div>
                        )}
                        {csvError && (
                          <div className="flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-600" role="alert">
                            <AlertCircle className="h-4 w-4 shrink-0" />{csvError}
                          </div>
                        )}
                      </div>
                    </TabsContent>
                  </Tabs>

                  <div className="flex justify-end">
                    <Button onClick={() => navigate('configure')} disabled={!hasData} className="gap-2">
                      Continue <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              )}

              {/* ---- PHASE: configure (Step 2) ---- */}
              {phase === 'configure' && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-lg font-semibold text-text-primary">Extraction settings</h2>
                    <p className="text-sm text-text-secondary mt-0.5">
                      Choose what data to extract from {lineStats.total} {lineStats.total === 1 ? 'company' : 'companies'}.
                    </p>
                  </div>

                  <ExtractionSettings
                    industryDescription={industryDescription}
                    targetMarket={targetMarket}
                    companyPeople={companyPeople}
                    homepageRawText={homepageRawText}
                    onIndustryDescriptionChange={setIndustryDescription}
                    onTargetMarketChange={setTargetMarket}
                    onCompanyPeopleChange={setCompanyPeople}
                    onHomepageRawTextChange={setHomepageRawText}
                    quickenrichApiKey={quickenrichApiKey}
                    onQuickenrichApiKeyChange={setQuickenrichApiKey}
                    jobTitles={jobTitles}
                    onJobTitlesChange={setJobTitles}
                    maxContacts={maxContacts}
                    onMaxContactsChange={setMaxContacts}
                    hasCompanyNames={lineStats.names > 0}
                    serperApiKey={serperApiKey}
                    onSerperApiKeyChange={setSerperApiKey}
                  />

                  <div className="flex gap-3 pt-2">
                    <Button variant="outline" onClick={() => navigate('input')}>Back</Button>
                    <Button onClick={() => navigate('submit')} disabled={!canSubmit} className="flex-1 gap-2">
                      Continue <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              )}

              {/* ---- PHASE: submit (Step 3) ---- */}
              {phase === 'submit' && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-lg font-semibold text-text-primary">Almost there!</h2>
                    <p className="text-sm text-text-secondary mt-0.5">
                      Enter your email to start processing{' '}
                      <span className="font-medium text-text-primary">{lineStats.total} companies</span>.
                      We&apos;ll email you when done.
                    </p>
                  </div>

                  <EmailGate onSubmit={handleEmailSubmit} isLoading={isSubmitting} />

                  {submitError && (
                    <p className="text-sm text-red-600" role="alert">{submitError}</p>
                  )}

                  <button type="button" onClick={() => navigate('configure')}
                    className="text-sm text-text-secondary hover:text-text-primary transition-colors flex items-center gap-1">
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                    </svg>
                    Back to settings
                  </button>
                </div>
              )}

              {/* ---- PHASE: processing (Step 4) ---- */}
              {phase === 'processing' && progress && jobId && token && (
                <div className="space-y-8">
                  <div className="text-center space-y-1">
                    <h2 className="text-xl font-semibold text-text-primary">
                      Extracting company intelligence…
                    </h2>
                    <p className="text-sm text-text-secondary">
                      This may take a few minutes. You can keep this tab open or close it — we&apos;ll email you.
                    </p>
                  </div>

                  <ProgressTracker
                    status={progress.status}
                    currentPhase={progress.current_phase}
                    phaseProgress={progress.phase_progress}
                    processedRows={progress.processed_rows}
                    totalRows={progress.total_rows}
                    foundCount={progress.found_count}
                    phases={PIPELINE_PHASES}
                  />

                  <LivePreview
                    jobId={jobId}
                    token={token}
                    isProcessing={progress.status !== 'completed' && progress.status !== 'failed'}
                  />

                  {progress.status === 'failed' && (
                    <p className="text-sm text-red-600 text-center" role="alert">
                      {progress.error ?? 'Processing failed. Please try again.'}
                    </p>
                  )}
                </div>
              )}

              {phase === 'processing' && !progress && (
                <div className="flex flex-col items-center gap-4 py-12 text-text-secondary">
                  <svg className="w-6 h-6 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  <p className="text-sm">Connecting…</p>
                </div>
              )}

              {/* ---- PHASE: results ---- */}
              {phase === 'results' && jobId && token && (
                <div className="space-y-6">
                  <ResultsPanel
                    jobId={jobId}
                    token={token}
                    totalRows={progress?.total_rows ?? 0}
                    foundCount={progress?.found_count ?? 0}
                    enrichedCount={companyPeople ? (progress?.found_count ?? 0) : 0}
                    downloadUrlOverride={getIntelDownloadUrl(jobId, token)}
                  />
                  <div className="text-center">
                    <Button variant="ghost" onClick={() => {
                      clearSession();
                      setPhase("input");
                      setInputText("");
                      handleRemoveCsv();
                    }}>
                      Start a new extraction
                    </Button>
                  </div>
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </main>
  );
}
