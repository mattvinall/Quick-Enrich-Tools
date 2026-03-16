'use client';

import { useState } from 'react';
import { getDownloadUrl } from '@/lib/api';
import ClayPushModal from './ClayPushModal';

interface ResultsPanelProps {
  jobId: string;
  token: string;
  totalRows: number;
  foundCount: number;
}

export default function ResultsPanel({ jobId, token, totalRows, foundCount }: ResultsPanelProps) {
  const [showClay, setShowClay] = useState(false);

  const matchRate = totalRows > 0 ? Math.round((foundCount / totalRows) * 100) : 0;
  const downloadUrl = getDownloadUrl(jobId, token);

  return (
    <div className="flex flex-col items-center text-center space-y-6">
      {/* Green checkmark circle */}
      <div className="flex items-center justify-center w-16 h-16 rounded-full bg-green-100">
        <svg
          className="w-8 h-8 text-green-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      </div>

      {/* Heading */}
      <div className="space-y-1">
        <h2 className="text-2xl font-bold text-[#1f2937]">Processing Complete!</h2>
        <p className="text-[#6b7280] text-sm">Your enriched data is ready to download.</p>
      </div>

      {/* Stats */}
      <div className="bg-[#f9fafb] border border-[#e5e7eb] rounded-lg px-8 py-4 space-y-1">
        <p className="text-[#1f2937] font-medium text-lg">
          Found{' '}
          <span className="text-green-600 font-bold">{foundCount}</span>
          {' '}of{' '}
          <span className="font-bold">{totalRows}</span>
          {' '}websites
        </p>
        <p className="text-[#6b7280] text-sm">{matchRate}% match rate</p>
      </div>

      {/* Action buttons */}
      <div className="flex flex-col sm:flex-row gap-3 w-full max-w-sm">
        <a
          href={downloadUrl}
          download
          className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-md bg-primary text-white hover:bg-primary-hover hover:-translate-y-0.5 transition-all duration-150"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
            />
          </svg>
          Download CSV
        </a>

        <button
          type="button"
          onClick={() => setShowClay(true)}
          className="flex-1 px-4 py-2 text-sm font-medium rounded-md border border-[#e5e7eb] bg-white text-[#1f2937] hover:bg-[#f9fafb] hover:-translate-y-0.5 transition-all duration-150"
        >
          Push to Clay
        </button>
      </div>

      {/* Footer note */}
      <p className="text-xs text-[#9ca3af]">
        A copy of your results has also been sent to your email.
      </p>

      {showClay && (
        <ClayPushModal
          jobId={jobId}
          token={token}
          onClose={() => setShowClay(false)}
        />
      )}
    </div>
  );
}
