"use client";

import "./globals.css";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { BICPProvider } from "@/lib/bicp-context";
import { ContextViewerProvider } from "@/lib/context-viewer-context";

const navItems = [
  { href: "/connectors", label: "Connectors" },
  { href: "/context", label: "Context" },
  { href: "/query", label: "Query" },
  { href: "/tools", label: "Tools" },
  { href: "/explorer", label: "Explorer" },
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
      <body className="bg-gray-950 text-gray-100 min-h-screen">
        <header className="border-b border-gray-800">
          <div className="max-w-7xl mx-auto px-4 py-4">
            <div className="flex items-center justify-between">
              <Link href="/" className="text-xl font-bold text-white">
                db-mcp
              </Link>
            </div>
            <nav className="mt-4">
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
                          ? "bg-gray-800 text-white shadow"
                          : "text-gray-400 hover:text-gray-200",
                      )}
                    >
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </nav>
          </div>
        </header>
        <main className="max-w-7xl mx-auto px-4 py-8">
          <BICPProvider baseUrl="/bicp" autoConnect>
            <ContextViewerProvider>{children}</ContextViewerProvider>
          </BICPProvider>
        </main>
      </body>
    </html>
  );
}
