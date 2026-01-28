"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useBICP } from "@/lib/bicp-context";
import { useContextViewer } from "@/lib/context-viewer-context";
import { TreeView, ConnectionNode } from "@/components/context/TreeView";
import { CodeEditor } from "@/components/context/CodeEditor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

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
  gitCommit?: boolean;
  error?: string;
}

interface CreateResult {
  success: boolean;
  gitCommit?: boolean;
  error?: string;
}

interface DeleteResult {
  success: boolean;
  gitCommit?: boolean;
  trashedTo?: string;
  error?: string;
}

export default function ContextPage() {
  const { isInitialized, call } = useBICP();
  const {
    connections,
    setConnections,
    selectedFile,
    setSelectedFile,
    selectedTreeNode,
    setSelectedTreeNode,
    content,
    setContent,
    originalContent,
    setOriginalContent,
    isStockReadme,
    setIsStockReadme,
    expandedConnections,
    toggleConnection,
    expandedFolders,
    toggleFolder,
    treeWidth,
    setTreeWidth,
    isDirty,
  } = useContextViewer();

  // Local loading/error state (doesn't need to persist)
  const [treeLoading, setTreeLoading] = useState(false);
  const [treeError, setTreeError] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);

  // Create file modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createContext, setCreateContext] = useState<{
    connection: string;
    folder: string;
  } | null>(null);
  const [newFileName, setNewFileName] = useState("");
  const [createLoading, setCreateLoading] = useState(false);

  // Split pane resize
  const resizingRef = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Get current connection's git status
  const currentGitEnabled =
    selectedFile &&
    connections.find((c) => c.name === selectedFile.connection)?.gitEnabled;

  // Fetch tree
  const fetchTree = useCallback(async () => {
    if (!isInitialized) return;

    setTreeLoading(true);
    setTreeError(null);
    try {
      const result = await call<ContextTreeResult>("context/tree", {});
      setConnections(result.connections);
    } catch (err) {
      setTreeError(
        err instanceof Error ? err.message : "Failed to fetch context tree",
      );
    } finally {
      setTreeLoading(false);
    }
  }, [isInitialized, call]);

  // Fetch file content
  const fetchFile = useCallback(
    async (connection: string, path: string) => {
      setFileLoading(true);
      setFileError(null);
      try {
        const result = await call<ReadResult>("context/read", {
          connection,
          path,
        });
        if (result.success) {
          setContent(result.content || "");
          setOriginalContent(result.content || "");
          setIsStockReadme(result.isStockReadme || false);
        } else {
          // Clear selection on error - the path is likely invalid
          setSelectedFile(null);
          setContent("");
          setOriginalContent("");
          // Don't show error for common cases like selecting folders
          if (
            !result.error?.includes("File not found") &&
            !result.error?.includes("File type not allowed")
          ) {
            setFileError(result.error || "Failed to read file");
          }
        }
      } catch (err) {
        setSelectedFile(null);
        setContent("");
        setOriginalContent("");
        setFileError(
          err instanceof Error ? err.message : "Failed to read file",
        );
      } finally {
        setFileLoading(false);
      }
    },
    [call, setSelectedFile, setContent, setOriginalContent],
  );

  // Initial fetch
  useEffect(() => {
    fetchTree();
  }, [fetchTree]);

  // Handle file selection
  const handleSelectFile = (connection: string, path: string) => {
    // Check for unsaved changes
    if (content !== originalContent) {
      if (!confirm("You have unsaved changes. Discard them?")) {
        return;
      }
    }
    const folder = path.includes("/") ? path.split("/")[0] : undefined;
    setSelectedFile({ connection, path });
    setSelectedTreeNode({ connection, folder, file: path });
    setIsStockReadme(false);
    fetchFile(connection, path);
  };

  // Handle folder selection (for empty folders with README content)
  const handleSelectFolder = (connection: string, folderName: string) => {
    // Check for unsaved changes
    if (content !== originalContent) {
      if (!confirm("You have unsaved changes. Discard them?")) {
        return;
      }
    }
    // Set path to folder name - backend will return stock README
    setSelectedFile({ connection, path: folderName });
    setSelectedTreeNode({ connection, folder: folderName });
    setIsStockReadme(false); // Will be set by fetchFile response
    fetchFile(connection, folderName);
  };

  // Handle save
  const handleSave = async () => {
    if (!selectedFile) return;

    try {
      const result = await call<WriteResult>("context/write", {
        connection: selectedFile.connection,
        path: selectedFile.path,
        content,
      });

      if (result.success) {
        setOriginalContent(content);
        // Refresh tree to show any new files
        fetchTree();
      } else {
        setFileError(result.error || "Failed to save file");
      }
    } catch (err) {
      setFileError(err instanceof Error ? err.message : "Failed to save file");
    }
  };

  // Handle discard
  const handleDiscard = () => {
    setContent(originalContent);
  };

  // Handle delete
  const handleDelete = async () => {
    if (!selectedFile) return;

    try {
      const result = await call<DeleteResult>("context/delete", {
        connection: selectedFile.connection,
        path: selectedFile.path,
      });

      if (result.success) {
        // Clear selection and refresh tree
        setSelectedFile(null);
        setContent("");
        setOriginalContent("");
        fetchTree();
      } else {
        setFileError(result.error || "Failed to delete file");
      }
    } catch (err) {
      setFileError(
        err instanceof Error ? err.message : "Failed to delete file",
      );
    }
  };

  // Handle create file button (from file/folder view)
  const handleCreateFileButton = () => {
    if (!selectedFile) return;

    // Extract folder from path: for stock READMEs the path IS the folder,
    // for real files like "domain/model.md" we need the directory part
    const folder = selectedFile.path.includes("/")
      ? selectedFile.path.split("/")[0]
      : selectedFile.path;
    setCreateContext({ connection: selectedFile.connection, folder });
    setNewFileName(
      folder === "training" || folder === "examples" ? "example.yaml" : "",
    );
    setShowCreateModal(true);
  };

  // Handle create file from folder context (no file open, but folder selected in tree)
  const handleCreateFileForFolder = () => {
    if (!selectedTreeNode?.folder) return;

    const folder = selectedTreeNode.folder;
    setCreateContext({ connection: selectedTreeNode.connection, folder });
    setNewFileName(
      folder === "training" || folder === "examples" ? "example.yaml" : "",
    );
    setShowCreateModal(true);
  };

  // Handle create file submit
  const handleCreateFile = async () => {
    if (!createContext || !newFileName.trim()) return;

    setCreateLoading(true);
    try {
      const path = `${createContext.folder}/${newFileName.trim()}`;
      const result = await call<CreateResult>("context/create", {
        connection: createContext.connection,
        path,
        content: "",
      });

      if (result.success) {
        setShowCreateModal(false);
        setNewFileName("");
        // Select the new file
        setSelectedFile({ connection: createContext.connection, path });
        setContent("");
        setOriginalContent("");
        setIsStockReadme(false);
        // Refresh tree
        fetchTree();
      } else {
        setFileError(result.error || "Failed to create file");
      }
    } catch (err) {
      setFileError(
        err instanceof Error ? err.message : "Failed to create file",
      );
    } finally {
      setCreateLoading(false);
    }
  };

  // Resize handling
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    resizingRef.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!resizingRef.current || !containerRef.current) return;
      e.preventDefault();

      // Calculate position relative to container
      const containerRect = containerRef.current.getBoundingClientRect();
      const newWidth = e.clientX - containerRect.left;
      setTreeWidth(Math.max(180, Math.min(600, newWidth)));
    };

    const handleMouseUp = () => {
      if (resizingRef.current) {
        resizingRef.current = false;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      }
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [setTreeWidth]);

  return (
    <div className="h-[calc(100vh-120px)] flex flex-col">
      {/* Header */}
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-white">Context Viewer</h1>
        <p className="text-gray-400 mt-1">
          Browse and edit schema descriptions, domain models, and training
          examples
        </p>
      </div>

      {/* Error banner */}
      {(treeError || fileError) && (
        <div className="mb-4 p-3 bg-red-950 border border-red-800 rounded text-red-300 text-sm">
          {treeError || fileError}
        </div>
      )}

      {/* Main content - split pane */}
      <div
        ref={containerRef}
        className="flex-1 flex border border-gray-800 rounded-lg overflow-hidden bg-gray-900"
      >
        {/* Tree panel */}
        <div
          className="border-r border-gray-800 overflow-auto bg-gray-950"
          style={{ width: treeWidth, minWidth: treeWidth }}
        >
          <div className="p-2 border-b border-gray-800 flex items-center justify-between">
            <span className="text-xs text-gray-500 uppercase tracking-wider">
              Connections
            </span>
            <button
              onClick={fetchTree}
              disabled={treeLoading}
              className="text-gray-500 hover:text-gray-300 disabled:opacity-50"
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
            connections={connections}
            selectedFile={selectedFile}
            selectedTreeNode={selectedTreeNode}
            expandedConnections={expandedConnections}
            expandedFolders={expandedFolders}
            onSelectFile={handleSelectFile}
            onSelectFolder={handleSelectFolder}
            onToggleConnection={(name) => {
              const isExpanding = !expandedConnections.has(name);
              toggleConnection(name);
              if (isExpanding) {
                // Check for unsaved changes before clearing editor
                if (isDirty) {
                  if (!confirm("You have unsaved changes. Discard them?")) {
                    return;
                  }
                }
                setSelectedTreeNode({ connection: name });
                setSelectedFile(null);
                setContent("");
                setOriginalContent("");
                setIsStockReadme(false);
              }
            }}
            onToggleFolder={(key) => {
              const isExpanding = !expandedFolders.has(key);
              toggleFolder(key);
              const [conn, folder] = key.split("/", 2);
              if (isExpanding) {
                // Check for unsaved changes before clearing editor
                if (isDirty) {
                  if (!confirm("You have unsaved changes. Discard them?")) {
                    return;
                  }
                }
                setSelectedTreeNode({ connection: conn, folder });
                setSelectedFile(null);
                setContent("");
                setOriginalContent("");
                setIsStockReadme(false);
              }
            }}
          />
        </div>

        {/* Resize handle */}
        <div
          className="w-1 bg-gray-800 hover:bg-blue-600 cursor-col-resize transition-colors"
          onMouseDown={handleMouseDown}
        />

        {/* Editor panel */}
        <div className="flex-1 overflow-hidden">
          <CodeEditor
            connection={selectedFile?.connection || null}
            path={selectedFile?.path || null}
            content={content}
            isStockReadme={isStockReadme}
            isLoading={fileLoading}
            isDirty={isDirty}
            gitEnabled={currentGitEnabled ?? false}
            onContentChange={setContent}
            onSave={handleSave}
            onDiscard={handleDiscard}
            onDelete={handleDelete}
            onCreateFile={handleCreateFileButton}
            onCreateFileForFolder={handleCreateFileForFolder}
            hasFolderContext={!!selectedTreeNode?.folder}
          />
        </div>
      </div>

      {/* Create file modal */}
      {showCreateModal && createContext && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 w-96">
            <h3 className="text-white font-medium mb-4">Create New File</h3>
            <div className="mb-4">
              <label className="text-sm text-gray-400 block mb-1">
                File name
              </label>
              <div className="flex items-center gap-2">
                <span className="text-gray-500 text-sm">
                  {createContext.folder}/
                </span>
                <Input
                  value={newFileName}
                  onChange={(e) => setNewFileName(e.target.value)}
                  placeholder="filename.yaml"
                  className="flex-1 bg-gray-950 border-gray-700 text-white"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleCreateFile();
                    if (e.key === "Escape") setShowCreateModal(false);
                  }}
                />
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Allowed: .yaml, .yml, .md
              </p>
            </div>
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowCreateModal(false)}
                className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleCreateFile}
                disabled={createLoading || !newFileName.trim()}
                className="bg-green-600 hover:bg-green-700 text-white"
              >
                {createLoading ? "Creating..." : "Create"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
