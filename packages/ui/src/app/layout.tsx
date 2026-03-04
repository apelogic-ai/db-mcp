"use client";

import "./globals.css";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Space_Grotesk, Inconsolata } from "next/font/google";
import { cn } from "@/lib/utils";
import { BICPProvider } from "@/lib/bicp-context";
import { ContextViewerProvider } from "@/lib/context-viewer-context";
import { ConnectionProvider } from "@/lib/connection-context";
import { ConnectionSelector } from "@/components/ConnectionSelector";
import { ViewModeProvider, useViewMode } from "@/lib/view-mode-context";
import { ViewModeToggle } from "@/components/ViewModeToggle";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-sans",
});

const inconsolata = Inconsolata({
  subsets: ["latin"],
  variable: "--font-mono",
});

const coreNavItems = [
  { href: "/home", label: "Home" },
  { href: "/config", label: "Setup" },
  { href: "/context", label: "Knowledge" },
  { href: "/insights", label: "Insights" },
];

const advancedNavItems = [
  { href: "/metrics", label: "Metrics" },
  { href: "/traces", label: "Traces" },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    fetch("/health")
      .then((r) => r.json())
      .then((d) => setVersion(d.version || null))
      .catch(() => {});
  }, []);

  const isItemActive = (href: string) =>
    pathname === href || pathname.startsWith(href + "/");

  const advancedActive = advancedNavItems.some((item) => isItemActive(item.href));

  return (
    <html lang="en">
      <head>
        <title>db-mcp</title>
        <meta name="description" content="Database Intelligence Platform" />
      </head>
      <body
        className={cn(
          spaceGrotesk.variable,
          inconsolata.variable,
          "font-sans bg-[#121212] text-gray-100 min-h-screen dark",
        )}
      >
        <BICPProvider baseUrl="/bicp" autoConnect>
          <ConnectionProvider>
            <ViewModeProvider>
              <header className="border-b border-gray-800">
                <div className="max-w-7xl mx-auto px-4 py-4">
                  <div className="flex items-center justify-between">
                    <Link href="/" className="flex items-center gap-2.5">
                      <Image
                        src="/ape-icon.svg"
                        alt="APE"
                        width={32}
                        height={32}
                        priority
                      />
                      <span className="text-xl font-bold tracking-tight">
                        <span className="text-white">db</span>
                        <span className="text-brand">mcp</span>
                      </span>
                    </Link>
                    {version && (
                      <span className="text-xs text-gray-600 font-mono">
                        v{version}
                      </span>
                    )}
                  </div>
                  <nav className="mt-4 flex items-center justify-between gap-3">
                    <div className="inline-flex h-9 items-center justify-center gap-1 text-gray-400">
                      {coreNavItems.map((item) => (
                        <Link
                          key={item.href}
                          href={item.href}
                          className={cn(
                            "inline-flex items-center justify-center whitespace-nowrap px-3 py-1 text-sm font-medium transition-all border-b-2",
                            isItemActive(item.href)
                              ? "text-brand border-brand"
                              : "text-gray-400 border-transparent hover:text-gray-200",
                          )}
                        >
                          {item.label}
                        </Link>
                      ))}
                      <AdvancedNav
                        advancedActive={advancedActive}
                        isItemActive={isItemActive}
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      <ViewModeToggle />
                      <ConnectionSelector />
                    </div>
                  </nav>
                </div>
              </header>
              <main className="max-w-7xl mx-auto px-4 py-8">
                <ContextViewerProvider>{children}</ContextViewerProvider>
              </main>
            </ViewModeProvider>
          </ConnectionProvider>
        </BICPProvider>
      </body>
    </html>
  );
}

function AdvancedNav({
  advancedActive,
  isItemActive,
}: {
  advancedActive: boolean;
  isItemActive: (href: string) => boolean;
}) {
  const { viewMode } = useViewMode();

  if (viewMode === "advanced") {
    return (
      <>
        {advancedNavItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "inline-flex items-center justify-center whitespace-nowrap px-3 py-1 text-sm font-medium transition-all border-b-2",
              isItemActive(item.href)
                ? "text-brand border-brand"
                : "text-gray-400 border-transparent hover:text-gray-200",
            )}
          >
            {item.label}
          </Link>
        ))}
      </>
    );
  }

  return (
    <details className="relative">
      <summary
        className={cn(
          "inline-flex h-9 cursor-pointer list-none items-center whitespace-nowrap px-3 py-1 text-sm font-medium border-b-2 transition-all",
          advancedActive
            ? "text-brand border-brand"
            : "text-gray-400 border-transparent hover:text-gray-200",
        )}
      >
        Advanced
      </summary>
      <div className="absolute right-0 z-10 mt-2 min-w-36 rounded-md border border-gray-700 bg-gray-900 p-1 shadow-xl">
        {advancedNavItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "block rounded px-3 py-2 text-sm transition-colors",
              isItemActive(item.href)
                ? "bg-gray-800 text-brand"
                : "text-gray-300 hover:bg-gray-800 hover:text-gray-100",
            )}
          >
            {item.label}
          </Link>
        ))}
      </div>
    </details>
  );
}
