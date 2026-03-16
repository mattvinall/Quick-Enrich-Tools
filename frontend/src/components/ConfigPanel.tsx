"use client";

import { useState, useRef, useEffect } from "react";

const SUGGESTED_TITLES = [
  "CEO",
  "CTO",
  "CFO",
  "COO",
  "CMO",
  "VP Sales",
  "VP Marketing",
  "VP Engineering",
  "Head of Growth",
  "Head of Sales",
  "Head of Marketing",
  "Founder",
  "Co-Founder",
  "Director of Sales",
];

interface ConfigPanelProps {
  enrichContacts: boolean;
  jobTitles: string[];
  maxContacts: number;
  onEnrichContactsChange: (value: boolean) => void;
  onJobTitlesChange: (titles: string[]) => void;
  onMaxContactsChange: (value: number) => void;
}

export default function ConfigPanel({
  enrichContacts,
  jobTitles,
  maxContacts,
  onEnrichContactsChange,
  onJobTitlesChange,
  onMaxContactsChange,
}: ConfigPanelProps) {
  const [titleInput, setTitleInput] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const suggestionsRef = useRef<HTMLDivElement>(null);

  const filteredSuggestions = SUGGESTED_TITLES.filter(
    (title) =>
      !jobTitles.includes(title) &&
      title.toLowerCase().includes(titleInput.toLowerCase())
  );

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        suggestionsRef.current &&
        !suggestionsRef.current.contains(event.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(event.target as Node)
      ) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function addTitle(title: string) {
    const trimmed = title.trim();
    if (trimmed && !jobTitles.includes(trimmed)) {
      onJobTitlesChange([...jobTitles, trimmed]);
    }
    setTitleInput("");
    setShowSuggestions(false);
    inputRef.current?.focus();
  }

  function removeTitle(title: string) {
    onJobTitlesChange(jobTitles.filter((t) => t !== title));
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      if (titleInput.trim()) {
        addTitle(titleInput);
      }
    } else if (e.key === "Escape") {
      setShowSuggestions(false);
    }
  }

  return (
    <div className="border border-border rounded-lg p-4 space-y-4">
      <label className="flex items-center gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={enrichContacts}
          onChange={(e) => onEnrichContactsChange(e.target.checked)}
          className="w-4 h-4 accent-primary cursor-pointer"
        />
        <span className="font-medium text-sm">Enrich with contact data</span>
      </label>

      {enrichContacts && (
        <div className="space-y-4 pl-7">
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground">
              Job titles to target
            </label>

            {jobTitles.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {jobTitles.map((title) => (
                  <span
                    key={title}
                    className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-primary/10 text-primary"
                  >
                    {title}
                    <button
                      type="button"
                      onClick={() => removeTitle(title)}
                      className="ml-1 hover:opacity-70 transition-opacity leading-none"
                      aria-label={`Remove ${title}`}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}

            <div className="relative">
              <input
                ref={inputRef}
                type="text"
                value={titleInput}
                onChange={(e) => {
                  setTitleInput(e.target.value);
                  setShowSuggestions(true);
                }}
                onFocus={() => setShowSuggestions(true)}
                onKeyDown={handleKeyDown}
                placeholder="Type or select a job title..."
                className="w-full px-3 py-2 text-sm border border-border rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
              />

              {showSuggestions && filteredSuggestions.length > 0 && (
                <div
                  ref={suggestionsRef}
                  className="absolute z-10 w-full mt-1 bg-background border border-border rounded-md shadow-lg max-h-48 overflow-y-auto"
                >
                  {filteredSuggestions.map((title) => (
                    <button
                      key={title}
                      type="button"
                      onMouseDown={(e) => {
                        e.preventDefault();
                        addTitle(title);
                      }}
                      className="w-full text-left px-3 py-2 text-sm text-foreground hover:bg-primary/10 hover:text-primary transition-colors"
                    >
                      {title}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <p className="text-xs text-muted-foreground">
              Press Enter to add a custom title, or select from suggestions.
            </p>
          </div>

          <div className="space-y-2">
            <label
              htmlFor="max-contacts"
              className="text-sm font-medium text-foreground"
            >
              Max contacts per company
            </label>
            <select
              id="max-contacts"
              value={maxContacts}
              onChange={(e) => onMaxContactsChange(Number(e.target.value))}
              className="w-full px-3 py-2 text-sm border border-border rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
            >
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
    </div>
  );
}
