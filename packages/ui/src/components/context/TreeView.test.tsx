import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TreeView, type ConnectionNode, type UsageData } from "@/components/context/TreeView";

describe("TreeView", () => {
  const baseConnections: ConnectionNode[] = [
    {
      name: "analytics",
      isActive: true,
      gitEnabled: false,
      folders: [
        {
          name: "examples",
          path: "examples",
          isEmpty: false,
          files: [
            {
              name: "recent-orders.yaml",
              path: "examples/recent-orders.yaml",
              size: 2048,
            },
          ],
        },
      ],
      rootFiles: [
        {
          name: "PROTOCOL.md",
          path: "PROTOCOL.md",
          size: 512,
        },
      ],
    },
  ];

  const noop = vi.fn();

  it("shows usage counts instead of file sizes when usage data is loaded", () => {
    const usage: UsageData = {
      files: {
        "analytics/examples/recent-orders.yaml": { count: 12, lastUsed: 1_741_000_000 },
        "analytics/PROTOCOL.md": { count: 3, lastUsed: 1_741_000_000 },
      },
      folders: {
        "analytics/examples": { count: 15, lastUsed: 1_741_000_000 },
      },
    };

    render(
      <TreeView
        connections={baseConnections}
        selectedFile={null}
        selectedTreeNode={null}
        expandedConnections={new Set(["analytics"])}
        expandedFolders={new Set(["analytics/examples"])}
        onSelectFile={noop}
        onSelectFolder={noop}
        onToggleConnection={noop}
        onToggleFolder={noop}
        usage={usage}
      />,
    );

    expect(screen.getByText("15x")).toBeInTheDocument();
    expect(screen.getByText("12x")).toBeInTheDocument();
    expect(screen.getByText("3x")).toBeInTheDocument();
    expect(screen.queryByText("2.0KB")).not.toBeInTheDocument();
    expect(screen.queryByText("512B")).not.toBeInTheDocument();
  });
});
