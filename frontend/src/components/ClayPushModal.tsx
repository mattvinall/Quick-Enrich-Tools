'use client';

import { useState } from 'react';
import { pushToClay } from '@/lib/api';

interface ClayPushModalProps {
  jobId: string;
  token: string;
  onClose: () => void;
}

type ModalState = 'idle' | 'pushing' | 'done' | 'error';

export default function ClayPushModal({ jobId, token, onClose }: ClayPushModalProps) {
  const [clayApiKey, setClayApiKey] = useState('');
  const [tableId, setTableId] = useState('');
  const [state, setState] = useState<ModalState>('idle');
  const [pushedCount, setPushedCount] = useState(0);
  const [errorMessage, setErrorMessage] = useState('');

  async function handlePush() {
    if (!clayApiKey.trim() || !tableId.trim()) return;
    setState('pushing');
    setErrorMessage('');
    try {
      const result = await pushToClay(jobId, clayApiKey.trim(), tableId.trim(), token);
      setPushedCount(result.pushed_count);
      setState('done');
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'An unexpected error occurred.');
      setState('error');
    }
  }

  function handleOverlayClick(e: React.MouseEvent<HTMLDivElement>) {
    if (e.target === e.currentTarget) onClose();
  }

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
      onClick={handleOverlayClick}
    >
      <div className="bg-white rounded-lg p-6 max-w-md w-full shadow-xl">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-[#1f2937]">Push to Clay</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-[#6b7280] hover:text-[#1f2937] transition-colors text-xl leading-none"
            aria-label="Close modal"
          >
            ×
          </button>
        </div>

        {state === 'done' ? (
          <div className="text-center space-y-4">
            <div className="flex items-center justify-center w-12 h-12 rounded-full bg-green-100 mx-auto">
              <svg
                className="w-6 h-6 text-green-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
                aria-hidden="true"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-[#1f2937] font-medium">
              Successfully pushed {pushedCount} {pushedCount === 1 ? 'row' : 'rows'} to Clay!
            </p>
            <button
              type="button"
              onClick={onClose}
              className="w-full px-4 py-2 text-sm font-medium rounded-md bg-primary text-white hover:bg-primary-hover hover:-translate-y-0.5 transition-all duration-150"
            >
              Close
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-1">
              <label
                htmlFor="clay-api-key"
                className="block text-sm font-medium text-[#1f2937]"
              >
                Clay API Key
              </label>
              <input
                id="clay-api-key"
                type="password"
                value={clayApiKey}
                onChange={(e) => setClayApiKey(e.target.value)}
                placeholder="••••••••••••••••"
                disabled={state === 'pushing'}
                className="w-full px-3 py-2 text-sm border border-[#e5e7eb] rounded-md bg-white text-[#1f2937] placeholder:text-[#9ca3af] focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-50 disabled:cursor-not-allowed"
              />
            </div>

            <div className="space-y-1">
              <label
                htmlFor="clay-table-id"
                className="block text-sm font-medium text-[#1f2937]"
              >
                Table ID
              </label>
              <input
                id="clay-table-id"
                type="text"
                value={tableId}
                onChange={(e) => setTableId(e.target.value)}
                placeholder="e.g. tbl_abc123"
                disabled={state === 'pushing'}
                className="w-full px-3 py-2 text-sm border border-[#e5e7eb] rounded-md bg-white text-[#1f2937] placeholder:text-[#9ca3af] focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-50 disabled:cursor-not-allowed"
              />
            </div>

            {state === 'error' && (
              <p className="text-sm text-red-600" role="alert">
                {errorMessage}
              </p>
            )}

            <button
              type="button"
              onClick={handlePush}
              disabled={state === 'pushing' || !clayApiKey.trim() || !tableId.trim()}
              className="w-full px-4 py-2 text-sm font-medium rounded-md bg-primary text-white hover:bg-primary-hover hover:-translate-y-0.5 transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed disabled:translate-y-0"
            >
              {state === 'pushing' ? 'Pushing...' : 'Push to Clay'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
