"use client";

import { Settings, ExternalLink } from "lucide-react";

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
  serperApiKey: string;
  onSerperApiKeyChange: (v: string) => void;
  showSerperKey: boolean;
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
  serperApiKey,
  onSerperApiKeyChange,
  showSerperKey,
}: ExtractionSettingsProps) {
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
        <div className="space-y-1.5 pt-2 border-t border-border">
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
      )}

      {showSerperKey && (
        <div className="space-y-1.5 pt-2 border-t border-border">
          <label className="text-xs font-semibold text-text-primary">
            Serper API Key
          </label>
          <input
            type="text"
            value={serperApiKey}
            onChange={(e) => onSerperApiKeyChange(e.target.value)}
            placeholder="serper_..."
            className="w-full px-3 py-2 text-sm border border-border rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
          <p className="text-xs text-text-secondary">
            Required to search for company websites from names.
          </p>
        </div>
      )}
    </div>
  );
}
