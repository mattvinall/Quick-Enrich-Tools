import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Image from "next/image";
import Link from "next/link";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "QuickEnrich Tools",
  description: "Free data enrichment tools by QuickEnrich",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${inter.className} min-h-screen`}>
        <header className="border-b border-[#e5e7eb]">
          <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
            <a
              href="https://quickenrich.io"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="QuickEnrich home"
              className="flex items-center gap-2 hover:opacity-80 transition-opacity"
            >
              <Image
                src="/quickenrich-logo.png"
                alt="QuickEnrich"
                width={140}
                height={32}
                className="h-8 w-auto"
                priority
              />
            </a>
            <nav className="flex items-center gap-5">
              <Link
                href="/"
                className="text-sm text-[#6b7280] hover:text-[#2b7ec8] transition-colors"
              >
                All tools
              </Link>
              <a
                href="https://quickenrich.io"
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-[#6b7280] hover:text-[#2b7ec8] transition-colors"
              >
                quickenrich.io
              </a>
            </nav>
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
