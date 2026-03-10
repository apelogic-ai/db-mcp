"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useConnections } from "@/lib/connection-context";
import { buildConnectionAppHref } from "./utils";

export function ConnectionsLandingPageClient() {
  const router = useRouter();
  const { connections, activeConnection, hasLoaded } = useConnections();

  useEffect(() => {
    if (!hasLoaded) {
      return;
    }

    const targetName = activeConnection || connections[0]?.name;
    if (targetName) {
      router.replace(buildConnectionAppHref(targetName));
      return;
    }

    router.replace("/connection/new#connect");
  }, [activeConnection, connections, hasLoaded, router]);

  return (
    <div className="flex min-h-[40vh] items-center justify-center text-gray-400">
      Loading connections workspace...
    </div>
  );
}
