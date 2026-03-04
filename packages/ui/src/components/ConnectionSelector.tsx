"use client";

import { useConnections } from "@/lib/connection-context";

export function ConnectionSelector() {
  const { connections, activeConnection, isLoading, switchConnection } = useConnections();

  const handleSwitch = async (name: string) => {
    await switchConnection(name);
  };

  if (connections.length === 0) {
    return null;
  }

  return (
    <select
      className="h-8 rounded-md bg-gray-900 border border-gray-700 text-sm text-gray-300 px-2 pr-7 appearance-none cursor-pointer hover:border-gray-600 transition-colors"
      style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%239ca3af' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E")`,
        backgroundRepeat: "no-repeat",
        backgroundPosition: "right 6px center",
      }}
      value={activeConnection || ""}
      onChange={(e) => handleSwitch(e.target.value)}
      disabled={isLoading}
    >
      {connections.map((conn) => (
        <option key={conn.name} value={conn.name}>
          {conn.name}
          {conn.dialect ? ` (${conn.dialect})` : ""}
        </option>
      ))}
    </select>
  );
}
