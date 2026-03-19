"use client";

import { useMemo } from "react";

interface LineStats {
  total: number;
  urls: number;
  names: number;
}

interface IntelInputPanelProps {
  value: string;
  onChange: (value: string) => void;
  lineStats: LineStats;
}

function classifyLine(line: string): "url" | "name" {
  const trimmed = line.trim().toLowerCase();
  if (!trimmed) return "name";
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) return "url";
  const dotIdx = trimmed.indexOf(".");
  if (dotIdx > 0 && dotIdx < trimmed.length - 1) {
    const afterDot = trimmed.slice(dotIdx + 1).split(/[/?#]/)[0];
    if (afterDot.length >= 2 && afterDot.length <= 10 && /^[a-z]+$/.test(afterDot)) {
      return "url";
    }
  }
  return "name";
}

export function computeLineStats(text: string): LineStats {
  const lines = text.split("\n").filter((l) => l.trim());
  let urls = 0;
  let names = 0;
  for (const line of lines) {
    if (classifyLine(line) === "url") urls++;
    else names++;
  }
  return { total: lines.length, urls, names };
}

export default function IntelInputPanel({ value, onChange, lineStats }: IntelInputPanelProps) {
  return (
    <div className="space-y-2">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={"apple.com\nMicrosoft\nhttps://stripe.com\nAcme Inc"}
        rows={14}
        className="w-full px-4 py-3 text-sm font-mono border border-border rounded-xl bg-white text-text-primary placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 resize-y min-h-[200px]"
      />
      <div className="flex items-center gap-3 text-xs text-text-secondary">
        <span className="font-medium">
          {lineStats.total} {lineStats.total === 1 ? "line" : "lines"} detected
        </span>
        {lineStats.total > 0 && lineStats.urls > 0 && lineStats.names > 0 && (
          <span className="text-gray-400">
            ({lineStats.urls} {lineStats.urls === 1 ? "URL" : "URLs"},{" "}
            {lineStats.names} {lineStats.names === 1 ? "company name" : "company names"})
          </span>
        )}
      </div>
    </div>
  );
}
