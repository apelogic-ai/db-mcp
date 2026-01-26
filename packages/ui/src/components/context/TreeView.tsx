"use client";

import { cn } from "@/lib/utils";

// Icons
const ChevronRight = ({ className }: { className?: string }) => (
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
    <path d="m9 18 6-6-6-6" />
  </svg>
);

const FolderIcon = ({ className }: { className?: string }) => (
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
    <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />
  </svg>
);

const FileIcon = ({ className }: { className?: string }) => (
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
    <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
    <path d="M14 2v4a2 2 0 0 0 2 2h4" />
  </svg>
);

const DatabaseIcon = ({ className }: { className?: string }) => (
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
    <ellipse cx="12" cy="5" rx="9" ry="3" />
    <path d="M3 5V19A9 3 0 0 0 21 19V5" />
    <path d="M3 12A9 3 0 0 0 21 12" />
  </svg>
);

const GitIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="12"
    height="12"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <circle cx="12" cy="12" r="3" />
    <line x1="3" x2="9" y1="12" y2="12" />
    <line x1="15" x2="21" y1="12" y2="12" />
  </svg>
);

const WarningIcon = ({ className }: { className?: string }) => (
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
    <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" />
    <path d="M12 9v4" />
    <path d="M12 17h.01" />
  </svg>
);

const InfoIcon = ({ className }: { className?: string }) => (
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
    <circle cx="12" cy="12" r="10" />
    <path d="M12 16v-4" />
    <path d="M12 8h.01" />
  </svg>
);

export interface FileNode {
  name: string;
  path: string;
  size?: number;
}

export interface FolderNode {
  name: string;
  path: string;
  files: FileNode[];
  isEmpty: boolean;
  importance?: "critical" | "recommended" | "optional" | null;
  hasReadme?: boolean;
}

export interface ConnectionNode {
  name: string;
  isActive: boolean;
  gitEnabled: boolean;
  folders: FolderNode[];
  rootFiles?: FileNode[];
}

interface TreeViewProps {
  connections: ConnectionNode[];
  selectedFile: { connection: string; path: string } | null;
  expandedConnections: Set<string>;
  expandedFolders: Set<string>;
  onSelectFile: (connection: string, path: string) => void;
  onSelectFolder: (connection: string, folderName: string) => void;
  onToggleConnection: (name: string) => void;
  onToggleFolder: (key: string) => void;
}

export function TreeView({
  connections,
  selectedFile,
  expandedConnections,
  expandedFolders,
  onSelectFile,
  onSelectFolder,
  onToggleConnection,
  onToggleFolder,
}: TreeViewProps) {
  const isFileSelected = (connection: string, path: string) => {
    return (
      selectedFile?.connection === connection && selectedFile?.path === path
    );
  };

  const isFolderSelected = (connection: string, folderName: string) => {
    return (
      selectedFile?.connection === connection &&
      selectedFile?.path === folderName
    );
  };

  const getImportanceIcon = (folder: FolderNode) => {
    if (!folder.isEmpty || !folder.importance) return null;

    if (folder.importance === "critical") {
      return <WarningIcon className="text-red-500 ml-1" />;
    } else if (folder.importance === "recommended") {
      return <InfoIcon className="text-yellow-500 ml-1" />;
    }
    return null;
  };

  const getImportanceTooltip = (folder: FolderNode): string | undefined => {
    if (!folder.isEmpty || !folder.importance) return undefined;

    if (folder.importance === "critical") {
      return "Required: Click to learn how to set up this folder";
    } else if (folder.importance === "recommended") {
      return "Recommended: Click to learn how to improve your setup";
    }
    return undefined;
  };

  return (
    <div className="text-sm">
      {connections.length === 0 ? (
        <div className="p-4 text-gray-500 text-center">
          No connections configured.
          <br />
          <span className="text-xs">
            Add a connection in the Connectors page.
          </span>
        </div>
      ) : (
        connections.map((conn) => {
          const isExpanded = expandedConnections.has(conn.name);

          return (
            <div key={conn.name}>
              {/* Connection node */}
              <div
                className={cn(
                  "flex items-center gap-1 px-2 py-1.5 cursor-pointer hover:bg-gray-800 rounded",
                  conn.isActive && "bg-green-950/30",
                )}
                onClick={() => onToggleConnection(conn.name)}
              >
                <ChevronRight
                  className={cn(
                    "text-gray-500 transition-transform",
                    isExpanded && "rotate-90",
                  )}
                />
                <DatabaseIcon
                  className={cn(
                    "text-gray-400",
                    conn.isActive && "text-green-500",
                  )}
                />
                <span
                  className={cn(
                    "text-gray-300 flex-1",
                    conn.isActive && "text-white font-medium",
                  )}
                >
                  {conn.name}
                </span>
                {conn.gitEnabled && (
                  <span title="Git enabled">
                    <GitIcon className="text-orange-500" />
                  </span>
                )}
              </div>

              {/* Folders */}
              {isExpanded && (
                <div className="ml-4">
                  {conn.folders.map((folder) => {
                    const folderKey = `${conn.name}/${folder.name}`;
                    const isFolderExpanded = expandedFolders.has(folderKey);
                    const isEmptyClickable =
                      folder.isEmpty && folder.hasReadme && folder.importance;
                    const isSelected = isFolderSelected(conn.name, folder.name);

                    return (
                      <div key={folderKey}>
                        {/* Folder node */}
                        <div
                          className={cn(
                            "flex items-center gap-1 px-2 py-1 rounded",
                            !folder.isEmpty &&
                              "cursor-pointer hover:bg-gray-800",
                            isEmptyClickable &&
                              "cursor-pointer hover:bg-gray-800",
                            folder.isEmpty &&
                              !isEmptyClickable &&
                              "cursor-default",
                            isSelected && "bg-blue-900/50",
                          )}
                          onClick={() => {
                            if (!folder.isEmpty) {
                              // Non-empty folder: toggle expansion
                              onToggleFolder(folderKey);
                            } else if (isEmptyClickable) {
                              // Empty folder with README: show help content
                              onSelectFolder(conn.name, folder.name);
                            }
                          }}
                          title={getImportanceTooltip(folder)}
                        >
                          <ChevronRight
                            className={cn(
                              "text-gray-500 transition-transform",
                              isFolderExpanded && "rotate-90",
                              folder.isEmpty && "invisible",
                            )}
                          />
                          <FolderIcon
                            className={cn(
                              "text-yellow-600",
                              folder.isEmpty && "text-gray-600",
                              isEmptyClickable &&
                                folder.importance === "critical" &&
                                "text-red-400",
                              isEmptyClickable &&
                                folder.importance === "recommended" &&
                                "text-yellow-500",
                            )}
                          />
                          <span
                            className={cn(
                              "text-gray-400",
                              folder.isEmpty &&
                                !isEmptyClickable &&
                                "text-gray-600 italic",
                              isEmptyClickable && "text-gray-300",
                              isSelected && "text-white",
                            )}
                          >
                            {folder.name}
                            {folder.isEmpty && !isEmptyClickable && " (empty)"}
                          </span>
                          {getImportanceIcon(folder)}
                        </div>

                        {/* Files */}
                        {isFolderExpanded && !folder.isEmpty && (
                          <div className="ml-4">
                            {folder.files.map((file) => {
                              const isSelected = isFileSelected(
                                conn.name,
                                file.path,
                              );

                              return (
                                <div
                                  key={file.path}
                                  className={cn(
                                    "flex items-center gap-1 px-2 py-1 cursor-pointer hover:bg-gray-800 rounded",
                                    isSelected && "bg-blue-900/50",
                                  )}
                                  onClick={() =>
                                    onSelectFile(conn.name, file.path)
                                  }
                                >
                                  <span className="w-4" /> {/* Spacer */}
                                  <FileIcon
                                    className={cn(
                                      "text-gray-500",
                                      file.name.endsWith(".yaml") ||
                                        file.name.endsWith(".yml")
                                        ? "text-purple-400"
                                        : "text-blue-400",
                                    )}
                                  />
                                  <span
                                    className={cn(
                                      "text-gray-400",
                                      isSelected && "text-white",
                                    )}
                                  >
                                    {file.name}
                                  </span>
                                  {file.size !== undefined && (
                                    <span className="text-gray-600 text-xs ml-auto">
                                      {formatFileSize(file.size)}
                                    </span>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}

                  {/* Root-level files */}
                  {conn.rootFiles && conn.rootFiles.length > 0 && (
                    <>
                      {conn.rootFiles.map((file) => {
                        const isSelected = isFileSelected(conn.name, file.path);

                        return (
                          <div
                            key={file.path}
                            className={cn(
                              "flex items-center gap-1 px-2 py-1 cursor-pointer hover:bg-gray-800 rounded",
                              isSelected && "bg-blue-900/50",
                            )}
                            onClick={() => onSelectFile(conn.name, file.path)}
                          >
                            <span className="w-4" /> {/* Spacer for chevron */}
                            <FileIcon
                              className={cn(
                                "text-gray-500",
                                file.name.endsWith(".yaml") ||
                                  file.name.endsWith(".yml")
                                  ? "text-purple-400"
                                  : "text-blue-400",
                              )}
                            />
                            <span
                              className={cn(
                                "text-gray-400",
                                isSelected && "text-white",
                              )}
                            >
                              {file.name}
                            </span>
                            {file.size !== undefined && (
                              <span className="text-gray-600 text-xs ml-auto">
                                {formatFileSize(file.size)}
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}
