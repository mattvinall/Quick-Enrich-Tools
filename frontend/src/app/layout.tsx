import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'QuickEnrich Tools',
  description: 'Data enrichment tools for your business',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-white min-h-screen`}>
        <header className="border-b border-border">
          <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
            <a
              href="/"
              className="text-xl font-semibold text-text-primary hover:text-primary transition-colors"
            >
              QuickEnrich Tools
            </a>
            <a
              href="https://quickenrich.io"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-text-secondary hover:text-primary transition-colors"
            >
              quickenrich.io
            </a>
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
