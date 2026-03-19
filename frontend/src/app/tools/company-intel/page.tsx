'use client';

import { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Building2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

import IntelInputPanel, { computeLineStats } from '@/components/IntelInputPanel';
import ExtractionSettings from '@/components/ExtractionSettings';
import EmailGate from '@/components/EmailGate';
import ProgressTracker from '@/components/ProgressTracker';
import LivePreview from '@/components/LivePreview';
import ResultsPanel from '@/components/ResultsPanel';
import { useSSE } from '@/hooks/useSSE';
import { captureEmail, submitExtraction, getIntelDownloadUrl } from '@/lib/api';

type Phase = 'input' | 'submit' | 'processing' | 'results';

const PHASE_ORDER: Phase[] = ['input', 'submit', 'processing', 'results'];

function phaseIndex(p: Phase): number {
  return PHASE_ORDER.indexOf(p);
}

export default function CompanyIntelPage() {
  const [phase, setPhase] = useState<Phase>('input');
  const [direction, setDirection] = useState<'forward' | 'back'>('forward');

  // Input
  const [inputText, setInputText] = useState('');
  const lineStats = useMemo(() => computeLineStats(inputText), [inputText]);

  // Extraction options
  const [industryDescription, setIndustryDescription] = useState(true);
  const [targetMarket, setTargetMarket] = useState(true);
  const [companyPeople, setCompanyPeople] = useState(true);
  const [homepageRawText, setHomepageRawText] = useState(false);

  // API keys
  const [quickenrichApiKey, setQuickenrichApiKey] = useState('');
  const [serperApiKey, setSerperApiKey] = useState('');

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
  const canSubmit = lineStats.total > 0 &&
    (industryDescription || targetMarket || companyPeople || homepageRawText) &&
    (!companyPeople || quickenrichApiKey.trim()) &&
    (lineStats.names === 0 || serperApiKey.trim());

  async function handleEmailSubmit(email: string) {
    setIsSubmitting(true);
    setSubmitError('');

    try {
      const capture = await captureEmail(email, 'company-intel', 'company-intel-page');

      const lines = inputText.split('\n').filter((l) => l.trim());

      const result = await submitExtraction(
        {
          lines,
          options: {
            industry_description: industryDescription,
            target_market: targetMarket,
            company_people: companyPeople,
            homepage_raw_text: homepageRawText,
          },
          serper_api_key: serperApiKey,
          quickenrich_api_key: quickenrichApiKey,
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

  return (
    <main className="min-h-screen bg-gradient-to-b from-gray-50 to-white py-8 px-4">
      <div className="max-w-5xl mx-auto space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <Search className="w-5 h-5 text-primary" />
            </div>
            <h1 className="text-xl font-bold text-text-primary">
              Company/People Intel by URL
            </h1>
          </div>
          <div className="flex items-center gap-2 text-sm text-text-secondary">
            <Building2 className="w-4 h-4" />
            <span>Company Intelligence</span>
          </div>
        </div>

        {/* Content */}
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={phase}
            initial={{ opacity: 0, x: entering ? 40 : -40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: entering ? -40 : 40 }}
            transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
          >
            {/* ---- PHASE: input ---- */}
            {phase === 'input' && (
              <div className="bg-white rounded-2xl border border-border shadow-sm p-6 sm:p-8 space-y-6">
                <div>
                  <h2 className="text-2xl font-bold text-text-primary">Extract Deep Insights</h2>
                  <p className="text-text-secondary mt-1">
                    Paste a list of URLs or company names (one per line). We&apos;ll automatically determine
                    if we need to search for the website or scrape it directly to gather the intelligence you need.
                  </p>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
                  {/* Textarea — 3 cols */}
                  <div className="lg:col-span-3">
                    <IntelInputPanel
                      value={inputText}
                      onChange={setInputText}
                      lineStats={lineStats}
                    />
                  </div>

                  {/* Settings — 2 cols */}
                  <div className="lg:col-span-2">
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
                      serperApiKey={serperApiKey}
                      onSerperApiKeyChange={setSerperApiKey}
                      showSerperKey={lineStats.names > 0}
                    />
                  </div>
                </div>

                <div className="flex justify-end">
                  <Button
                    onClick={() => navigate('submit')}
                    disabled={!canSubmit}
                    className="px-8 py-2.5 gap-2"
                  >
                    <Search className="w-4 h-4" />
                    Run Extraction
                  </Button>
                </div>
              </div>
            )}

            {/* ---- PHASE: submit ---- */}
            {phase === 'submit' && (
              <div className="bg-white rounded-2xl border border-border shadow-sm p-6 sm:p-8 max-w-lg mx-auto space-y-6">
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

                <button
                  type="button"
                  onClick={() => navigate('input')}
                  className="text-sm text-text-secondary hover:text-text-primary transition-colors flex items-center gap-1"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                  </svg>
                  Back to configuration
                </button>
              </div>
            )}

            {/* ---- PHASE: processing ---- */}
            {phase === 'processing' && progress && jobId && token && (
              <div className="bg-white rounded-2xl border border-border shadow-sm p-6 sm:p-8 space-y-8">
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
              <div className="bg-white rounded-2xl border border-border shadow-sm p-6 sm:p-8">
                <div className="flex flex-col items-center gap-4 py-12 text-text-secondary">
                  <svg className="w-6 h-6 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  <p className="text-sm">Connecting…</p>
                </div>
              </div>
            )}

            {/* ---- PHASE: results ---- */}
            {phase === 'results' && jobId && token && (
              <div className="bg-white rounded-2xl border border-border shadow-sm p-6 sm:p-8 space-y-6">
                <ResultsPanel
                  jobId={jobId}
                  token={token}
                  totalRows={progress?.total_rows ?? 0}
                  foundCount={progress?.found_count ?? 0}
                  enrichedCount={companyPeople ? (progress?.found_count ?? 0) : 0}
                  downloadUrlOverride={getIntelDownloadUrl(jobId, token)}
                />
                <div className="text-center">
                  <Button
                    variant="ghost"
                    onClick={() => {
                      clearSession();
                      setPhase("input");
                      setInputText("");
                    }}
                  >
                    Start a new extraction
                  </Button>
                </div>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </main>
  );
}
