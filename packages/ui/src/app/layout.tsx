"use client";

import "./globals.css";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
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
              <Link href="/" className="flex items-center gap-3">
                <Image
                  src="/apegpt-logo.svg"
                  alt="ApeGPT"
                  width={108}
                  height={30}
                  priority
                />
                <span className="text-sm font-medium text-gray-400">db-mcp</span>
              </Link>
              <nav className="mt-4 flex items-center justify-between">
                <div className="inline-flex h-9 items-center justify-center rounded-lg bg-gray-900 p-1 text-gray-400">
                  {navItems.map((item) => {
                    const isActive =
                      pathname === item.href ||
                      pathname.startsWith(item.href + "/");
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        className={cn(
                          "inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium transition-all",
                          isActive
                            ? "bg-brand text-white shadow"
                            : "text-gray-400 hover:text-gray-200",
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
