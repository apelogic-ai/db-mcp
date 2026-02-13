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
import { ConnectionSelector } from "@/components/ConnectionSelector";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-sans",
});

const inconsolata = Inconsolata({
  subsets: ["latin"],
  variable: "--font-mono",
});

const navItems = [
  { href: "/config", label: "Config" },
  { href: "/context", label: "Context" },
  { href: "/metrics", label: "Metrics" },
  { href: "/traces", label: "Traces" },
  { href: "/insights", label: "Insights" },
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
              <nav className="mt-4 flex items-center justify-between">
                <div className="inline-flex h-9 items-center justify-center gap-1 text-gray-400">
                  {navItems.map((item) => {
                    const isActive =
                      pathname === item.href ||
                      pathname.startsWith(item.href + "/");
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        className={cn(
                          "inline-flex items-center justify-center whitespace-nowrap px-3 py-1 text-sm font-medium transition-all border-b-2",
                          isActive
                            ? "text-brand border-brand"
                            : "text-gray-400 border-transparent hover:text-gray-200",
                        )}
                      >
                        {item.label}
                      </Link>
                    );
                  })}
                </div>
                <ConnectionSelector />
              </nav>
            </div>
          </header>
          <main className="max-w-7xl mx-auto px-4 py-8">
            <ContextViewerProvider>{children}</ContextViewerProvider>
          </main>
        </BICPProvider>
      </body>
    </html>
  );
}
