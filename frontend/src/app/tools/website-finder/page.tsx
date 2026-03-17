'use client';

import { useState, useEffect } from 'react';
import UploadZone from '@/components/UploadZone';
import ColumnMapper, { autoDetectColumns } from '@/components/ColumnMapper';
import ConfigPanel from '@/components/ConfigPanel';
import EmailGate from '@/components/EmailGate';
import ResultsPanel from '@/components/ResultsPanel';
import { useSSE } from '@/hooks/useSSE';
import { captureEmail, uploadCSV } from '@/lib/api';

type Phase = 'upload' | 'config' | 'email' | 'processing' | 'results';

export default function WebsiteFinderPage() {
  const [phase, setPhase] = useState<Phase>('upload');

  // File & CSV state
  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [preview, setPreview] = useState<Record<string, string>[]>([]);
  const [totalRows, setTotalRows] = useState(0);

  // Column config
  const [companyColumn, setCompanyColumn] = useState('');
  const [locationColumn, setLocationColumn] = useState('');

  // Enrich config
  const [enrichContacts, setEnrichContacts] = useState(false);
  const [jobTitles, setJobTitles] = useState<string[]>([]);
  const [maxContacts, setMaxContacts] = useState(3);

  // Job state
  const [jobId, setJobId] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);

  // Submission state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  // SSE progress
  const { progress } = useSSE(
    phase === 'processing' ? jobId : null,
    phase === 'processing' ? token : null,
  );

  // Move to results when job completes
  useEffect(() => {
    if (phase === 'processing' && progress?.status === 'completed') {
      setPhase('results');
    }
  }, [phase, progress?.status]);

  function handleDataReady(
    selectedFile: File | null,
    parsedHeaders: string[],
    parsedRows: Record<string, string>[],
    _rawText?: string,
  ) {
    setFile(selectedFile);
    setHeaders(parsedHeaders);
    setPreview(parsedRows);
    setTotalRows(parsedRows.length);

    const detected = autoDetectColumns(parsedHeaders);
    setCompanyColumn(detected.company);
    setLocationColumn(detected.location);

    setPhase('config');
  }

  async function handleEmailSubmit(email: string) {
    if (!file) return;
    setIsSubmitting(true);
    setSubmitError('');

    try {
      const capture = await captureEmail(email, 'website-finder', 'website-finder-page');
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
      setPhase('processing');
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f9fafb] py-12 px-4">
      <div className="max-w-3xl mx-auto space-y-8">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold text-[#1f2937]">Website Finder</h1>
          <p className="text-[#6b7280]">
            Upload a CSV of companies and we&apos;ll find their websites automatically.
          </p>
        </div>

        {/* Card */}
        <div className="bg-white border border-[#e5e7eb] rounded-xl shadow-sm p-6 sm:p-8">
          {/* Upload phase */}
          {phase === 'upload' && (
            <UploadZone onDataReady={handleDataReady} />
          )}

          {/* Config phase */}
          {phase === 'config' && (
            <div className="space-y-6">
              <ColumnMapper
                headers={headers}
                preview={preview}
                totalRows={totalRows}
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
                <button
                  type="button"
                  onClick={() => setPhase('upload')}
                  className="px-4 py-2 text-sm font-medium rounded-md border border-[#e5e7eb] bg-white text-[#1f2937] hover:bg-[#f9fafb] transition-colors"
                >
                  Back
                </button>
                <button
                  type="button"
                  disabled={!companyColumn}
                  onClick={() => setPhase('email')}
                  className="flex-1 px-4 py-2 text-sm font-medium rounded-md bg-primary text-white hover:bg-primary-hover hover:-translate-y-0.5 transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed disabled:translate-y-0"
                >
                  Continue
                </button>
              </div>
            </div>
          )}

          {/* Email gate phase */}
          {phase === 'email' && (
            <div className="space-y-4">
              <button
                type="button"
                onClick={() => setPhase('config')}
                className="text-sm text-[#6b7280] hover:text-[#1f2937] transition-colors flex items-center gap-1"
              >
                <svg
                  className="w-4 h-4"
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

              <EmailGate onSubmit={handleEmailSubmit} isLoading={isSubmitting} />

              {submitError && (
                <p className="text-sm text-red-600" role="alert">
                  {submitError}
                </p>
              )}
            </div>
          )}

          {/* Processing phase */}
          {phase === 'processing' && progress && (
            <div className="space-y-6">
              <div className="text-center space-y-1">
                <h2 className="text-xl font-semibold text-[#1f2937]">Processing your file…</h2>
                <p className="text-sm text-[#6b7280]">This may take a few minutes.</p>
              </div>

              {/* Progress bar */}
              <div className="space-y-2">
                <div className="flex justify-between text-sm text-[#6b7280]">
                  <span>{progress.current_phase ?? 'Working…'}</span>
                  <span>
                    {progress.processed_rows} / {progress.total_rows}
                  </span>
                </div>
                <div className="w-full bg-[#e5e7eb] rounded-full h-2">
                  <div
                    className="bg-primary h-2 rounded-full transition-all duration-500"
                    style={{
                      width:
                        progress.total_rows > 0
                          ? `${Math.round((progress.processed_rows / progress.total_rows) * 100)}%`
                          : '0%',
                    }}
                  />
                </div>
              </div>

              {/* Live stats */}
              <div className="grid grid-cols-2 gap-4 text-center">
                <div className="bg-[#f9fafb] rounded-lg p-4">
                  <p className="text-2xl font-bold text-green-600">{progress.found_count}</p>
                  <p className="text-xs text-[#6b7280] mt-1">Websites found</p>
                </div>
                <div className="bg-[#f9fafb] rounded-lg p-4">
                  <p className="text-2xl font-bold text-[#1f2937]">{progress.processed_rows}</p>
                  <p className="text-xs text-[#6b7280] mt-1">Rows processed</p>
                </div>
              </div>

              {progress.status === 'failed' && (
                <p className="text-sm text-red-600 text-center" role="alert">
                  {progress.error ?? 'Processing failed. Please try again.'}
                </p>
              )}
            </div>
          )}

          {/* Results phase */}
          {phase === 'results' && jobId && token && progress && (
            <ResultsPanel
              jobId={jobId}
              token={token}
              totalRows={progress.total_rows}
              foundCount={progress.found_count}
              enrichedCount={progress.enriched_count ?? 0}
            />
          )}
        </div>
      </div>
    </main>
  );
}
