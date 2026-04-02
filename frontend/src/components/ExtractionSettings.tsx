"use client";

import { useState, useRef, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Settings, X, ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const SUGGESTED_TITLES = [
  "CEO", "CTO", "CFO", "COO", "CMO",
  "VP Sales", "VP Marketing", "VP Engineering",
  "Head of Growth", "Head of Sales", "Head of Marketing",
  "Founder", "Co-Founder", "Director of Sales", "Owner", "President",
] as const;

interface ExtractionSettingsProps {
  industryDescription: boolean;
  targetMarket: boolean;
  companyPeople: boolean;
  homepageRawText: boolean;
  onIndustryDescriptionChange: (v: boolean) => void;
  onTargetMarketChange: (v: boolean) => void;
  onCompanyPeopleChange: (v: boolean) => void;
  onHomepageRawTextChange: (v: boolean) => void;
  quickenrichApiKey: string;
  onQuickenrichApiKeyChange: (v: string) => void;
  jobTitles: string[];
  onJobTitlesChange: (titles: string[]) => void;
  maxContacts: number;
  onMaxContactsChange: (v: number) => void;
  hasCompanyNames?: boolean;
  serperApiKey?: string;
  onSerperApiKeyChange?: (v: string) => void;
}

interface CheckboxItemProps {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description: string;
}

function CheckboxItem({ checked, onChange, label, description }: CheckboxItemProps) {
  return (
    <label className="flex items-start gap-3 cursor-pointer group">
      <div className="pt-0.5">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary/50 cursor-pointer"
        />
      </div>
      <div className="space-y-0.5">
        <span className="text-sm font-semibold text-text-primary group-hover:text-primary transition-colors">
          {label}
        </span>
        <p className="text-xs text-text-secondary leading-relaxed">{description}</p>
      </div>
    </label>
  );
}

export default function ExtractionSettings({
  industryDescription,
  targetMarket,
  companyPeople,
  homepageRawText,
  onIndustryDescriptionChange,
  onTargetMarketChange,
  onCompanyPeopleChange,
  onHomepageRawTextChange,
  quickenrichApiKey,
  onQuickenrichApiKeyChange,
  jobTitles,
  onJobTitlesChange,
  maxContacts,
  onMaxContactsChange,
  hasCompanyNames = false,
  serperApiKey = "",
  onSerperApiKeyChange,
}: ExtractionSettingsProps) {
  const [titleInput, setTitleInput] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const titleInputRef = useRef<HTMLInputElement>(null);
  const suggestionsRef = useRef<HTMLDivElement>(null);

  const titles = jobTitles ?? [];
  const filteredSuggestions = SUGGESTED_TITLES.filter(
    (t) => !titles.includes(t) && t.toLowerCase().includes(titleInput.toLowerCase())
  );

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        suggestionsRef.current && !suggestionsRef.current.contains(e.target as Node) &&
        titleInputRef.current && !titleInputRef.current.contains(e.target as Node)
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
    titleInputRef.current?.focus();
  }

  function removeTitle(title: string) {
    onJobTitlesChange(jobTitles.filter((t) => t !== title));
  }
  return (
    <div className="rounded-xl border border-border bg-white p-5 space-y-5">
      <div className="flex items-center gap-2">
        <Settings className="w-4 h-4 text-text-secondary" />
        <h3 className="text-sm font-semibold text-text-primary">Extraction Settings</h3>
      </div>
      <p className="text-xs text-text-secondary -mt-3">
        Select the data points you want to retrieve.
      </p>

      <div className="space-y-4">
        <CheckboxItem
          checked={industryDescription}
          onChange={onIndustryDescriptionChange}
          label="Industry & Description"
          description="Retrieves Industry, Niche, and a ~600 word company description."
        />
        <CheckboxItem
          checked={targetMarket}
          onChange={onTargetMarketChange}
          label="Target Market"
          description="Identifies Target Market and extracts Case Studies company names."
        />
        <CheckboxItem
          checked={companyPeople}
          onChange={onCompanyPeopleChange}
          label="Company's People"
          description="Finds Contacts (name, title, email, phone) and generic emails."
        />
        <CheckboxItem
          checked={homepageRawText}
          onChange={onHomepageRawTextChange}
          label="Home Page Raw Text"
          description="Returns the raw, viewable text scraped from the home page."
        />
      </div>

      {companyPeople && (
        <div className="space-y-4 pt-2 border-t border-border">
          {/* QuickEnrich API Key */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-text-primary">
                QuickEnrich.io API Key
              </label>
              <a
                href="https://app.quickenrich.io"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-medium text-primary hover:underline flex items-center gap-1"
              >
                Get Key <ExternalLink className="w-3 h-3" />
              </a>
            </div>
            <input
              type="text"
              value={quickenrichApiKey}
              onChange={(e) => onQuickenrichApiKeyChange(e.target.value)}
              placeholder="qe_..."
              className="w-full px-3 py-2 text-sm border border-border rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
            <p className="text-xs text-primary">
              Get 50,000 free QuickEnrich.io credits
            </p>
          </div>

          {/* Job Titles */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-text-primary">
              Job titles to find
            </label>
            <p className="text-xs text-text-secondary -mt-1">
              Press Enter to add a custom title, or pick from suggestions.
            </p>

            {jobTitles.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                <AnimatePresence mode="popLayout">
                  {jobTitles.map((title) => (
                    <motion.div
                      key={title}
                      layout
                      initial={{ scale: 0.8, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.8, opacity: 0 }}
                      transition={{ duration: 0.15 }}
                    >
                      <Badge variant="secondary" className="gap-1 pr-1.5 pl-2.5 py-1">
                        {title}
                        <button
                          type="button"
                          onClick={() => removeTitle(title)}
                          aria-label={`Remove ${title}`}
                          className="ml-0.5 rounded-full p-0.5 hover:bg-gray-300 transition-colors"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            )}

            <div className="relative">
              <input
                ref={titleInputRef}
                type="text"
                value={titleInput}
                onChange={(e) => { setTitleInput(e.target.value); setShowSuggestions(true); }}
                onFocus={() => setShowSuggestions(true)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") { e.preventDefault(); if (titleInput.trim()) addTitle(titleInput); }
                  else if (e.key === "Escape") setShowSuggestions(false);
                }}
                placeholder="e.g. VP of Sales, Head of Growth…"
                autoComplete="off"
                className="w-full px-3 py-2 text-sm border border-border rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
              <AnimatePresence>
                {showSuggestions && filteredSuggestions.length > 0 && (
                  <motion.div
                    ref={suggestionsRef}
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.12 }}
                    className="absolute z-20 w-full mt-1.5 bg-white border border-border rounded-lg shadow-lg max-h-48 overflow-y-auto"
                  >
                    {filteredSuggestions.map((title) => (
                      <button
                        key={title}
                        type="button"
                        onMouseDown={(e) => { e.preventDefault(); addTitle(title); }}
                        className="w-full text-left px-3 py-2 text-sm text-text-primary hover:bg-primary/5 hover:text-primary transition-colors first:rounded-t-lg last:rounded-b-lg"
                      >
                        {title}
                      </button>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>

          {/* Max contacts */}
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-0.5">
              <label className="text-xs font-semibold text-text-primary">Max contacts per company</label>
              <p className="text-xs text-text-secondary">Limit how many contacts are found per company.</p>
            </div>
            <select
              value={maxContacts}
              onChange={(e) => onMaxContactsChange(Number(e.target.value))}
              className={cn(
                "w-16 shrink-0 px-2.5 py-1.5 text-sm rounded-md",
                "border border-border bg-white text-text-primary",
                "focus:outline-none focus:ring-2 focus:ring-primary/40"
              )}
            >
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {hasCompanyNames && (
        <div className="space-y-1.5 pt-2 border-t border-border">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold text-text-primary">
              Serper API Key
            </label>
            <a
              href="https://serper.dev"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs font-medium text-primary hover:underline flex items-center gap-1"
            >
              Get Key <ExternalLink className="w-3 h-3" />
            </a>
          </div>
          <input
            type="text"
            value={serperApiKey}
            onChange={(e) => onSerperApiKeyChange?.(e.target.value)}
            placeholder="Your Serper API key"
            className="w-full px-3 py-2 text-sm border border-border rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
          <p className="text-xs text-text-secondary">
            Required to look up websites for company names. Free tier includes 2,500 searches.
          </p>
        </div>
      )}

    </div>
  );
}
