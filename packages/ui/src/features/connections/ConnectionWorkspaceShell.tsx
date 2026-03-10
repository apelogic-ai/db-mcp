"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo } from "react";
import { DialectIcon } from "@/components/DialectIcon";
import { Button } from "@/components/ui/button";
import { useConnections } from "@/lib/connection-context";
import { cn } from "@/lib/utils";
import { buildConnectionAppHref, getConnectionOnboardingDotClass } from "./utils";

type WorkspaceView = "overview" | "insights" | "knowledge" | null;
type AdvancedView = "metrics" | "traces" | null;

export function ConnectionWorkspaceShell({
  selectedName,
  currentView,
  currentAdvancedView = null,
  children,
}: {
  selectedName?: string | null;
  currentView: WorkspaceView;
  currentAdvancedView?: AdvancedView;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { connections, activeConnection, isLoading } = useConnections();

  const drawerItems = useMemo(
    () =>
      connections.map((connection) => ({
        ...connection,
        href: buildConnectionAppHref(connection.name, currentView ?? "overview"),
        isSelected: connection.name === selectedName,
        isActive: connection.name === activeConnection,
      })),
    [activeConnection, connections, currentView, selectedName],
  );

  const advancedLinks = [
    { href: "/metrics", label: "Metrics", isSelected: currentAdvancedView === "metrics" },
    { href: "/traces", label: "Traces", isSelected: currentAdvancedView === "traces" },
  ];

  const currentAppHref = useMemo(() => {
    if (currentAdvancedView === "metrics") {
      return "/metrics";
    }
    if (currentAdvancedView === "traces") {
      return "/traces";
    }
    if (selectedName && currentView) {
      return buildConnectionAppHref(selectedName, currentView);
    }
    return null;
  }, [currentAdvancedView, currentView, selectedName]);

  const navigateWithinApp = (targetHref: string) => {
    const currentVisibleUrl =
      typeof window === "undefined"
        ? currentAppHref
        : `${window.location.pathname}${window.location.search}`;

    if (currentAppHref && currentVisibleUrl !== currentAppHref) {
      window.history.replaceState(window.history.state, "", currentAppHref);
    }
    router.push(targetHref, { scroll: false });
  };

  return (
    <div className="grid min-h-[calc(100vh-73px)] gap-0 xl:grid-cols-[260px_minmax(0,1fr)]">
      <aside className="border-r border-gray-800 py-6 pr-6">
        <div className="space-y-5 xl:sticky xl:top-6">
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-[1.2rem] font-semibold tracking-tight text-white">Connections</h2>
              <Button
                asChild
                size="sm"
                className="bg-brand hover:bg-brand/90 text-white"
              >
                <Link href="/connection/new#connect">+ New</Link>
              </Button>
            </div>
          </div>

          <div className="space-y-1">
            {isLoading && drawerItems.length === 0 ? (
              <p className="py-2 text-sm text-gray-500">Loading connections...</p>
            ) : drawerItems.length === 0 ? (
              <p className="py-2 text-sm text-gray-500">No connections configured yet.</p>
            ) : (
              drawerItems.map((connection) => (
                <Link
                  key={connection.name}
                  href={connection.href}
                  onClick={(event) => {
                    event.preventDefault();
                    navigateWithinApp(connection.href);
                  }}
                  className={cn(
                    "flex items-center gap-3 rounded-md py-2 text-base transition-colors",
                    connection.isSelected
                      ? "text-brand"
                      : "text-gray-300 hover:text-white",
                  )}
                >
                    <span
                      className={cn(
                        "h-2.5 w-2.5 shrink-0 rounded-full",
                        getConnectionOnboardingDotClass(connection),
                    )}
                  />
                  <DialectIcon
                    dialect={connection.dialect}
                    size={16}
                    className={cn(
                      connection.isSelected ? "text-brand" : "text-gray-500",
                    )}
                  />
                  <span className="min-w-0 flex-1 truncate">{connection.name}</span>
                </Link>
              ))
            )}
          </div>

          <div className="space-y-2 pt-6">
            <h3 className="text-[1.2rem] font-semibold tracking-tight text-white">Advanced</h3>
            <div className="space-y-1">
              {advancedLinks.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={(event) => {
                    event.preventDefault();
                    navigateWithinApp(link.href);
                  }}
                  className={cn(
                    "block rounded-md py-1 text-base transition-colors",
                    link.isSelected
                      ? "text-brand"
                      : "text-gray-400 hover:text-white",
                  )}
                >
                  {link.label}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </aside>

      <div className="min-w-0 py-6 pl-8">{children}</div>
    </div>
  );
}
