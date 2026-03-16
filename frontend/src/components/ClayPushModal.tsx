'use client';

import { useState } from 'react';
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { pushToClay } from '@/lib/api';

interface ClayPushModalProps {
  jobId: string;
  token: string;
  onClose: () => void;
  open: boolean;
}

type ModalStatus = 'idle' | 'pushing' | 'done' | 'error';

export default function ClayPushModal({ jobId, token, onClose, open }: ClayPushModalProps) {
  const [clayApiKey, setClayApiKey] = useState('');
  const [tableId, setTableId] = useState('');
  const [status, setStatus] = useState<ModalStatus>('idle');
  const [pushedCount, setPushedCount] = useState(0);
  const [errorMessage, setErrorMessage] = useState('');

  function handleOpenChange(next: boolean) {
    if (!next) onClose();
  }

  async function handlePush() {
    if (!clayApiKey.trim() || !tableId.trim()) return;
    setStatus('pushing');
    setErrorMessage('');
    try {
      const result = await pushToClay(jobId, clayApiKey.trim(), tableId.trim(), token);
      setPushedCount(result.pushed_count);
      setStatus('done');
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'An unexpected error occurred.');
      setStatus('error');
    }
  }

  const isPushing = status === 'pushing';
  const canSubmit = clayApiKey.trim().length > 0 && tableId.trim().length > 0 && !isPushing;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-md">
        {status === 'done' ? (
          <>
            <DialogHeader className="items-center text-center">
              <div className="flex items-center justify-center w-12 h-12 rounded-full bg-green-100 mx-auto mb-2">
                <CheckCircle2 className="w-6 h-6 text-green-600" />
              </div>
              <DialogTitle>Pushed to Clay!</DialogTitle>
              <DialogDescription>
                Successfully pushed{' '}
                <span className="font-semibold text-text-primary">
                  {pushedCount} {pushedCount === 1 ? 'row' : 'rows'}
                </span>{' '}
                to your Clay table.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="pt-2">
              <Button className="w-full" onClick={onClose}>
                Done
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Push to Clay</DialogTitle>
              <DialogDescription>
                Send your enriched results directly to a Clay table.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-2">
              <div className="space-y-1.5">
                <label
                  htmlFor="clay-api-key"
                  className="text-sm font-medium text-text-primary"
                >
                  Clay API Key
                </label>
                <Input
                  id="clay-api-key"
                  type="password"
                  value={clayApiKey}
                  onChange={(e) => setClayApiKey(e.target.value)}
                  placeholder="••••••••••••••••"
                  disabled={isPushing}
                  autoComplete="off"
                />
              </div>

              <div className="space-y-1.5">
                <label
                  htmlFor="clay-table-id"
                  className="text-sm font-medium text-text-primary"
                >
                  Table ID
                </label>
                <Input
                  id="clay-table-id"
                  type="text"
                  value={tableId}
                  onChange={(e) => setTableId(e.target.value)}
                  placeholder="e.g. tbl_abc123"
                  disabled={isPushing}
                />
              </div>

              {status === 'error' && (
                <div
                  role="alert"
                  className={cn(
                    'flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700',
                  )}
                >
                  <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  <span>{errorMessage}</span>
                </div>
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={onClose} disabled={isPushing}>
                Cancel
              </Button>
              <Button onClick={handlePush} disabled={!canSubmit}>
                {isPushing ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Pushing…
                  </>
                ) : (
                  'Push to Clay'
                )}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
