'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import UploadZone from '@/components/UploadZone';
import ColumnMapper, { autoDetectColumns } from '@/components/ColumnMapper';
import ConfigPanel from '@/components/ConfigPanel';
import SubmitForm from '@/components/SubmitForm';
import ProgressTracker from '@/components/ProgressTracker';
import LivePreview from '@/components/LivePreview';
import ResultsPanel from '@/components/ResultsPanel';
import { useSSE } from '@/hooks/useSSE';
import { captureEmail, uploadCSV } from '@/lib/api';

// ---------------------------------------------------------------------------
// Phase state machine
// ---------------------------------------------------------------------------
type Phase = 'input' | 'configure' | 'submit' | 'processing' | 'results';

const PHASE_ORDER: Phase[] = ['input', 'configure', 'submit', 'processing', 'results'];

function phaseIndex(p: Phase): number {
  return PHASE_ORDER.indexOf(p);
}

// ---------------------------------------------------------------------------
// Step breadcrumb config
// ---------------------------------------------------------------------------
interface StepInfo {
  step: number;
  total: number;
  label: string;
}

const STEP_MAP: Partial<Record<Phase, StepInfo>> = {
  input:     { step: 1, total: 4, label: 'Upload your data' },
  configure: { step: 2, total: 4, label: 'Configure columns' },
  submit:    { step: 3, total: 4, label: 'Enter your email' },
  processing:{ step: 4, total: 4, label: 'Processing' },
};

// ---------------------------------------------------------------------------
// Page transition variants
// ---------------------------------------------------------------------------
function getSlideVariants(entering: boolean) {
  return {
    initial:  { opacity: 0, x: entering ? 40 : -40 },
    animate:  { opacity: 1, x: 0 },
    exit:     { opacity: 0, x: entering ? -40 : 40 },
  };
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function CompanyLocationFinderPage() {
  const [phase, setPhase] = useState<Phase>('input');
  const [direction, setDirection] = useState<'forward' | 'back'>('forward');

  // File / CSV
  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [preview, setPreview] = useState<Record<string, string>[]>([]);
  const [allRows, setAllRows] = useState<Record<string, string>[]>([]);

  // Column mapping
  const [companyColumn, setCompanyColumn] = useState('');
  const [locationColumn, setLocationColumn] = useState('');

  // Contact enrichment
  const [enrichContacts, setEnrichContacts] = useState(false);
  const [jobTitles, setJobTitles] = useState<string[]>([]);
  const [maxContacts, setMaxContacts] = useState(3);

  // Job / auth — restore from localStorage if available
  const [jobId, setJobId] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("qe_job_id");
  });
  const [token, setToken] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("qe_token");
  });

  // Submit state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  // Email (kept for potential future use)
  const [email, setEmail] = useState('');

  // Persist job session to localStorage
  useEffect(() => {
    if (jobId && token) {
      localStorage.setItem("qe_job_id", jobId);
      localStorage.setItem("qe_token", token);
    }
  }, [jobId, token]);

  // On mount: if we have a saved job, resume it
  useEffect(() => {
    if (jobId && token && phase === "input") {
      setPhase("processing");
    }
  }, []);

  // SSE progress
  const { progress } = useSSE(
    phase === 'processing' ? jobId : null,
    phase === 'processing' ? token : null,
  );

  // Transition to results when job completes
  useEffect(() => {
    if (phase === 'processing' && progress?.status === 'completed') {
      navigate('results');
    }
  }, [phase, progress?.status]);

  function navigate(next: Phase) {
    setDirection(phaseIndex(next) >= phaseIndex(phase) ? 'forward' : 'back');
    setPhase(next);
  }

  // Clear saved session when starting fresh
  function clearSession() {
    localStorage.removeItem("qe_job_id");
    localStorage.removeItem("qe_token");
    setJobId(null);
    setToken(null);
  }

  // ------------------------------------------------------------------
  // Handlers
  // ------------------------------------------------------------------
  function handleDataReady(
    selectedFile: File | null,
    parsedHeaders: string[],
    parsedRows: Record<string, string>[],
    _rawText?: string,
  ) {
    setFile(selectedFile);
    setHeaders(parsedHeaders);
    setPreview(parsedRows.slice(0, 5));
    setAllRows(parsedRows);

    const detected = autoDetectColumns(parsedHeaders);
    setCompanyColumn(detected.company);
    setLocationColumn(detected.location);

    navigate('configure');
  }

  async function handleSubmit(submittedEmail: string) {
    if (!file) return;
    setEmail(submittedEmail);
    setIsSubmitting(true);
    setSubmitError('');

    try {
      const capture = await captureEmail(
        submittedEmail,
        'company-location-finder',
        'company-location-finder-page',
      );
      const upload = await uploadCSV(
        file,
        {
          companyColumn,
          locationColumn,
          emailCaptureId: capture.email_capture_id,
          enrichContacts,
          jobTitles,
          maxContacts,
        },
        capture.token,
      );

      setJobId(upload.job_id);
      setToken(upload.token);
      navigate('processing');
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : 'Something went wrong. Please try again.',
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  // ------------------------------------------------------------------
  // Step breadcrumb
  // ------------------------------------------------------------------
  const stepInfo = STEP_MAP[phase];

  // ------------------------------------------------------------------
  // Slide variants based on direction
  // ------------------------------------------------------------------
  const entering = direction === 'forward';
  const slideInitial = { opacity: 0, x: entering ? 48 : -48 };
  const slideAnimate = { opacity: 1, x: 0 };
  const slideExit = { opacity: 0, x: entering ? -48 : 48 };

  return (
    <main className="min-h-screen bg-gradient-to-b from-gray-50 to-white py-8 px-4">
      <div className="max-w-4xl mx-auto space-y-6">

        {/* ----------------------------------------------------------------
            Header
        ----------------------------------------------------------------- */}
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold tracking-tight text-text-primary">
            Company + Location Website Finder
          </h1>
          <p className="text-text-secondary max-w-xl mx-auto">
            Find the exact company website by matching name + location
          </p>
        </div>

        {/* ----------------------------------------------------------------
            Step breadcrumb
        ----------------------------------------------------------------- */}
        {stepInfo && (
          <div className="flex items-center gap-2 justify-center">
            {/* Step dots */}
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

        {/* ----------------------------------------------------------------
            Phase content card
        ----------------------------------------------------------------- */}
        <div className="relative overflow-hidden">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={phase}
              initial={slideInitial}
              animate={slideAnimate}
              exit={slideExit}
              transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
              className="bg-white rounded-2xl border border-border shadow-sm p-6 sm:p-8"
            >
              {/* ---- PHASE: input ---- */}
              {phase === 'input' && (
                <UploadZone onDataReady={handleDataReady} />
              )}

              {/* ---- PHASE: configure ---- */}
              {phase === 'configure' && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-lg font-semibold text-text-primary">Configure columns</h2>
                    <p className="text-sm text-text-secondary mt-0.5">
                      Map your CSV columns so we know which to use.
                    </p>
                  </div>

                  <ColumnMapper
                    headers={headers}
                    preview={preview}
                    totalRows={allRows.length}
                    companyColumn={companyColumn}
                    locationColumn={locationColumn}
                    onCompanyColumnChange={setCompanyColumn}
                    onLocationColumnChange={setLocationColumn}
                  />

                  <ConfigPanel
                    enrichContacts={enrichContacts}
                    jobTitles={jobTitles}
                    maxContacts={maxContacts}
                    onEnrichContactsChange={setEnrichContacts}
                    onJobTitlesChange={setJobTitles}
                    onMaxContactsChange={setMaxContacts}
                  />

                  <div className="flex gap-3 pt-2">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => navigate('input')}
                    >
                      Back
                    </Button>
                    <Button
                      type="button"
                      disabled={!companyColumn}
                      onClick={() => navigate('submit')}
                      className="flex-1 gap-2"
                    >
                      Continue
                      <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              )}

              {/* ---- PHASE: submit ---- */}
              {phase === 'submit' && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-lg font-semibold text-text-primary">Almost there!</h2>
                    <p className="text-sm text-text-secondary mt-0.5">
                      Enter your email to start processing.{' '}
                      {allRows.length > 0 && (
                        <span>
                          We&apos;ll process your{' '}
                          <span className="font-medium text-text-primary">
                            {allRows.length}+ rows
                          </span>{' '}
                          and email you when done.
                        </span>
                      )}
                    </p>
                  </div>

                  <SubmitForm
                    onSubmit={handleSubmit}
                    isLoading={isSubmitting}
                    rowCount={allRows.length || preview.length}
                  />

                  {submitError && (
                    <p className="text-sm text-red-600" role="alert">
                      {submitError}
                    </p>
                  )}

                  <button
                    type="button"
                    onClick={() => navigate('configure')}
                    className="text-sm text-text-secondary hover:text-text-primary transition-colors flex items-center gap-1"
                  >
                    <svg
                      className="w-3.5 h-3.5"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                      aria-hidden="true"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                    </svg>
                    Back to configuration
                  </button>
                </div>
              )}

              {/* ---- PHASE: processing ---- */}
              {phase === 'processing' && progress && jobId && token && (
                <div className="space-y-8">
                  <div className="text-center space-y-1">
                    <h2 className="text-xl font-semibold text-text-primary">
                      Processing your file…
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

                  <LivePreview jobId={jobId} token={token} isProcessing={progress.status !== 'completed' && progress.status !== 'failed'} />

                  {progress.status === 'failed' && (
                    <p className="text-sm text-red-600 text-center" role="alert">
                      {progress.error ?? 'Processing failed. Please try again.'}
                    </p>
                  )}
                </div>
              )}

              {/* ---- PHASE: processing (no progress yet) ---- */}
              {phase === 'processing' && !progress && (
                <div className="flex flex-col items-center gap-4 py-12 text-text-secondary">
                  <svg
                    className="w-6 h-6 animate-spin"
                    fill="none"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8v8H4z"
                    />
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
                    enrichedCount={enrichContacts ? (progress?.found_count ?? 0) : 0}
                  />
                  <div className="text-center">
                    <Button
                      variant="ghost"
                      onClick={() => {
                        clearSession();
                        setPhase("input");
                        setFile(null);
                        setHeaders([]);
                        setPreview([]);
                        setAllRows([]);
                      }}
                    >
                      Start a new job
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
