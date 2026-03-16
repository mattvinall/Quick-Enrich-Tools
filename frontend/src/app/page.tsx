import Link from 'next/link';
import { tools } from '@/lib/tool-registry';

export default function HomePage() {
  const activeTools = tools.filter((tool) => tool.isActive);

  return (
    <div className="max-w-6xl mx-auto px-6 py-16">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-text-primary mb-4">
          Data Enrichment Tools
        </h1>
        <p className="text-lg text-text-secondary max-w-xl mx-auto">
          Upload a CSV, enrich your data at scale, and download the results in
          seconds.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {activeTools.map((tool) => (
          <Link
            key={tool.slug}
            href={`/tools/${tool.slug}`}
            className="group block rounded-xl border border-border bg-white p-6 shadow-sm hover:shadow-md hover:border-primary transition-all duration-200"
          >
            <h2 className="text-lg font-semibold text-text-primary mb-2 group-hover:text-primary transition-colors">
              {tool.name}
            </h2>
            <p className="text-sm text-text-secondary leading-relaxed">
              {tool.description}
            </p>
            <div className="mt-4 flex items-center text-sm font-medium text-primary">
              Use tool
              <svg
                className="ml-1 w-4 h-4 transition-transform group-hover:translate-x-1"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9 5l7 7-7 7"
                />
              </svg>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
