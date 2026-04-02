'use client';

import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, ShieldCheck, Filter, Users, Send, Check, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';

import { Globe, Cpu, Layers } from 'lucide-react';

const DEFAULT_PHASES = ['Search', 'Verify', 'Normalize', 'Enrich', 'Deliver'] as const;

const ALL_PHASE_ICONS: Record<string, React.ElementType> = {
  Search: Search,
  Verify: ShieldCheck,
  Normalize: Filter,
  Enrich: Users,
  Deliver: Send,
  Resolve: Search,
  Crawl: Globe,
  Extract: Cpu,
  Discover: Layers,
};

const ALL_PHASE_LABELS: Record<string, string> = {
  Search: 'Searching',
  Verify: 'Verifying',
  Normalize: 'Normalizing',
  Enrich: 'Enriching',
  Deliver: 'Delivering',
  Resolve: 'Resolving',
  Crawl: 'Crawling',
  Extract: 'Extracting',
  Discover: 'Discovering',
};

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
  phases?: readonly string[];
}

// Map backend phase names to display phase names
const PHASE_ALIASES: Record<string, string> = {
  g2_scrape: 'discover',
  maps_search: 'search',
};

function findPhaseIndex(phases: readonly string[], phase: string | null): number {
  if (!phase) return -1;
  const normalized = PHASE_ALIASES[phase.toLowerCase()] ?? phase.toLowerCase();
  return phases.findIndex((p) => p.toLowerCase() === normalized);
}

// Animated counter that smoothly increments to the target value
function AnimatedNumber({
  value,
  className,
}: {
  value: number;
  className?: string;
}) {
  const [displayed, setDisplayed] = useState(value);
  const prevRef = useRef(value);

  useEffect(() => {
    const from = prevRef.current;
    const to = value;
    prevRef.current = value;

    if (from === to) return;

    const steps = 20;
    const stepMs = 30;
    let step = 0;

    const id = setInterval(() => {
      step++;
      const progress = step / steps;
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplayed(Math.round(from + (to - from) * eased));
      if (step >= steps) {
        clearInterval(id);
        setDisplayed(to);
      }
    }, stepMs);

    return () => clearInterval(id);
  }, [value]);

  return <span className={className}>{(displayed ?? 0).toLocaleString()}</span>;
}

export default function ProgressTracker({
  status,
  currentPhase,
  phaseProgress,
  processedRows,
  totalRows,
  foundCount,
  phases = DEFAULT_PHASES,
}: ProgressTrackerProps) {
  const currentIndex = findPhaseIndex(phases, currentPhase);
  const isComplete = status === 'completed';
  const activeIndex = isComplete ? phases.length : currentIndex;

  const currentEntry: PhaseEntry | undefined = currentPhase && phaseProgress
    ? phaseProgress[currentPhase]
    : undefined;

  const barPercent =
    currentEntry && currentEntry.total > 0
      ? Math.round((currentEntry.done / currentEntry.total) * 100)
      : isComplete
        ? 100
        : 0;

  const matchRate =
    totalRows > 0 ? Math.round((foundCount / totalRows) * 100) : 0;

  // Phase label for the progress section
  const activePhase = isComplete
    ? null
    : phases[activeIndex] ?? null;
  const progressLabel = isComplete
    ? 'Complete'
    : activePhase
      ? `${ALL_PHASE_LABELS[activePhase] ?? activePhase}…`
      : 'Waiting…';

  // Simple ETA: remaining rows at current throughput (rough)
  const etaLabel = (() => {
    if (isComplete || processedRows === 0 || totalRows === 0) return null;
    const remaining = totalRows - processedRows;
    if (remaining <= 0) return null;
    // Estimate ~2s per row processed so far
    return `~${remaining} remaining`;
  })();

  return (
    <div className="space-y-5">
      {/* Phase Stepper */}
      <div className="flex items-start">
        {phases.map((phase, idx) => {
          const isPast = idx < activeIndex;
          const isCurrent = idx === activeIndex;
          const Icon = ALL_PHASE_ICONS[phase] ?? Search;

          return (
            <div key={phase} className="flex items-start flex-1 last:flex-none">
              <div className="flex flex-col items-center gap-1.5 min-w-0">
                {/* Circle */}
                <div className="relative flex items-center justify-center">
                  <motion.div
                    animate={{
                      backgroundColor: isPast
                        ? '#22c55e'
                        : isCurrent
                          ? 'hsl(var(--primary, 221 83% 53%))'
                          : '#e5e7eb',
                      scale: isCurrent ? [1, 1.08, 1] : 1,
                    }}
                    transition={
                      isCurrent
                        ? {
                            scale: {
                              repeat: Infinity,
                              repeatType: 'loop',
                              duration: 1.8,
                              ease: 'easeInOut',
                            },
                            backgroundColor: { duration: 0.4 },
                          }
                        : { backgroundColor: { duration: 0.4 } }
                    }
                    className="w-9 h-9 rounded-full flex items-center justify-center shadow-sm"
                  >
                    <AnimatePresence mode="wait" initial={false}>
                      {isPast ? (
                        <motion.span
                          key="check"
                          initial={{ scale: 0, opacity: 0 }}
                          animate={{ scale: 1, opacity: 1 }}
                          exit={{ scale: 0, opacity: 0 }}
                          transition={{ duration: 0.25, type: 'spring', stiffness: 260 }}
                        >
                          <Check className="w-4 h-4 text-white" strokeWidth={3} />
                        </motion.span>
                      ) : (
                        <motion.span
                          key="icon"
                          initial={{ scale: 0, opacity: 0 }}
                          animate={{ scale: 1, opacity: 1 }}
                          exit={{ scale: 0, opacity: 0 }}
                          transition={{ duration: 0.2 }}
                        >
                          <Icon
                            className={cn(
                              'w-4 h-4',
                              isCurrent ? 'text-white' : 'text-gray-400',
                            )}
                            strokeWidth={2}
                          />
                        </motion.span>
                      )}
                    </AnimatePresence>
                  </motion.div>

                  {/* Pulse ring on active */}
                  {isCurrent && (
                    <motion.div
                      className="absolute inset-0 rounded-full border-2 border-primary/40"
                      animate={{ scale: [1, 1.6], opacity: [0.6, 0] }}
                      transition={{
                        repeat: Infinity,
                        duration: 1.8,
                        ease: 'easeOut',
                      }}
                    />
                  )}
                </div>

                {/* Label */}
                <motion.span
                  animate={{
                    color: isPast
                      ? '#16a34a'
                      : isCurrent
                        ? 'hsl(var(--primary, 221 83% 53%))'
                        : '#9ca3af',
                  }}
                  transition={{ duration: 0.3 }}
                  className="text-xs font-medium whitespace-nowrap"
                >
                  {phase}
                </motion.span>
              </div>

              {/* Connector line */}
              {idx < phases.length - 1 && (
                <div className="relative h-0.5 flex-1 mx-1.5 mt-[18px] bg-gray-200 rounded-full overflow-hidden">
                  <motion.div
                    className="absolute inset-y-0 left-0 bg-green-400 rounded-full"
                    initial={{ width: '0%' }}
                    animate={{ width: idx < activeIndex ? '100%' : '0%' }}
                    transition={{ duration: 0.5, ease: 'easeInOut' }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Progress Bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-text-primary">
            {progressLabel}
          </span>
          <div className="flex items-center gap-2">
            {etaLabel && (
              <span className="flex items-center gap-1 text-xs text-text-secondary">
                <Clock className="w-3 h-3" />
                {etaLabel}
              </span>
            )}
            <motion.span
              key={barPercent}
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-sm font-semibold tabular-nums text-text-primary"
            >
              {barPercent}%
            </motion.span>
          </div>
        </div>
        <Progress value={barPercent} className="h-2" />
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-3 gap-3">
        {/* Processed */}
        <Card className="bg-gray-50/80 border-gray-200/80 shadow-none">
          <CardContent className="p-4 text-center">
            <div className="flex items-center justify-center mb-2">
              <div className="w-7 h-7 rounded-lg bg-gray-200/80 flex items-center justify-center">
                <Filter className="w-3.5 h-3.5 text-gray-500" />
              </div>
            </div>
            <AnimatedNumber
              value={processedRows}
              className="block text-2xl font-bold tabular-nums text-text-primary leading-none"
            />
            <p className="text-xs text-text-secondary mt-1.5">Processed</p>
          </CardContent>
        </Card>

        {/* Found */}
        <Card className="bg-green-50/70 border-green-200/80 shadow-none">
          <CardContent className="p-4 text-center">
            <div className="flex items-center justify-center mb-2">
              <div className="w-7 h-7 rounded-lg bg-green-200/80 flex items-center justify-center">
                <Check className="w-3.5 h-3.5 text-green-600" strokeWidth={3} />
              </div>
            </div>
            <AnimatedNumber
              value={foundCount}
              className="block text-2xl font-bold tabular-nums text-green-600 leading-none"
            />
            <p className="text-xs text-text-secondary mt-1.5">Found</p>
          </CardContent>
        </Card>

        {/* Match Rate */}
        <Card className="bg-gray-50/80 border-gray-200/80 shadow-none">
          <CardContent className="p-4 text-center">
            <div className="flex items-center justify-center mb-2">
              <div className="w-7 h-7 rounded-lg bg-gray-200/80 flex items-center justify-center">
                <ShieldCheck className="w-3.5 h-3.5 text-gray-500" />
              </div>
            </div>
            <AnimatedNumber
              value={matchRate}
              className={cn(
                'block text-2xl font-bold tabular-nums leading-none',
                matchRate >= 70
                  ? 'text-green-600'
                  : matchRate >= 40
                    ? 'text-amber-600'
                    : 'text-text-primary',
              )}
            />
            <p className="text-xs text-text-secondary mt-1.5">Match Rate %</p>
            {/* Mini bar indicator */}
            <div className="mt-2 h-1 w-full bg-gray-200 rounded-full overflow-hidden">
              <motion.div
                className={cn(
                  'h-full rounded-full',
                  matchRate >= 70
                    ? 'bg-green-500'
                    : matchRate >= 40
                      ? 'bg-amber-500'
                      : 'bg-gray-400',
                )}
                initial={{ width: '0%' }}
                animate={{ width: `${matchRate}%` }}
                transition={{ duration: 0.6, ease: 'easeOut' }}
              />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
