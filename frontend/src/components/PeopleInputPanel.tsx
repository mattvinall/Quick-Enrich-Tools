"use client";

interface PeopleInputStats {
  total: number;
  parsed: number;
  errors: number;
}

interface PeopleInputPanelProps {
  value: string;
  onChange: (value: string) => void;
  stats: PeopleInputStats;
}

export function parsePeopleLines(text: string): {
  items: { full_name: string; company_name: string }[];
  errors: number;
} {
  const lines = text.split("\n").filter((l) => l.trim());
  if (lines.length === 0) return { items: [], errors: 0 };

  // Auto-detect separator from first 5 lines
  const sample = lines.slice(0, 5);
  const separators = [", ", " | ", " - "];
  const counts = separators.map((sep) => sample.filter((l) => l.includes(sep)).length);
  const bestIdx = counts.indexOf(Math.max(...counts));
  const sep = counts[bestIdx] > 0 ? separators[bestIdx] : ", ";

  const items: { full_name: string; company_name: string }[] = [];
  let errors = 0;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    let name: string;
    let company: string;

    if (sep === ", ") {
      const idx = trimmed.indexOf(",");
      if (idx === -1) {
        errors++;
        continue;
      }
      name = trimmed.slice(0, idx).trim();
      company = trimmed.slice(idx + 1).trim();
    } else {
      const parts = trimmed.split(sep);
      if (parts.length < 2) {
        errors++;
        continue;
      }
      name = parts[0].trim();
      company = parts.slice(1).join(sep).trim();
    }

    if (!name || !company) {
      errors++;
      continue;
    }

    items.push({ full_name: name, company_name: company });
  }

  return { items, errors };
}

export function computePeopleStats(text: string): PeopleInputStats {
  const lines = text.split("\n").filter((l) => l.trim());
  const { items, errors } = parsePeopleLines(text);
  return { total: lines.length, parsed: items.length, errors };
}

export default function PeopleInputPanel({ value, onChange, stats }: PeopleInputPanelProps) {
  return (
    <div className="space-y-2">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={"Fred Smith, Apple\nJane Doe, Google\nBob Jones, Microsoft"}
        rows={14}
        className="w-full px-4 py-3 text-sm font-mono border border-border rounded-xl bg-white text-text-primary placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 resize-y min-h-[200px]"
      />
      <div className="flex items-center gap-3 text-xs text-text-secondary">
        <span className="font-medium">
          {stats.parsed} {stats.parsed === 1 ? "person" : "people"} detected
        </span>
        {stats.errors > 0 && (
          <span className="text-amber-600">
            ({stats.errors} {stats.errors === 1 ? "line" : "lines"} could not be parsed)
          </span>
        )}
      </div>
      <p className="text-xs text-gray-400">
        One person per line: <span className="font-medium">Name, Company</span> (comma, pipe, or dash separated)
      </p>
    </div>
  );
}
