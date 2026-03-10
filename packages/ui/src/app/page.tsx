"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

export default function RootPage() {
  const router = useRouter();
  const redirected = useRef(false);

  useEffect(() => {
    if (redirected.current) {
      return;
    }

    redirected.current = true;
    router.replace("/connections");
  }, [router]);

  return (
    <div className="flex min-h-[40vh] items-center justify-center text-gray-400">
      Redirecting...
    </div>
  );
}
