"use client";

import { useCallback, useEffect, useState, useMemo } from "react";
import { diffLines, Change } from "diff";
import {
  GitCommit,
  getGitHistory,
  getGitShow,
  revertToCommit,
} from "@/lib/bicp";

// Icons
const CloseIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M18 6 6 18" />
    <path d="m6 6 12 12" />
  </svg>
);

const HistoryIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
    <path d="M3 3v5h5" />
    <path d="M12 7v5l4 2" />
  </svg>
);

const RevertIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M3 7v6h6" />
    <path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13" />
  </svg>
);

const EyeIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

const BackIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="m15 18-6-6 6-6" />
  </svg>
);

interface HistoryDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  connection: string | null;
  path: string | null;
  currentContent: string;
  onRevert: () => void; // Called after successful revert to refresh content
}

// Diff view component
interface DiffViewProps {
  oldContent: string;
  newContent: string;
  oldLabel: string;
  newLabel: string;
}

function DiffView({
  oldContent,
  newContent,
  oldLabel,
  newLabel,
}: DiffViewProps) {
  const diff = useMemo(() => {
    return diffLines(oldContent, newContent);
  }, [oldContent, newContent]);

  // Count changes
  const stats = useMemo(() => {
    let additions = 0;
    let deletions = 0;
    diff.forEach((part) => {
      const lines = part.value.split("\n").filter((l) => l !== "").length;
      if (part.added) additions += lines;
      if (part.removed) deletions += lines;
    });
    return { additions, deletions };
  }, [diff]);

  if (oldContent === newContent) {
    return (
      <div className="p-4 text-center text-gray-500 text-sm">
        No changes from current version
      </div>
    );
  }

  return (
    <div className="text-xs font-mono">
      {/* Stats header */}
      <div className="flex items-center gap-3 px-3 py-2 bg-gray-950 border-b border-gray-800">
        <span className="text-gray-400">Changes:</span>
        {stats.additions > 0 && (
          <span className="text-green-400">+{stats.additions}</span>
        )}
        {stats.deletions > 0 && (
          <span className="text-red-400">-{stats.deletions}</span>
        )}
      </div>

      {/* Diff content */}
      <div className="overflow-x-auto">
        {diff.map((part, index) => {
          const lines = part.value.split("\n");
          // Remove last empty line from split
          if (lines[lines.length - 1] === "") lines.pop();

          return lines.map((line, lineIndex) => (
            <div
              key={`${index}-${lineIndex}`}
              className={`px-3 py-0.5 whitespace-pre ${
                part.added
                  ? "bg-green-950/50 text-green-300"
                  : part.removed
                    ? "bg-red-950/50 text-red-300"
                    : "text-gray-400"
              }`}
            >
              <span className="inline-block w-4 text-gray-600 select-none">
                {part.added ? "+" : part.removed ? "-" : " "}
              </span>
              {line || " "}
            </div>
          ));
        })}
      </div>
    </div>
  );
}

function formatDate(isoDate: string): string {
  const date = new Date(isoDate);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return `Today at ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  } else if (diffDays === 1) {
    return `Yesterday at ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  } else if (diffDays < 7) {
    return `${diffDays} days ago`;
  } else {
    return date.toLocaleDateString([], {
      month: "short",
      day: "numeric",
      year: date.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
    });
  }
}

export function HistoryDrawer({
  isOpen,
  onClose,
  connection,
  path,
  currentContent,
  onRevert,
}: HistoryDrawerProps) {
  const [commits, setCommits] = useState<GitCommit[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedCommit, setSelectedCommit] = useState<GitCommit | null>(null);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [isReverting, setIsReverting] = useState(false);

  // Load commit history when drawer opens
  useEffect(() => {
    if (isOpen && connection && path) {
      setIsLoading(true);
      setError(null);
      setSelectedCommit(null);
      setPreviewContent(null);

      getGitHistory(connection, path)
        .then((result) => {
          if (result.success && result.commits) {
            setCommits(result.commits);
          } else {
            setError(result.error || "Failed to load history");
          }
        })
        .catch((err) => {
          setError(err.message);
        })
        .finally(() => {
          setIsLoading(false);
        });
    }
  }, [isOpen, connection, path]);

  // Load preview when commit is selected
  const handleSelectCommit = useCallback(
    async (commit: GitCommit) => {
      if (!connection || !path) return;

      setSelectedCommit(commit);
      setIsLoadingPreview(true);

      try {
        const result = await getGitShow(connection, path, commit.hash);
        if (result.success && result.content !== undefined) {
          setPreviewContent(result.content);
        } else {
          setPreviewContent(null);
          setError(result.error || "Failed to load file content");
        }
      } catch (err) {
        setPreviewContent(null);
        setError(err instanceof Error ? err.message : "Failed to load preview");
      } finally {
        setIsLoadingPreview(false);
      }
    },
    [connection, path],
  );

  // Revert to selected commit
  const handleRevert = useCallback(async () => {
    if (!connection || !path || !selectedCommit) return;

    const confirmMsg = `Revert "${path}" to version from ${formatDate(selectedCommit.date)}?\n\nCommit: ${selectedCommit.hash}\n"${selectedCommit.message}"`;

    if (!confirm(confirmMsg)) return;

    setIsReverting(true);

    try {
      const result = await revertToCommit(
        connection,
        path,
        selectedCommit.hash,
      );
      if (result.success) {
        onRevert();
        onClose();
      } else {
        setError(result.error || "Failed to revert");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revert");
    } finally {
      setIsReverting(false);
    }
  }, [connection, path, selectedCommit, onRevert, onClose]);

  if (!isOpen) return null;

  return (
    <div className="w-80 border-l border-gray-700 bg-gray-900 flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <HistoryIcon className="text-gray-400" />
          <h2 className="text-sm font-medium text-gray-200">Version History</h2>
        </div>
        <button
          onClick={onClose}
          className="p-1 hover:bg-gray-800 rounded text-gray-400 hover:text-white"
        >
          <CloseIcon />
        </button>
      </div>

      {/* File path */}
      <div className="px-4 py-2 border-b border-gray-800 bg-gray-900/50">
        <p className="text-xs text-gray-500 font-mono truncate">
          {connection}/{path}
        </p>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {isLoading ? (
          <div className="flex-1 flex items-center justify-center text-gray-500">
            Loading history...
          </div>
        ) : error ? (
          <div className="flex-1 flex items-center justify-center text-red-400 px-4 text-center">
            {error}
          </div>
        ) : commits.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-gray-500 px-4 text-center">
            No version history found for this file.
          </div>
        ) : selectedCommit ? (
          /* Diff view for selected commit */
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Back button and commit info */}
            <div className="px-3 py-2 border-b border-gray-800 bg-gray-900/50">
              <button
                onClick={() => {
                  setSelectedCommit(null);
                  setPreviewContent(null);
                }}
                className="flex items-center gap-1 text-sm text-gray-400 hover:text-white mb-2"
              >
                <BackIcon />
                Back to history
              </button>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-200 truncate">
                    {selectedCommit.message}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    <span className="font-mono text-gray-400">
                      {selectedCommit.hash}
                    </span>
                    {" · "}
                    {formatDate(selectedCommit.date)}
                  </p>
                </div>
                {selectedCommit === commits[0] && (
                  <span className="text-xs bg-green-900/50 text-green-400 px-2 py-0.5 rounded">
                    current
                  </span>
                )}
              </div>
            </div>

            {/* Revert button */}
            <div className="px-3 py-2 border-b border-gray-800">
              <button
                onClick={handleRevert}
                disabled={isReverting || selectedCommit === commits[0]}
                className={`w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded text-sm transition-colors ${
                  selectedCommit === commits[0]
                    ? "bg-gray-800 text-gray-500 cursor-not-allowed"
                    : "bg-blue-600 hover:bg-blue-700 text-white"
                }`}
              >
                <RevertIcon />
                {isReverting ? "Reverting..." : "Revert to this version"}
              </button>
            </div>

            {/* Diff view */}
            <div className="flex-1 overflow-y-auto">
              {isLoadingPreview ? (
                <div className="px-4 py-8 text-center text-gray-500">
                  Loading diff...
                </div>
              ) : previewContent !== null ? (
                <DiffView
                  oldContent={previewContent}
                  newContent={currentContent}
                  oldLabel={`${selectedCommit.hash} (selected)`}
                  newLabel="current"
                />
              ) : null}
            </div>
          </div>
        ) : (
          /* Commit list */
          <div className="flex-1 overflow-y-auto">
            {commits.map((commit, index) => (
              <div
                key={commit.fullHash}
                className="px-4 py-3 border-b border-gray-800 cursor-pointer transition-colors hover:bg-gray-800/50"
                onClick={() => handleSelectCommit(commit)}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-200 truncate">
                      {commit.message}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      <span className="font-mono text-gray-400">
                        {commit.hash}
                      </span>
                      {" · "}
                      {formatDate(commit.date)}
                    </p>
                  </div>
                  {index === 0 && (
                    <span className="text-xs bg-green-900/50 text-green-400 px-2 py-0.5 rounded">
                      current
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
