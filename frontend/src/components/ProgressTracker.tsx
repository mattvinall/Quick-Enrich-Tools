'use client';

const PHASES = ['Search', 'Verify', 'Normalize', 'Enrich', 'Deliver'] as const;
type Phase = (typeof PHASES)[number];

interface PhaseEntry {
  done: number;
  total: number;
}

interface ProgressTrackerProps {
  status: string;
  currentPhase: string | null;
  phaseProgress: Record<string, PhaseEntry>;
  processedRows: number;
  totalRows: number;
  foundCount: number;
}

function phaseIndex(phase: string | null): number {
  if (!phase) return -1;
  return PHASES.findIndex(
    (p) => p.toLowerCase() === phase.toLowerCase(),
  );
}

export default function ProgressTracker({
  status,
  currentPhase,
  phaseProgress,
  processedRows,
  totalRows,
  foundCount,
}: ProgressTrackerProps) {
  const currentIndex = phaseIndex(currentPhase);
  const isComplete = status === 'completed';

  const activeIndex = isComplete ? PHASES.length : currentIndex;

  const currentEntry: PhaseEntry | undefined =
    currentPhase ? phaseProgress[currentPhase] : undefined;

  const barPercent =
    currentEntry && currentEntry.total > 0
      ? Math.round((currentEntry.done / currentEntry.total) * 100)
      : isComplete
        ? 100
        : 0;

  return (
    <div className="space-y-6">
      {/* Phase step indicator */}
      <div className="flex items-center">
        {PHASES.map((phase, idx) => {
          const isPast = idx < activeIndex;
          const isCurrent = idx === activeIndex;

          return (
            <div key={phase} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center gap-1">
                <div
                  className={[
                    'w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold text-white flex-shrink-0',
                    isPast
                      ? 'bg-green-500'
                      : isCurrent
                        ? 'bg-primary'
                        : 'bg-gray-200',
                  ].join(' ')}
                >
                  {isPast ? (
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={3}
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                  ) : (
                    <span className={isCurrent ? '' : 'text-gray-400'}>
                      {idx + 1}
                    </span>
                  )}
                </div>
                <span
                  className={[
                    'text-xs font-medium whitespace-nowrap',
                    isPast
                      ? 'text-green-600'
                      : isCurrent
                        ? 'text-primary'
                        : 'text-gray-400',
                  ].join(' ')}
                >
                  {phase}
                </span>
              </div>

              {/* Connecting line */}
              {idx < PHASES.length - 1 && (
                <div
                  className={[
                    'h-0.5 flex-1 mx-1 mb-5',
                    idx < activeIndex ? 'bg-green-400' : 'bg-gray-200',
                  ].join(' ')}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Progress bar for current phase */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-text-secondary">
          <span>
            {isComplete
              ? 'Complete'
              : currentPhase
                ? `Phase: ${currentPhase}`
                : 'Waiting…'}
          </span>
          <span>{barPercent}%</span>
        </div>
        <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-primary rounded-full transition-all duration-500"
            style={{ width: `${barPercent}%` }}
          />
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <p className="text-2xl font-bold text-text-primary">{processedRows}</p>
          <p className="text-xs text-text-secondary mt-0.5">Processed</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <p className="text-2xl font-bold text-green-600">{foundCount}</p>
          <p className="text-xs text-text-secondary mt-0.5">Found</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <p className="text-2xl font-bold text-text-primary">{totalRows}</p>
          <p className="text-xs text-text-secondary mt-0.5">Total Rows</p>
        </div>
      </div>
    </div>
  );
}
