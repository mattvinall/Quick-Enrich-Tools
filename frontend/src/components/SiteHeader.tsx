"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Github } from "lucide-react";

const GITHUB_URL = "https://github.com/mattvinall/Quick-Enrich-Tools";

export function SiteHeader() {
  const pathname = usePathname();
  const onHomepage = pathname === "/";

  return (
    <header className="sticky top-0 z-50 border-b border-border-warm/60 bg-canvas/85 backdrop-blur-md">
      <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
        <a
          href="https://quickenrich.io"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="QuickEnrich — back to the main site"
          className="flex items-center hover:opacity-75 transition-opacity"
        >
          <Image
            src="/quickenrich-logo.png"
            alt="QuickEnrich"
            width={140}
            height={32}
            className="h-7 w-auto"
            priority
          />
        </a>

        <nav className="flex items-center gap-6 text-sm">
          {!onHomepage && (
            <Link
              href="/"
              className="text-muted-ink hover:text-ink transition-colors"
            >
              All tools
            </Link>
          )}
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-muted-ink hover:text-ink transition-colors"
            aria-label="View source on GitHub"
          >
            <Github className="w-4 h-4" />
            <span>Source</span>
          </a>
        </nav>
      </div>
    </header>
  );
}
