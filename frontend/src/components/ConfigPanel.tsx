"use client";

import { useState, useRef, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { HelpCircle, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

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
] as const;

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
    <TooltipProvider delayDuration={300}>
      <Card>
        <CardContent className="p-5 space-y-4">
          {/* Toggle row */}
          <div className="flex items-center gap-3">
            <Checkbox
              id="enrich-contacts"
              checked={enrichContacts}
              onCheckedChange={(checked) =>
                onEnrichContactsChange(checked === true)
              }
            />
            <Label
              htmlFor="enrich-contacts"
              className="cursor-pointer select-none"
            >
              Also find contacts via QuickEnrich
            </Label>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label="Learn about QuickEnrich enrichment"
                  className="text-text-secondary hover:text-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 rounded"
                >
                  <HelpCircle className="h-4 w-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right">
                QuickEnrich searches LinkedIn and company databases to find
                verified contacts matching your target job titles — delivered
                alongside your enriched company data.
              </TooltipContent>
            </Tooltip>
          </div>

          {/* Animated expansion */}
          <AnimatePresence initial={false}>
            {enrichContacts && (
              <motion.div
                key="enrich-panel"
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.22, ease: [0.4, 0, 0.2, 1] }}
                style={{ overflow: "hidden" }}
              >
                <div className="pt-1 space-y-5">
                  <Separator />

                  {/* Job titles section */}
                  <div className="space-y-3">
                    <div className="space-y-1">
                      <Label htmlFor="job-title-input" className="text-sm">
                        Job titles to target
                      </Label>
                      <p className="text-xs text-text-secondary">
                        Press Enter to add a custom title, or pick from
                        suggestions.
                      </p>
                    </div>

                    {/* Selected badges */}
                    {jobTitles.length > 0 && (
                      <motion.div
                        className="flex flex-wrap gap-1.5"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ duration: 0.15 }}
                      >
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
                              <Badge
                                variant="secondary"
                                className="gap-1 pr-1.5 pl-2.5 py-1"
                              >
                                {title}
                                <button
                                  type="button"
                                  onClick={() => removeTitle(title)}
                                  aria-label={`Remove ${title}`}
                                  className={cn(
                                    "ml-0.5 rounded-full p-0.5",
                                    "hover:bg-gray-300 transition-colors"
                                  )}
                                >
                                  <X className="h-3 w-3" />
                                </button>
                              </Badge>
                            </motion.div>
                          ))}
                        </AnimatePresence>
                      </motion.div>
                    )}

                    {/* Autocomplete input */}
                    <div className="relative">
                      <Input
                        ref={inputRef}
                        id="job-title-input"
                        type="text"
                        value={titleInput}
                        onChange={(e) => {
                          setTitleInput(e.target.value);
                          setShowSuggestions(true);
                        }}
                        onFocus={() => setShowSuggestions(true)}
                        onKeyDown={handleKeyDown}
                        placeholder="e.g. VP of Sales, Head of Growth…"
                        autoComplete="off"
                      />

                      <AnimatePresence>
                        {showSuggestions && filteredSuggestions.length > 0 && (
                          <motion.div
                            ref={suggestionsRef}
                            key="suggestions"
                            initial={{ opacity: 0, y: -4 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -4 }}
                            transition={{ duration: 0.12 }}
                            className={cn(
                              "absolute z-20 w-full mt-1.5",
                              "bg-white border border-border rounded-lg shadow-lg",
                              "max-h-48 overflow-y-auto"
                            )}
                          >
                            {filteredSuggestions.map((title) => (
                              <button
                                key={title}
                                type="button"
                                onMouseDown={(e) => {
                                  e.preventDefault();
                                  addTitle(title);
                                }}
                                className={cn(
                                  "w-full text-left px-3 py-2 text-sm text-text-primary",
                                  "hover:bg-primary/8 hover:text-primary",
                                  "transition-colors first:rounded-t-lg last:rounded-b-lg"
                                )}
                              >
                                {title}
                              </button>
                            ))}
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </div>

                  <Separator />

                  {/* Max contacts per company */}
                  <div className="flex items-center justify-between gap-4">
                    <div className="space-y-0.5">
                      <Label htmlFor="max-contacts" className="text-sm">
                        Max contacts per company
                      </Label>
                      <p className="text-xs text-text-secondary">
                        Limit how many contacts are found per company.
                      </p>
                    </div>
                    <select
                      id="max-contacts"
                      value={maxContacts}
                      onChange={(e) =>
                        onMaxContactsChange(Number(e.target.value))
                      }
                      className={cn(
                        "w-20 shrink-0 px-2.5 py-1.5 text-sm rounded-md",
                        "border border-border bg-white text-text-primary",
                        "focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary",
                        "transition-colors duration-150"
                      )}
                    >
                      {[1, 2, 3, 4, 5].map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}
