"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, MapPin, Search, Users } from "lucide-react";
import { tools } from "@/lib/tool-registry";

const TOOL_ICONS: Record<string, React.ReactNode> = {
  "company-location-finder": (
    <div className="flex items-center gap-1 text-primary">
      <Search className="w-5 h-5" />
      <MapPin className="w-4 h-4" />
    </div>
  ),
};

export default function HomePage() {
  const activeTools = tools.filter((t) => t.isActive);

  return (
    <div className="max-w-5xl mx-auto px-6 py-16">
      <motion.div
        className="text-center mb-14"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <h1 className="text-4xl font-bold text-text-primary mb-3">
          QuickEnrich Tools
        </h1>
        <p className="text-lg text-text-secondary max-w-lg mx-auto">
          Free data enrichment tools. Upload your data, get enriched results at
          scale.
        </p>
      </motion.div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {activeTools.map((tool, i) => (
          <motion.div
            key={tool.slug}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: i * 0.1 }}
          >
            <Link
              href={`/tools/${tool.slug}`}
              className="group block rounded-xl border border-border bg-white p-6 shadow-sm hover:shadow-md hover:border-primary/40 transition-all duration-200 h-full"
            >
              <div className="mb-3">
                {TOOL_ICONS[tool.slug] || (
                  <Users className="w-5 h-5 text-primary" />
                )}
              </div>
              <h2 className="text-lg font-semibold text-text-primary mb-2 group-hover:text-primary transition-colors">
                {tool.name}
              </h2>
              <p className="text-sm text-text-secondary leading-relaxed mb-4">
                {tool.description}
              </p>
              <div className="flex items-center text-sm font-medium text-primary">
                Use tool
                <ArrowRight className="ml-1.5 w-4 h-4 transition-transform group-hover:translate-x-1" />
              </div>
            </Link>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
