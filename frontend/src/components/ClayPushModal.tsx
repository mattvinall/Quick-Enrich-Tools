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
  const [webhookUrl, setWebhookUrl] = useState('');
  const [status, setStatus] = useState<ModalStatus>('idle');
  const [pushedCount, setPushedCount] = useState(0);
  const [errorMessage, setErrorMessage] = useState('');

  function handleOpenChange(next: boolean) {
    if (!next) onClose();
  }

  async function handlePush() {
    if (!webhookUrl.trim()) return;
    setStatus('pushing');
    setErrorMessage('');
    try {
      const result = await pushToClay(jobId, webhookUrl.trim(), token);
      setPushedCount(result.pushed_count);
      setStatus('done');
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'An unexpected error occurred.');
      setStatus('error');
    }
  }

  const isPushing = status === 'pushing';
  const canSubmit = webhookUrl.trim().length > 0 && !isPushing;

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
                Paste your Clay table webhook URL to send the enriched results directly.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-2">
              <div className="space-y-1.5">
                <label
                  htmlFor="clay-webhook"
                  className="text-sm font-medium text-text-primary"
                >
                  Clay Webhook URL
                </label>
                <Input
                  id="clay-webhook"
                  type="url"
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  placeholder="https://hooks.clay.com/..."
                  disabled={isPushing}
                />
                <p className="text-xs text-text-secondary">
                  In Clay, create a webhook source on your table and paste the URL here.
                </p>
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
