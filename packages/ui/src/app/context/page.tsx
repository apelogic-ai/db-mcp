"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useBICP } from "@/lib/bicp-context";
import { useContextViewer } from "@/lib/context-viewer-context";
import { TreeView, ConnectionNode, UsageData } from "@/components/context/TreeView";
import { CodeEditor } from "@/components/context/CodeEditor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AgentDialog } from "@/components/AgentDialog";

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

  // Modal states
  const [showAgentModal, setShowAgentModal] = useState(false);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [createContext, setCreateContext] = useState<{
    connection: string;
    folder: string;
  } | null>(null);
  const [uploadType, setUploadType] = useState<"domain" | "data" | "instructions" | null>(null);
  const [uploadContent, setUploadContent] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [createLoading, setCreateLoading] = useState(false);
  const [uploadMode, setUploadMode] = useState<"upload" | "paste">("upload");
  
  // Agent modal state (dialog handles its own agent loading)

  // Usage tracking state
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [usageLoading, setUsageLoading] = useState(false);

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
      
      // Fetch usage data after tree is loaded
      // Note: fetchUsage will be called in a useEffect when connections change
    } catch (err) {
      setTreeError(
        err instanceof Error ? err.message : "Failed to fetch context tree",
      );
    } finally {
      setTreeLoading(false);
    }
  }, [isInitialized, call]);

  // Fetch usage data
  const fetchUsage = useCallback(async () => {
    if (!isInitialized || connections.length === 0) {
      setUsage(null);
      return;
    }

    setUsageLoading(true);
    try {
      // Fetch usage for all active connections and merge results
      const usagePromises = connections.map(async (conn) => {
        try {
          const result = await call<UsageData>("context/usage", {
            connection: conn.name,
            days: 7,
          });
          return { connection: conn.name, usage: result };
        } catch (err) {
          console.error(`Failed to fetch usage for ${conn.name}:`, err);
          return { connection: conn.name, usage: { files: {}, folders: {} } };
        }
      });

      const usageResults = await Promise.all(usagePromises);
      
      // Namespace usage data by connection to prevent cross-connection pollution
      const mergedUsage: UsageData = {
        files: {},
        folders: {},
      };

      usageResults.forEach(({ connection, usage: connUsage }) => {
        // Prefix keys with connection name so schema/foo from "nova"
        // doesn't bleed into "boost-softball"'s schema/foo
        for (const [key, value] of Object.entries(connUsage.files)) {
          mergedUsage.files[`${connection}/${key}`] = value;
        }
        for (const [key, value] of Object.entries(connUsage.folders)) {
          mergedUsage.folders[`${connection}/${key}`] = value;
        }
      });

      setUsage(mergedUsage);
    } catch (err) {
      console.error("Failed to fetch usage data:", err);
      setUsage(null);
    } finally {
      setUsageLoading(false);
    }
  }, [isInitialized, call, connections]);

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

  // Fetch usage when connections change
  useEffect(() => {
    fetchUsage();
  }, [fetchUsage]);

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

  // Handle add via agent
  const handleAddViaAgent = () => {
    setShowAgentModal(true);
  };

  // Handle add file
  const handleAddFile = () => {
    if (!selectedFile && !selectedTreeNode?.folder) return;

    // Get folder context
    const folder = selectedFile 
      ? (selectedFile.path.includes("/")
          ? selectedFile.path.split("/")[0]
          : selectedFile.path)
      : selectedTreeNode!.folder!;
    const connection = selectedFile?.connection || selectedTreeNode!.connection;
    
    setCreateContext({ connection, folder });
    setUploadType(null);
    setUploadContent("");
    setUploadFile(null);
    setUploadMode("upload");
    setShowUploadModal(true);
  };

  // Derive filename from type, content heading, or increment
  const deriveFilename = (type: string, content: string, existingFiles: string[]): string => {
    // First try: extract from markdown heading
    const headingMatch = content.match(/^#\s+(.+)/m);
    if (headingMatch) {
      const base = headingMatch[1]
        .toLowerCase()
        .replace(/[^a-z0-9\s-]/g, '')
        .replace(/\s+/g, '-')
        .substring(0, 50);
      let name = `${base}.md`;
      let i = 1;
      while (existingFiles.includes(`${type}/${name}`)) {
        name = `${base}-${i}.md`;
        i++;
      }
      return name;
    }

    // Fallback: type-derived name (domain -> model.md, data -> reference.md)
    const baseNames: Record<string, string> = {
      domain: "model",
      data: "reference",
      instructions: "rules",
    };
    const base = baseNames[type] || "content";
    let name = `${base}.md`;
    let i = 1;
    while (existingFiles.includes(`${type}/${name}`)) {
      name = `${base}-${i}.md`;
      i++;
    }
    return name;
  };

  // Handle upload file submit
  const handleUploadFile = async () => {
    if (!createContext || !uploadType) return;

    let content = "";

    if (uploadMode === "upload" && uploadFile) {
      content = await uploadFile.text();
    } else if (uploadMode === "paste" && uploadContent.trim()) {
      content = uploadContent;
    } else {
      return;
    }

    // Collect existing file paths for dedup
    const existingFiles: string[] = [];
    for (const conn of connections) {
      if (conn.name === createContext.connection) {
        for (const folder of conn.folders) {
          for (const file of folder.files) {
            existingFiles.push(file.path);
          }
        }
        for (const file of conn.rootFiles || []) {
          existingFiles.push(file.path);
        }
        break;
      }
    }

    const filename = deriveFilename(uploadType, content, existingFiles);

    setCreateLoading(true);
    try {
      const path = `${uploadType}/${filename}`;
      const result = await call<CreateResult>("context/create", {
        connection: createContext.connection,
        path,
        content,
      });

      if (result.success) {
        setShowUploadModal(false);
        setUploadType(null);
        setUploadContent("");
        setUploadFile(null);
        // Select the new file
        setSelectedFile({ connection: createContext.connection, path });
        setContent(content);
        setOriginalContent(content);
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
            usage={usage}
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
            onCreateFile={handleAddFile}
            onCreateFileForFolder={handleAddFile}
            onAddViaAgent={handleAddViaAgent}
            hasFolderContext={!!selectedTreeNode?.folder}
          />
        </div>
      </div>

      {/* Add via Agent modal */}
      <AgentDialog
        open={showAgentModal}
        onClose={() => setShowAgentModal(false)}
        title="Add via Agent"
        description="Most context files (schema descriptions, examples, learnings, instructions) use structured formats that are best created through your AI agent."
        prompts={[
          "Save this SQL as a training example",
          "Add a business rule: always use UTC timestamps",
          "Describe the users table schema",
        ]}
      />

      {/* Add File upload modal */}
      {showUploadModal && createContext && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 w-[480px]">
            <h3 className="text-white font-medium mb-4">Add File</h3>
            
            {/* Step 1: Type selector */}
            {!uploadType && (
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-gray-400 block mb-3">
                    Select file type:
                  </label>
                  <div className="space-y-2">
                    <button
                      onClick={() => setUploadType("domain")}
                      className="w-full p-3 border border-gray-700 rounded-lg bg-gray-800 hover:bg-gray-700 text-left"
                    >
                      <div className="text-white font-medium">Domain Model</div>
                      <div className="text-gray-400 text-xs">Saves to domain/ as .md</div>
                    </button>
                    <button
                      onClick={() => setUploadType("data")}
                      className="w-full p-3 border border-gray-700 rounded-lg bg-gray-800 hover:bg-gray-700 text-left"
                    >
                      <div className="text-white font-medium">Data Reference</div>
                      <div className="text-gray-400 text-xs">Saves to data/ as .md</div>
                    </button>
                    <button
                      onClick={() => setUploadType("instructions")}
                      className="w-full p-3 border border-gray-700 rounded-lg bg-gray-800 hover:bg-gray-700 text-left"
                    >
                      <div className="text-white font-medium">Business Rules</div>
                      <div className="text-gray-400 text-xs">Saves to instructions/ as .md</div>
                    </button>
                    
                    {/* Disabled options */}
                    <div className="space-y-2 opacity-50 cursor-not-allowed">
                      <div className="w-full p-3 border border-gray-700 rounded-lg bg-gray-800 text-left">
                        <div className="text-gray-400 font-medium">Schema Description</div>
                        <div className="text-gray-500 text-xs">Use your agent for structured formats</div>
                      </div>
                      <div className="w-full p-3 border border-gray-700 rounded-lg bg-gray-800 text-left">
                        <div className="text-gray-400 font-medium">Training Example</div>
                        <div className="text-gray-500 text-xs">Use your agent for structured formats</div>
                      </div>
                      <div className="w-full p-3 border border-gray-700 rounded-lg bg-gray-800 text-left">
                        <div className="text-gray-400 font-medium">Learning / Feedback</div>
                        <div className="text-gray-500 text-xs">Use your agent for structured formats</div>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="flex justify-end gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowUploadModal(false)}
                    className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300"
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}

            {/* Step 2: File upload */}
            {uploadType && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-400">
                    Type: {uploadType === "domain" ? "Domain Model" : uploadType === "data" ? "Data Reference" : "Business Rules"}
                  </span>
                  <button
                    onClick={() => setUploadType(null)}
                    className="text-xs text-blue-400 hover:text-blue-300"
                  >
                    Change type
                  </button>
                </div>

                {/* Upload/Paste toggle */}
                <div className="flex border border-gray-700 rounded-lg">
                  <button
                    onClick={() => setUploadMode("upload")}
                    className={`flex-1 px-3 py-2 text-xs rounded-l-lg ${
                      uploadMode === "upload" 
                        ? "bg-gray-700 text-white" 
                        : "bg-gray-800 text-gray-400 hover:text-gray-300"
                    }`}
                  >
                    Upload File
                  </button>
                  <button
                    onClick={() => setUploadMode("paste")}
                    className={`flex-1 px-3 py-2 text-xs rounded-r-lg ${
                      uploadMode === "paste" 
                        ? "bg-gray-700 text-white" 
                        : "bg-gray-800 text-gray-400 hover:text-gray-300"
                    }`}
                  >
                    Paste Content
                  </button>
                </div>

                {/* File input or textarea */}
                {uploadMode === "upload" ? (
                  <div>
                    <Input
                      type="file"
                      accept=".md,.txt"
                      onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                      className="bg-gray-950 border-gray-700 text-white"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      Max 100KB. Accepts .md and .txt files
                    </p>
                  </div>
                ) : (
                  <div>
                    <textarea
                      value={uploadContent}
                      onChange={(e) => setUploadContent(e.target.value)}
                      placeholder="Paste your content here..."
                      rows={8}
                      className="w-full p-3 bg-gray-950 border border-gray-700 rounded-lg text-white text-sm resize-none"
                    />
                    <p className="text-xs text-gray-500 mt-1">
                      Max 100KB of content
                    </p>
                  </div>
                )}

                <div className="flex justify-end gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowUploadModal(false)}
                    className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300"
                  >
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleUploadFile}
                    disabled={createLoading || (uploadMode === "upload" && !uploadFile) || (uploadMode === "paste" && !uploadContent.trim())}
                    className="bg-brand hover:bg-brand-dark text-white"
                  >
                    {createLoading ? "Saving..." : "Save"}
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
