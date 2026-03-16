export interface ToolConfig {
  slug: string;
  name: string;
  description: string;
  isActive: boolean;
  backendUrl: string;
  requiredColumns: string[];
  optionalColumns: string[];
  columnPatterns: Record<string, RegExp>;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export const tools: ToolConfig[] = [
  {
    slug: 'website-finder',
    name: 'Website Finder',
    description:
      'Automatically discover company websites from a list of company names. Upload a CSV and get back verified URLs at scale.',
    isActive: true,
    backendUrl: `${API_BASE_URL}/website-finder`,
    requiredColumns: ['company_name'],
    optionalColumns: ['location'],
    columnPatterns: {
      company_name: /company|name|org|business|brand/i,
      location: /location|city|state|address|geo|region/i,
    },
  },
];

export function getToolBySlug(slug: string): ToolConfig | undefined {
  return tools.find((tool) => tool.slug === slug);
}
