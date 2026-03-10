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
import { ViewModeProvider } from "@/lib/view-mode-context";

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-sans",
});

const inconsolata = Inconsolata({
  subsets: ["latin"],
  variable: "--font-mono",
});

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

  const isWorkspaceRoute =
    pathname === "/connections" ||
    pathname === "/connections/" ||
    pathname.startsWith("/connection/") ||
    pathname === "/metrics" ||
    pathname === "/metrics/" ||
    pathname === "/traces" ||
    pathname === "/traces/";

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
                <div className="px-6 py-4">
                  <div className="flex items-center justify-between">
                    <Link href="/" prefetch={false} className="flex items-center gap-2.5">
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
                </div>
              </header>
              <main
                className={cn(
                  isWorkspaceRoute ? "w-full px-6 py-0" : "max-w-7xl mx-auto px-4 py-8",
                )}
              >
                <ContextViewerProvider>{children}</ContextViewerProvider>
              </main>
            </ViewModeProvider>
          </ConnectionProvider>
        </BICPProvider>
      </body>
    </html>
  );
}
