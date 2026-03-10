"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CodeEditor } from "@/components/context/CodeEditor";
import { type ConnectionNode, TreeView } from "@/components/context/TreeView";
import { useBICP } from "@/lib/bicp-context";

interface ContextTreeResult {
  connections: ConnectionNode[];
}

interface ReadResult {
  success: boolean;
  content?: string;
  isStockReadme?: boolean;
  error?: string;
}

interface WriteResult {
  success: boolean;
  error?: string;
}

interface CreateResult {
  success: boolean;
  error?: string;
}

interface DeleteResult {
  success: boolean;
  error?: string;
}

type SelectedTreeNode = {
  connection: string;
  folder?: string;
  file?: string;
};

export function ConnectionKnowledgeWorkspace({
  connectionName,
}: {
  connectionName: string;
}) {
  const { isInitialized, call } = useBICP();
  const [connection, setConnection] = useState<ConnectionNode | null>(null);
  const [selectedFile, setSelectedFile] = useState<{ connection: string; path: string } | null>(null);
  const [selectedTreeNode, setSelectedTreeNode] = useState<SelectedTreeNode | null>(null);
  const [content, setContent] = useState("");
  const [originalContent, setOriginalContent] = useState("");
  const [isStockReadme, setIsStockReadme] = useState(false);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [treeWidth, setTreeWidth] = useState(320);
  const [treeLoading, setTreeLoading] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const resizingRef = useRef(false);
  const isDirty = content !== originalContent;

  const fetchTree = useCallback(async () => {
    if (!isInitialized) {
      return;
    }

    setTreeLoading(true);
    setError(null);

    try {
      const result = await call<ContextTreeResult>("context/tree", {});
      const nextConnection =
        result.connections.find((candidate) => candidate.name === connectionName) || null;
      setConnection(nextConnection);

      if (!nextConnection) {
        setSelectedFile(null);
        setSelectedTreeNode(null);
        setContent("");
        setOriginalContent("");
        setIsStockReadme(false);
        return;
      }

      setExpandedFolders((prev) => {
        if (prev.size > 0) {
          return prev;
        }
        return new Set(nextConnection.folders.filter((folder) => !folder.isEmpty).map((folder) => `${connectionName}/${folder.name}`));
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load knowledge vault");
    } finally {
      setTreeLoading(false);
    }
  }, [call, connectionName, isInitialized]);

  const fetchFile = useCallback(
    async (path: string) => {
      setFileLoading(true);
      setError(null);
      try {
        const result = await call<ReadResult>("context/read", {
          connection: connectionName,
          path,
        });
        if (result.success) {
          const nextContent = result.content || "";
          setContent(nextContent);
          setOriginalContent(nextContent);
          setIsStockReadme(result.isStockReadme || false);
        } else {
          setError(result.error || "Failed to read file");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to read file");
      } finally {
        setFileLoading(false);
      }
    },
    [call, connectionName],
  );

  useEffect(() => {
    setSelectedFile(null);
    setSelectedTreeNode(null);
    setContent("");
    setOriginalContent("");
    setIsStockReadme(false);
    setExpandedFolders(new Set());
    fetchTree();
  }, [connectionName, fetchTree]);

  const confirmDiscard = () => {
    if (!isDirty) {
      return true;
    }
    return confirm("You have unsaved changes. Discard them?");
  };

  const handleSelectFile = (targetConnection: string, path: string) => {
    if (!confirmDiscard()) {
      return;
    }
    const folder = path.includes("/") ? path.split("/")[0] : undefined;
    setSelectedFile({ connection: targetConnection, path });
    setSelectedTreeNode({ connection: targetConnection, folder, file: path });
    setIsStockReadme(false);
    fetchFile(path);
  };

  const handleSelectFolder = (targetConnection: string, folderName: string) => {
    if (!confirmDiscard()) {
      return;
    }
    setSelectedFile({ connection: targetConnection, path: folderName });
    setSelectedTreeNode({ connection: targetConnection, folder: folderName });
    setIsStockReadme(false);
    fetchFile(folderName);
  };

  const handleSave = async () => {
    if (!selectedFile) {
      return;
    }

    try {
      const result = await call<WriteResult>("context/write", {
        connection: selectedFile.connection,
        path: selectedFile.path,
        content,
      });
      if (result.success) {
        setOriginalContent(content);
        await fetchTree();
      } else {
        setError(result.error || "Failed to save file");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save file");
    }
  };

  const handleDiscard = () => {
    setContent(originalContent);
  };

  const handleDelete = async () => {
    if (!selectedFile) {
      return;
    }

    try {
      const result = await call<DeleteResult>("context/delete", {
        connection: selectedFile.connection,
        path: selectedFile.path,
      });
      if (result.success) {
        setSelectedFile(null);
        setSelectedTreeNode(null);
        setContent("");
        setOriginalContent("");
        setIsStockReadme(false);
        await fetchTree();
      } else {
        setError(result.error || "Failed to delete file");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete file");
    }
  };

  const handleCreateFile = async () => {
    const activeFolder =
      selectedTreeNode?.folder ||
      (selectedFile?.path.includes("/") ? selectedFile.path.split("/")[0] : null);
    const suggestedPath = activeFolder ? `${activeFolder}/new-file.md` : "notes.md";
    const nextPath = prompt("New file path", suggestedPath)?.trim();

    if (!nextPath) {
      return;
    }

    try {
      const result = await call<CreateResult>("context/create", {
        connection: connectionName,
        path: nextPath,
        content: "",
      });
      if (!result.success) {
        setError(result.error || "Failed to create file");
        return;
      }

      await fetchTree();
      handleSelectFile(connectionName, nextPath);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create file");
    }
  };

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!resizingRef.current || !containerRef.current) {
        return;
      }

      const bounds = containerRef.current.getBoundingClientRect();
      const nextWidth = event.clientX - bounds.left;
      setTreeWidth(Math.max(240, Math.min(520, nextWidth)));
    };

    const handleMouseUp = () => {
      if (!resizingRef.current) {
        return;
      }
      resizingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  const treeConnections = useMemo(
    () => (connection ? [{ ...connection, isActive: true }] : []),
    [connection],
  );

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div
        ref={containerRef}
        className="flex min-h-[calc(100vh-190px)] items-stretch"
      >
        <div
          className="overflow-auto rounded-l-2xl border border-r-0 border-gray-800 bg-gray-950"
          style={{ width: treeWidth, minWidth: treeWidth }}
        >
          <div className="flex items-center justify-between border-b border-gray-800 px-3 py-2">
            <span className="text-xs uppercase tracking-[0.24em] text-gray-500">
              Knowledge Vault
            </span>
            <button
              onClick={fetchTree}
              disabled={treeLoading}
              className="text-gray-500 transition-colors hover:text-gray-300 disabled:opacity-50"
              title="Refresh"
            >
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
                className={treeLoading ? "animate-spin" : ""}
              >
                <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
                <path d="M21 3v5h-5" />
              </svg>
            </button>
          </div>
          <TreeView
            connections={treeConnections}
            selectedFile={selectedFile}
            selectedTreeNode={selectedTreeNode}
            expandedConnections={new Set([connectionName])}
            expandedFolders={expandedFolders}
            onSelectFile={handleSelectFile}
            onSelectFolder={handleSelectFolder}
            onToggleConnection={() => {}}
            onToggleFolder={(key) => {
              setExpandedFolders((prev) => {
                const next = new Set(prev);
                if (next.has(key)) {
                  next.delete(key);
                } else {
                  next.add(key);
                }
                return next;
              });
            }}
            hideConnectionLevel
          />
        </div>

        <div
          className="mx-2 w-1 cursor-col-resize rounded-full bg-gray-800 transition-colors hover:bg-blue-600"
          onMouseDown={(event) => {
            event.preventDefault();
            resizingRef.current = true;
            document.body.style.cursor = "col-resize";
            document.body.style.userSelect = "none";
          }}
        />

        <div className="min-w-0 flex-1 overflow-hidden rounded-r-2xl border border-gray-800 bg-gray-900">
          <CodeEditor
            connection={selectedFile?.connection || connectionName}
            path={selectedFile?.path || null}
            content={content}
            isStockReadme={isStockReadme}
            isLoading={fileLoading}
            isDirty={isDirty}
            gitEnabled={connection?.gitEnabled ?? false}
            onContentChange={setContent}
            onSave={handleSave}
            onDiscard={handleDiscard}
            onDelete={handleDelete}
            onCreateFile={handleCreateFile}
            onCreateFileForFolder={handleCreateFile}
            hasFolderContext={!!selectedTreeNode?.folder}
          />
        </div>
      </div>
    </div>
  );
}
