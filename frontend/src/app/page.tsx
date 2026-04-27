"use client";

import Link from "next/link";
import { useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowUpRight,
  Check,
  Copy,
  DollarSign,
  Github,
  Grid3X3,
  Map,
  MapPin,
  Search,
  UserSearch,
  Users,
} from "lucide-react";
import { tools } from "@/lib/tool-registry";

const GITHUB_URL = "https://github.com/mattvinall/Quick-Enrich-Tools";
const CLONE_CMD = `git clone ${GITHUB_URL}.git`;

const TOOL_ICONS: Record<string, React.ReactNode> = {
  "company-location-finder": (
    <div className="flex items-center gap-1">
      <Search className="w-5 h-5" strokeWidth={1.5} />
      <MapPin className="w-4 h-4" strokeWidth={1.5} />
    </div>
  ),
  "company-intel": (
    <div className="flex items-center gap-1">
      <Search className="w-5 h-5" strokeWidth={1.5} />
      <Users className="w-4 h-4" strokeWidth={1.5} />
    </div>
  ),
  "g2-intel": (
    <div className="flex items-center gap-1">
      <Grid3X3 className="w-5 h-5" strokeWidth={1.5} />
      <Users className="w-4 h-4" strokeWidth={1.5} />
    </div>
  ),
  "maps-intel": (
    <div className="flex items-center gap-1">
      <Map className="w-5 h-5" strokeWidth={1.5} />
      <Users className="w-4 h-4" strokeWidth={1.5} />
    </div>
  ),
  "funding-intel": (
    <div className="flex items-center gap-1">
      <DollarSign className="w-5 h-5" strokeWidth={1.5} />
      <Users className="w-4 h-4" strokeWidth={1.5} />
    </div>
  ),
  "people-intel": (
    <div className="flex items-center gap-1">
      <UserSearch className="w-5 h-5" strokeWidth={1.5} />
      <Users className="w-4 h-4" strokeWidth={1.5} />
    </div>
  ),
};

const PROVIDERS = [
  "Supabase",
  "Neon",
  "Firebase",
  "Railway",
  "Fly.io",
  "Render",
  "Vercel",
  "Netlify",
  "Scrape.do",
  "SpiderCloud",
  "Resend",
  "Postmark",
];

export default function HomePage() {
  const activeTools = tools.filter((t) => t.isActive);

  return (
    <>
      {/* ───────── Hero ───────── */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-dot-grid opacity-60 pointer-events-none" />
        <div className="absolute -top-40 -right-40 w-[600px] h-[600px] rounded-full bg-primary/5 blur-3xl pointer-events-none" />

        <div className="relative max-w-6xl mx-auto px-6 pt-20 md:pt-28 pb-20 md:pb-24">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="flex items-center gap-3 mb-8 font-mono text-[11px] uppercase tracking-[0.18em] text-muted-ink"
          >
            <span className="inline-block w-6 h-px bg-muted-ink/50" />
            Open source · Free forever
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.05 }}
            className="font-serif text-[2.6rem] sm:text-5xl md:text-6xl lg:text-[4.5rem] leading-[1.02] tracking-tight text-ink max-w-5xl"
            style={{ fontFeatureSettings: '"ss01"' }}
          >
            Six lead-gen tools for finding the companies and people you{" "}
            <span className="italic font-light text-primary">actually</span>{" "}
            want to talk to.
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="mt-8 max-w-2xl text-lg md:text-xl leading-relaxed text-muted-ink"
          >
            Run them right here in your browser, or clone the repo and
            self-host on your own stack. MIT-licensed, customizable with any
            AI coding agent.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.3 }}
            className="mt-10 flex flex-wrap items-center gap-x-8 gap-y-3 text-sm text-muted-ink"
          >
            <Stat label="Tools" value="6" />
            <Stat label="License" value="MIT" />
            <Stat label="Cost" value="$0" />
            <Stat label="Self-host" value="Anywhere" />
          </motion.div>
        </div>
      </section>

      {/* ───────── Tools ───────── */}
      <section className="relative max-w-6xl mx-auto px-6 pb-24">
        <div className="flex items-baseline justify-between mb-10">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-ink">
            ◇ The tools
          </h2>
          <p className="hidden sm:block text-sm text-muted-ink">
            Pick one. Bring your CSV or paste a list.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {activeTools.map((tool, i) => (
            <motion.div
              key={tool.slug}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.4 + i * 0.06 }}
            >
              <Link
                href={`/tools/${tool.slug}`}
                className="group relative block h-full rounded-2xl border border-border-warm bg-white p-7 transition-all duration-300 hover:border-ink/20 hover:shadow-[0_30px_60px_-30px_rgba(12,12,14,0.18)] hover:-translate-y-0.5"
              >
                <div className="flex items-start justify-between mb-6">
                  <div className="text-primary">
                    {TOOL_ICONS[tool.slug] || (
                      <Users className="w-5 h-5" strokeWidth={1.5} />
                    )}
                  </div>
                  <span className="font-mono text-xs text-muted-ink/70">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                </div>
                <h3 className="text-[1.05rem] font-medium text-ink leading-snug mb-2 group-hover:text-primary transition-colors">
                  {tool.name}
                </h3>
                <p className="text-sm leading-relaxed text-muted-ink mb-6">
                  {tool.description}
                </p>
                <div className="flex items-center text-sm font-medium text-ink">
                  Use tool
                  <ArrowUpRight
                    className="ml-1 w-4 h-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
                    strokeWidth={1.75}
                  />
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ───────── Open Source band ───────── */}
      <section className="relative bg-deep text-cream overflow-hidden">
        <div className="absolute inset-0 bg-grain pointer-events-none" />
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[120%] h-px bg-gradient-to-r from-transparent via-cream/15 to-transparent" />

        <div className="relative max-w-6xl mx-auto px-6 py-24 md:py-28">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16">
            <div className="lg:col-span-7">
              <div className="font-mono text-[11px] uppercase tracking-[0.18em] text-cream-muted mb-6">
                ◇ Take it
              </div>
              <h2 className="font-serif text-4xl md:text-5xl lg:text-[3.5rem] leading-[1.05] tracking-tight">
                Fork it, swap any provider,{" "}
                <span className="italic font-light text-[#7ab5e6]">
                  ship your own.
                </span>
              </h2>
              <p className="mt-7 max-w-xl text-base md:text-lg leading-relaxed text-cream-muted">
                Every tool here is a public, MIT-licensed repo. Clone it, open
                it in Claude Code, Codex, or Cursor, and ask the agent to swap
                Supabase for Neon, Scrape.do for SpiderCloud, Railway for
                Fly — whatever your stack runs on. The seams are documented in{" "}
                <span className="text-cream font-mono text-[0.95em]">
                  AGENTS.md
                </span>
                .
              </p>

              <div className="mt-9 flex flex-wrap gap-3">
                <a
                  href={GITHUB_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-5 py-3 rounded-lg bg-cream text-deep font-medium hover:bg-white transition-colors"
                >
                  <Github className="w-4 h-4" strokeWidth={2} />
                  View on GitHub
                  <ArrowUpRight className="w-4 h-4" strokeWidth={2} />
                </a>
                <a
                  href={`${GITHUB_URL}/blob/main/AGENTS.md`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-5 py-3 rounded-lg border border-cream/25 text-cream font-medium hover:bg-cream/5 transition-colors"
                >
                  Read AGENTS.md
                  <ArrowUpRight className="w-4 h-4" strokeWidth={2} />
                </a>
              </div>
            </div>

            <div className="lg:col-span-5 flex flex-col gap-6">
              <CloneCommand />

              <div>
                <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-cream-muted mb-3">
                  Swap any of these
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {PROVIDERS.map((p) => (
                    <span
                      key={p}
                      className="px-2.5 py-1 rounded-md bg-cream/8 border border-cream/10 text-cream-muted text-xs font-mono"
                    >
                      {p}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ───────── Footer ───────── */}
      <footer className="border-t border-border-warm/60 mt-0">
        <div className="max-w-6xl mx-auto px-6 py-10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6">
          <div className="text-sm text-muted-ink">
            Built by{" "}
            <a
              href="https://quickenrich.io"
              target="_blank"
              rel="noopener noreferrer"
              className="text-ink hover:text-primary transition-colors underline-offset-4 hover:underline"
            >
              QuickEnrich
            </a>
            . Free forever.
          </div>
          <nav className="flex items-center gap-6 text-sm text-muted-ink">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-ink transition-colors inline-flex items-center gap-1.5"
            >
              <Github className="w-4 h-4" strokeWidth={1.75} />
              GitHub
            </a>
            <a
              href={`${GITHUB_URL}/blob/main/LICENSE`}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-ink transition-colors"
            >
              MIT License
            </a>
            <a
              href={`${GITHUB_URL}/blob/main/AGENTS.md`}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-ink transition-colors"
            >
              AGENTS.md
            </a>
          </nav>
        </div>
      </footer>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="font-serif text-2xl text-ink leading-none">{value}</span>
      <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-ink">
        {label}
      </span>
    </div>
  );
}

function CloneCommand() {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(CLONE_CMD).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  }

  return (
    <div className="rounded-xl border border-cream/15 bg-deep/50 backdrop-blur-sm overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-cream/10">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-cream-muted">
          Clone the repo
        </span>
        <button
          onClick={copy}
          className="inline-flex items-center gap-1.5 text-xs text-cream-muted hover:text-cream transition-colors"
          aria-label="Copy clone command"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5" strokeWidth={2} />
              Copied
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" strokeWidth={1.75} />
              Copy
            </>
          )}
        </button>
      </div>
      <pre className="px-4 py-4 text-sm font-mono text-cream overflow-x-auto leading-relaxed">
        <code>
          <span className="text-cream-muted">$</span> {CLONE_CMD}
        </code>
      </pre>
    </div>
  );
}
