"use client";

import { useCallback, useEffect, useState, useRef } from "react";
import Editor from "react-simple-code-editor";
import Prism from "prismjs";
import "prismjs/components/prism-yaml";
import "prismjs/components/prism-markdown";
import "prismjs/themes/prism-tomorrow.css";
import Markdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { HistoryDrawer } from "./HistoryDrawer";
import { SchemaExplorer, parseDbLink } from "./SchemaExplorer";

// Icons
const SaveIcon = ({ className }: { className?: string }) => (
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
    <path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" />
    <path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7" />
    <path d="M7 3v4a1 1 0 0 0 1 1h7" />
  </svg>
);

const UndoIcon = ({ className }: { className?: string }) => (
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
    <path d="M3 7v6h6" />
    <path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13" />
  </svg>
);

const TrashIcon = ({ className }: { className?: string }) => (
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
    <path d="M3 6h18" />
    <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
    <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
  </svg>
);

const PlusIcon = ({ className }: { className?: string }) => (
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
    <path d="M5 12h14" />
    <path d="M12 5v14" />
  </svg>
);

const CopyIcon = ({ className }: { className?: string }) => (
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
    <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
    <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
  </svg>
);

const LinkIcon = ({ className }: { className?: string }) => (
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
    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
  </svg>
);

const HistoryIcon = ({ className }: { className?: string }) => (
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
    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
    <path d="M3 3v5h5" />
    <path d="M12 7v5l4 2" />
  </svg>
);

const DatabaseIcon = ({ className }: { className?: string }) => (
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
    <ellipse cx="12" cy="5" rx="9" ry="3" />
    <path d="M3 5V19A9 3 0 0 0 21 19V5" />
    <path d="M3 12A9 3 0 0 0 21 12" />
  </svg>
);

// Separator component for toolbar
function ToolbarSeparator() {
  return <div className="w-px h-5 bg-gray-700 mx-1" />;
}

// Toast notification component
function Toast({
  message,
  onClose,
}: {
  message: string | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (message) {
      const timer = setTimeout(onClose, 2000);
      return () => clearTimeout(timer);
    }
  }, [message, onClose]);

  if (!message) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 bg-gray-800 border border-gray-700 rounded-md shadow-lg px-4 py-2 text-sm text-gray-200">
      {message}
    </div>
  );
}

interface CodeEditorProps {
  connection: string | null;
  path: string | null;
  content: string;
  isStockReadme?: boolean;
  isLoading?: boolean;
  isDirty: boolean;
  gitEnabled?: boolean;
  onContentChange: (content: string) => void;
  onSave: () => Promise<void>;
  onDiscard: () => void;
  onDelete: () => Promise<void>;
  onCreateFile: () => void;
  onCreateFileForFolder?: () => void; // Create file when a folder is selected but no file open
  onAddViaAgent?: () => void; // Add file via agent workflow
  hasFolderContext?: boolean; // Whether a folder is selected in the tree
  onRefresh?: () => void; // Called after git revert to refresh content
}

export function CodeEditor({
  connection,
  path,
  content,
  isStockReadme,
  isLoading,
  isDirty,
  gitEnabled,
  onContentChange,
  onSave,
  onDiscard,
  onDelete,
  onCreateFile,
  onCreateFileForFolder,
  onAddViaAgent,
  hasFolderContext,
  onRefresh,
}: CodeEditorProps) {
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [schemaOpen, setSchemaOpen] = useState(false);
  const [schemaTarget, setSchemaTarget] =
    useState<ReturnType<typeof parseDbLink>>(null);
  const [selection, setSelection] = useState<{
    text: string;
    startLine: number;
    endLine: number;
  } | null>(null);
  const editorContainerRef = useRef<HTMLDivElement>(null);
  const selectionRef = useRef(selection); // Keep ref in sync for event handlers
  selectionRef.current = selection;

  // Determine language from file extension (or markdown for folder READMEs)
  const getLanguage = useCallback(
    (filePath: string | null, stockReadme: boolean | undefined): string => {
      if (stockReadme) return "markdown"; // Stock READMEs are always markdown
      if (!filePath) return "markdown";
      if (filePath.endsWith(".yaml") || filePath.endsWith(".yml"))
        return "yaml";
      if (filePath.endsWith(".md")) return "markdown";
      return "markdown";
    },
    [],
  );

  const language = getLanguage(path, isStockReadme);

  // Syntax highlighting function with db:// link detection
  const highlight = useCallback(
    (code: string) => {
      const grammar =
        language === "yaml" ? Prism.languages.yaml : Prism.languages.markdown;
      let highlighted = Prism.highlight(code, grammar, language);

      // Highlight db:// links - make them clickable-looking
      // Pattern: db://catalog/schema/table[/column]
      highlighted = highlighted.replace(
        /(db:\/\/[\w.-]+(?:\/[\w.-]+){1,3})/g,
        '<span class="db-link" style="color: #60a5fa; text-decoration: underline; cursor: pointer;">$1</span>',
      );

      return highlighted;
    },
    [language],
  );

  // Handle clicks on db:// links in the editor
  const handleEditorClick = useCallback((e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.classList.contains("db-link")) {
      const link = target.textContent;
      if (link) {
        const parsed = parseDbLink(link);
        if (parsed) {
          setSchemaTarget(parsed);
          setSchemaOpen(true);
          setHistoryOpen(false); // Close history if open
        }
      }
    }
  }, []);

  // Handle save
  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave();
    } finally {
      setSaving(false);
    }
  };

  // Handle delete
  const handleDelete = async () => {
    if (
      !confirm(
        `Delete "${path}"? ${gitEnabled ? "This will be committed to git." : "File will be moved to .trash folder."}`,
      )
    ) {
      return;
    }
    setDeleting(true);
    try {
      await onDelete();
    } finally {
      setDeleting(false);
    }
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        if (isDirty && !saving) {
          handleSave();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isDirty, saving]);

  // Track selection changes in the textarea
  const updateSelection = useCallback(() => {
    if (!editorContainerRef.current) {
      setSelection(null);
      return;
    }

    const textarea = editorContainerRef.current.querySelector("textarea");
    if (!textarea) {
      setSelection(null);
      return;
    }

    const { selectionStart, selectionEnd, value } = textarea;
    if (selectionStart === selectionEnd) {
      setSelection(null);
      return;
    }

    const selectedText = value.substring(selectionStart, selectionEnd);
    if (!selectedText.trim()) {
      setSelection(null);
      return;
    }

    // Calculate line numbers
    const textBeforeSelection = value.substring(0, selectionStart);
    const startLine = (textBeforeSelection.match(/\n/g) || []).length + 1;
    const selectedLines = (selectedText.match(/\n/g) || []).length;
    const endLine = startLine + selectedLines;

    setSelection({ text: selectedText, startLine, endLine });
  }, []);

  // Listen for selection changes on the textarea
  useEffect(() => {
    const container = editorContainerRef.current;
    if (!container) return;

    const textarea = container.querySelector("textarea");
    if (!textarea) return;

    // Update selection on mouseup and keyup within the textarea
    const handleMouseUp = () => setTimeout(updateSelection, 0);
    const handleKeyUp = () => setTimeout(updateSelection, 0);

    textarea.addEventListener("mouseup", handleMouseUp);
    textarea.addEventListener("keyup", handleKeyUp);
    textarea.addEventListener("select", updateSelection);

    return () => {
      textarea.removeEventListener("mouseup", handleMouseUp);
      textarea.removeEventListener("keyup", handleKeyUp);
      textarea.removeEventListener("select", updateSelection);
    };
  }, [updateSelection, content]); // Re-attach when content changes (textarea may be recreated)

  // Copy handlers - use stored selection
  const handleCopyText = useCallback(() => {
    const sel = selectionRef.current;
    if (sel) {
      navigator.clipboard.writeText(sel.text);
      setToast("Copied to clipboard");
    } else {
      setToast("No text selected");
    }
  }, []);

  const handleCopyReference = useCallback(() => {
    const sel = selectionRef.current;
    if (sel && connection && path) {
      const lineRef =
        sel.startLine === sel.endLine
          ? `${sel.startLine}`
          : `${sel.startLine}-${sel.endLine}`;
      const reference = `${connection}/${path}:${lineRef}`;
      navigator.clipboard.writeText(reference);
      setToast(`Copied: ${reference}`);
    } else if (!sel) {
      setToast("No text selected");
    }
  }, [connection, path]);

  // Check if path looks like a valid file (has allowed extension) or is a stock README
  const isValidFilePath = path && /\.(yaml|yml|md)$/i.test(path);
  const isFolderPath = path && !path.includes("/") && !isValidFilePath;

  // No file selected state
  if (!connection || !path) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <div className="text-center space-y-4">
          <p>Select a file from the tree to view or edit.</p>
          {hasFolderContext && (onAddViaAgent || onCreateFileForFolder) && (
            <div className="flex gap-2 justify-center">
              {onAddViaAgent && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onAddViaAgent}
                  className="text-xs border-[#EF8626] text-[#EF8626] hover:bg-[#EF8626]/10 bg-transparent"
                >
                  <PlusIcon className="mr-1" />
                  Add via Agent
                </Button>
              )}
              {onCreateFileForFolder && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onCreateFileForFolder}
                  className="text-xs border-gray-700 text-gray-300 hover:bg-gray-800"
                >
                  <PlusIcon className="mr-1" />
                  Add File
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  // Loading state for folder READMEs (waiting for content)
  if (isFolderPath && !isStockReadme && !content) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <div className="text-center">
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  // Invalid path (not a file and not a stock README)
  if (!isValidFilePath && !isStockReadme) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <div className="text-center">
          <p>Select a file from the tree to view or edit.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800 bg-gray-900/50">
        <div className="flex items-center gap-2">
          <span className="text-gray-400 text-sm font-mono">
            {connection}/{path}
            {isStockReadme && !path?.includes("/") && " (setup guide)"}
          </span>
          {isDirty && (
            <span className="text-yellow-500 text-xs">(unsaved)</span>
          )}
          {isStockReadme && (
            <span className="text-blue-400 text-xs">(read-only)</span>
          )}
          {gitEnabled && !isStockReadme && (
            <span className="text-brand text-xs" title="Git enabled">
              git
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {!isStockReadme && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={handleSave}
                disabled={!isDirty || saving || isLoading}
                className={cn(
                  "text-xs border-gray-700 bg-gray-900 hover:bg-gray-800",
                  isDirty ? "text-green-400 border-green-800" : "text-gray-500",
                )}
              >
                <SaveIcon className="mr-1" />
                {saving ? "Saving..." : "Save"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={onDiscard}
                disabled={!isDirty || isLoading}
                className="text-xs border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-400"
              >
                <UndoIcon className="mr-1" />
                Discard
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleDelete}
                disabled={deleting || isLoading}
                className="text-xs border-red-800 bg-gray-900 text-red-400 hover:bg-red-950"
              >
                <TrashIcon className="mr-1" />
                {deleting ? "Deleting..." : "Delete"}
              </Button>
              <ToolbarSeparator />
              <Button
                variant="outline"
                size="sm"
                onClick={handleCopyText}
                disabled={isLoading}
                className={cn(
                  "text-xs border-gray-700 bg-gray-900 hover:bg-gray-800",
                  selection ? "text-blue-400 border-blue-800" : "text-gray-500",
                )}
                title={
                  selection
                    ? `Copy selected text (${selection.text.length} chars)`
                    : "Select text to copy"
                }
              >
                <CopyIcon className="mr-1" />
                Copy
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleCopyReference}
                disabled={isLoading}
                className={cn(
                  "text-xs border-gray-700 bg-gray-900 hover:bg-gray-800",
                  selection ? "text-blue-400 border-blue-800" : "text-gray-500",
                )}
                title={
                  selection
                    ? `Copy reference: ${connection}/${path}:${selection.startLine}${selection.startLine !== selection.endLine ? `-${selection.endLine}` : ""}`
                    : "Select text to copy reference"
                }
              >
                <LinkIcon className="mr-1" />
                Copy Ref
              </Button>
              <ToolbarSeparator />
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSchemaOpen(true);
                  setSchemaTarget(null);
                  setHistoryOpen(false);
                }}
                disabled={isLoading}
                className="text-xs border-gray-700 bg-gray-900 hover:bg-gray-800 text-blue-400"
                title="Browse database schema"
              >
                <DatabaseIcon className="mr-1" />
                Schema
              </Button>
              {gitEnabled && (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setHistoryOpen(true);
                      setSchemaOpen(false);
                    }}
                    disabled={isLoading}
                    className="text-xs border-gray-700 bg-gray-900 hover:bg-gray-800 text-brand-light"
                    title="View version history"
                  >
                    <HistoryIcon className="mr-1" />
                    History
                  </Button>
                </>
              )}
              <ToolbarSeparator />
              {onAddViaAgent && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onAddViaAgent}
                  className="text-xs border-[#EF8626] text-[#EF8626] hover:bg-[#EF8626]/10 bg-transparent"
                  title="Add file via agent workflow"
                >
                  <PlusIcon className="mr-1" />
                  Add via Agent
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={onCreateFile}
                className="text-xs border-gray-700 text-gray-300 hover:bg-gray-800"
                title="Add file directly"
              >
                <PlusIcon className="mr-1" />
                Add File
              </Button>
            </>
          )}
          {isStockReadme && (
            <div className="flex items-center gap-2">
              {onAddViaAgent && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onAddViaAgent}
                  className="text-xs border-[#EF8626] text-[#EF8626] hover:bg-[#EF8626]/10 bg-transparent"
                >
                  <PlusIcon className="mr-1" />
                  Add via Agent
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={onCreateFile}
                className="text-xs border-gray-700 text-gray-300 hover:bg-gray-800"
              >
                <PlusIcon className="mr-1" />
                Add File
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Editor area with optional history drawer */}
      <div className="flex-1 flex overflow-hidden">
        {/* Editor or Markdown Viewer */}
        <div className="flex-1 overflow-auto">
          {isLoading ? (
            <div className="h-full flex items-center justify-center text-gray-500">
              Loading...
            </div>
          ) : isStockReadme ? (
            <div className="p-6 prose prose-invert prose-sm max-w-none">
              <Markdown
                components={{
                  h1: ({ children }) => (
                    <h1 className="text-2xl font-bold text-white mb-4 border-b border-gray-700 pb-2">
                      {children}
                    </h1>
                  ),
                  h2: ({ children }) => (
                    <h2 className="text-lg font-semibold text-gray-200 mt-6 mb-3">
                      {children}
                    </h2>
                  ),
                  p: ({ children }) => (
                    <p className="text-gray-300 mb-3 leading-relaxed">
                      {children}
                    </p>
                  ),
                  ul: ({ children }) => (
                    <ul className="list-disc list-inside text-gray-300 mb-3 space-y-1">
                      {children}
                    </ul>
                  ),
                  li: ({ children }) => (
                    <li className="text-gray-300">{children}</li>
                  ),
                  strong: ({ children }) => (
                    <strong className="text-white font-semibold">
                      {children}
                    </strong>
                  ),
                  code: ({ children, className }) => {
                    const isBlock = className?.includes("language-");
                    if (isBlock) {
                      return (
                        <code className="block bg-gray-950 p-4 rounded text-sm text-gray-300 overflow-x-auto my-3">
                          {children}
                        </code>
                      );
                    }
                    return (
                      <code className="bg-gray-800 px-1.5 py-0.5 rounded text-sm text-yellow-300">
                        {children}
                      </code>
                    );
                  },
                  pre: ({ children }) => (
                    <pre className="bg-gray-950 rounded overflow-x-auto my-3">
                      {children}
                    </pre>
                  ),
                  blockquote: ({ children }) => (
                    <blockquote className="border-l-4 border-blue-500 pl-4 italic text-gray-400 my-3">
                      {children}
                    </blockquote>
                  ),
                }}
              >
                {content}
              </Markdown>
            </div>
          ) : (
            <div ref={editorContainerRef} onClick={handleEditorClick}>
              <Editor
                value={content}
                onValueChange={onContentChange}
                highlight={highlight}
                padding={16}
                disabled={isStockReadme}
                className="min-h-full font-mono text-sm"
                style={{
                  backgroundColor: "#1a1a1a",
                  color: "#e0e0e0",
                  minHeight: "100%",
                }}
                textareaClassName="outline-none"
              />
            </div>
          )}
        </div>

        {/* History Drawer - inline on the right */}
        <HistoryDrawer
          isOpen={historyOpen}
          onClose={() => setHistoryOpen(false)}
          connection={connection}
          path={path}
          currentContent={content}
          onRevert={() => {
            setToast("Reverted to previous version");
            onRefresh?.();
          }}
        />

        {/* Schema Explorer Drawer - inline on the right */}
        <SchemaExplorer
          isOpen={schemaOpen}
          onClose={() => setSchemaOpen(false)}
          targetLink={schemaTarget}
          onInsertLink={(link) => {
            navigator.clipboard.writeText(link);
            setToast(`Copied: ${link}`);
          }}
        />
      </div>

      {/* Toast notification */}
      <Toast message={toast} onClose={() => setToast(null)} />
    </div>
  );
}
