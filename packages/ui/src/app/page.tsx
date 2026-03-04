"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { useBICP } from "@/lib/bicp-context";
import { useConnections } from "@/lib/connection-context";

export default function RootPage() {
  const router = useRouter();
  const redirected = useRef(false);
  const { isInitialized, isLoading: bicpLoading } = useBICP();
  const {
    connections,
    isLoading: connectionsLoading,
    hasLoaded: connectionsLoaded,
    error: connectionError,
  } = useConnections();

  useEffect(() => {
    if (
      redirected.current ||
      bicpLoading ||
      !isInitialized ||
      connectionsLoading ||
      !connectionsLoaded
    ) {
      return;
    }

    redirected.current = true;

    if (connectionError) {
      router.replace("/config");
      return;
    }

    if (connections.length === 0) {
      router.replace("/config?wizard=onboarding");
      return;
    }

    router.replace("/home");
  }, [
    bicpLoading,
    connectionError,
    connections,
    connectionsLoading,
    connectionsLoaded,
    isInitialized,
    router,
  ]);

  return (
    <div className="flex min-h-[40vh] items-center justify-center text-gray-400">
      Redirecting...
    </div>
  );
}
