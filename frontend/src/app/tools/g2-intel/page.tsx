'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import G2CategorySelector from '@/components/G2CategorySelector';
import ExtractionSettings from '@/components/ExtractionSettings';
import EmailGate from '@/components/EmailGate';
import ProgressTracker from '@/components/ProgressTracker';
import LivePreview from '@/components/LivePreview';
import ResultsPanel from '@/components/ResultsPanel';
import { useSSE } from '@/hooks/useSSE';
import { captureEmail, submitG2Extraction, getG2DownloadUrl } from '@/lib/api';

type Phase = 'categories' | 'configure' | 'submit' | 'processing' | 'results';

const PHASE_ORDER: Phase[] = ['categories', 'configure', 'submit', 'processing', 'results'];

const PIPELINE_PHASES = ['Discover', 'Resolve', 'Crawl', 'Extract', 'Enrich', 'Deliver'] as const;

const STEP_MAP: Partial<Record<Phase, { step: number; total: number; label: string }>> = {
  categories: { step: 1, total: 4, label: 'Select G2 categories' },
  configure:  { step: 2, total: 4, label: 'Extraction settings' },
  submit:     { step: 3, total: 4, label: 'Enter your email' },
  processing: { step: 4, total: 4, label: 'Processing' },
};

function phaseIndex(p: Phase): number {
  return PHASE_ORDER.indexOf(p);
}

export default function G2IntelPage() {
  const [phase, setPhase] = useState<Phase>('categories');
  const [direction, setDirection] = useState<'forward' | 'back'>('forward');

  // Category selection
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [maxPerCategory, setMaxPerCategory] = useState(250);

  // Extraction options
  const [industryDescription, setIndustryDescription] = useState(true);
  const [targetMarket, setTargetMarket] = useState(true);
  const [companyPeople, setCompanyPeople] = useState(true);
  const [homepageRawText, setHomepageRawText] = useState(false);

  // QuickEnrich API key
  const [quickenrichApiKey, setQuickenrichApiKey] = useState('');
  const [serperApiKey, setSerperApiKey] = useState('');

  // Contact config
  const [jobTitles, setJobTitles] = useState<string[]>(['CEO', 'Founder']);
  const [maxContacts, setMaxContacts] = useState(3);

  // Job state — restore from localStorage
  const [jobId, setJobId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('qe_g2_job_id');
  });
  const [token, setToken] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('qe_g2_token');
  });

  // Submit state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  // Persist job session
  useEffect(() => {
    if (jobId && token) {
      localStorage.setItem('qe_g2_job_id', jobId);
      localStorage.setItem('qe_g2_token', token);
    }
  }, [jobId, token]);

  // Resume saved job on mount
  useEffect(() => {
    if (jobId && token && phase === 'categories') {
      setPhase('processing');
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
    localStorage.removeItem('qe_g2_job_id');
    localStorage.removeItem('qe_g2_token');
    setJobId(null);
    setToken(null);
  }

  // Validation
  const hasCategories = selectedCategories.length > 0;
  const hasOptions = industryDescription || targetMarket || companyPeople || homepageRawText;
  const canSubmit = hasCategories && hasOptions;

  async function handleEmailSubmit(email: string) {
    setIsSubmitting(true);
    setSubmitError('');

    try {
      const capture = await captureEmail(email, 'g2-intel', 'g2-intel-page');

      const result = await submitG2Extraction(
        {
          categories: selectedCategories,
          max_per_category: maxPerCategory,
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
            G2 Category to Company Intel
          </h1>
          <p className="text-text-secondary max-w-xl mx-auto">
            Select G2 software categories to discover companies and extract business intelligence
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
              {/* ---- PHASE: categories (Step 1) ---- */}
              {phase === 'categories' && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-lg font-semibold text-text-primary">Select G2 categories</h2>
                    <p className="text-sm text-text-secondary mt-0.5">
                      Choose software categories to discover companies listed on G2.
                    </p>
                  </div>

                  <G2CategorySelector
                    selectedSlugs={selectedCategories}
                    onSelectionChange={setSelectedCategories}
                    maxPerCategory={maxPerCategory}
                    onMaxPerCategoryChange={setMaxPerCategory}
                  />

                  <div className="flex justify-end">
                    <Button onClick={() => navigate('configure')} disabled={!hasCategories} className="gap-2">
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
                      Choose what data to extract from discovered companies.
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
                    hasCompanyNames={true}
                    quickenrichApiKey={quickenrichApiKey}
                    onQuickenrichApiKeyChange={setQuickenrichApiKey}
                    serperApiKey={serperApiKey}
                    onSerperApiKeyChange={setSerperApiKey}
                    jobTitles={jobTitles}
                    onJobTitlesChange={setJobTitles}
                    maxContacts={maxContacts}
                    onMaxContactsChange={setMaxContacts}
                  />

                  <div className="flex gap-3 pt-2">
                    <Button variant="outline" onClick={() => navigate('categories')}>Back</Button>
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
                      Enter your email to start discovering companies from{' '}
                      <span className="font-medium text-text-primary">
                        {selectedCategories.length} G2 {selectedCategories.length === 1 ? 'category' : 'categories'}
                      </span>.
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
                      Discovering & extracting company intelligence…
                    </h2>
                    <p className="text-sm text-text-secondary">
                      This may take a while for large categories. You can keep this tab open or close it — we&apos;ll email you.
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
                    enrichedCount={progress?.enriched_count ?? 0}
                    downloadUrlOverride={getG2DownloadUrl(jobId, token)}
                  />
                  <div className="text-center">
                    <Button variant="ghost" onClick={() => {
                      clearSession();
                      setPhase('categories');
                      setSelectedCategories([]);
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
