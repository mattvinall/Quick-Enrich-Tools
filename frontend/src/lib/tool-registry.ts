export type ApiKeyKind = "serper" | "scrape_do" | "quickenrich";

export interface ApiKeyMeta {
  kind: ApiKeyKind;
  label: string;
  signupUrl: string;
  blurb: string;
}

export const API_KEY_META: Record<ApiKeyKind, ApiKeyMeta> = {
  serper: {
    kind: "serper",
    label: "Serper",
    signupUrl: "https://serper.dev",
    blurb: "Google search API. Free tier covers ~2.5k queries.",
  },
  scrape_do: {
    kind: "scrape_do",
    label: "Scrape.do",
    signupUrl: "https://scrape.do",
    blurb: "Anti-bot scraping proxy. Free trial available.",
  },
  quickenrich: {
    kind: "quickenrich",
    label: "QuickEnrich",
    signupUrl: "https://quickenrich.io",
    blurb: "Named-contact enrichment (email + LinkedIn).",
  },
};

export interface ToolConfig {
  slug: string;
  name: string;
  description: string;
  isActive: boolean;
  backendUrl: string;
  requiredColumns: string[];
  optionalColumns: string[];
  columnPatterns: Record<string, RegExp>;
  /** API keys the user must provide to run this tool. */
  requiredKeys: ApiKeyKind[];
  /** API keys that unlock optional features (e.g., contact enrichment). */
  optionalKeys: ApiKeyKind[];
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const tools: ToolConfig[] = [
  {
    slug: "company-location-finder",
    name: "Company + Location Website Finder",
    description:
      "Find the exact company website by matching name and location. Upload companies with their city or state to get precise, verified domain matches.",
    isActive: true,
    backendUrl: API_BASE_URL,
    requiredColumns: ["company_name"],
    optionalColumns: ["location"],
    columnPatterns: {
      company_name: /company|name|org|business|brand/i,
      location: /location|city|state|address|geo|region/i,
    },
    requiredKeys: ["serper"],
    optionalKeys: [],
  },
  {
    slug: "company-intel",
    name: "Company/People Intel by URL",
    description:
      "Extract business intelligence from company websites. Paste URLs or company names to get industry, contacts, target market, and more.",
    isActive: true,
    backendUrl: API_BASE_URL,
    requiredColumns: [],
    optionalColumns: [],
    columnPatterns: {},
    requiredKeys: ["serper", "scrape_do"],
    optionalKeys: ["quickenrich"],
  },
  {
    slug: "g2-intel",
    name: "G2 Category to Company Intel",
    description:
      "Select G2 software categories to discover companies and extract business intelligence, contacts, and more.",
    isActive: true,
    backendUrl: API_BASE_URL,
    requiredColumns: [],
    optionalColumns: [],
    columnPatterns: {},
    requiredKeys: ["serper", "scrape_do"],
    optionalKeys: ["quickenrich"],
  },
  {
    slug: "maps-intel",
    name: "Google Maps to Company Intel",
    description:
      "Search Google Maps by category and location to discover businesses, then extract business intelligence, contacts, and more.",
    isActive: true,
    backendUrl: API_BASE_URL,
    requiredColumns: [],
    optionalColumns: [],
    columnPatterns: {},
    requiredKeys: ["serper", "scrape_do"],
    optionalKeys: ["quickenrich"],
  },
  {
    slug: "funding-intel",
    name: "Funded Companies Today",
    description:
      "Discover companies that received funding today and extract business intelligence, contacts, and more.",
    isActive: true,
    backendUrl: API_BASE_URL,
    requiredColumns: [],
    optionalColumns: [],
    columnPatterns: {},
    requiredKeys: ["serper", "scrape_do"],
    optionalKeys: ["quickenrich"],
  },
  {
    slug: "people-intel",
    name: "People Intel by Name",
    description:
      "Upload names and company names to find LinkedIn profiles and extract business intelligence, contacts, and more.",
    isActive: true,
    backendUrl: API_BASE_URL,
    requiredColumns: [],
    optionalColumns: [],
    columnPatterns: {},
    requiredKeys: ["serper", "quickenrich"],
    optionalKeys: [],
  },
];

export function getToolBySlug(slug: string): ToolConfig | undefined {
  return tools.find((tool) => tool.slug === slug);
}
