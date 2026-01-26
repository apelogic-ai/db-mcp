"use client";

import { useCallback, useEffect, useState } from "react";
import Editor from "react-simple-code-editor";
import Prism from "prismjs";
import "prismjs/components/prism-yaml";
import "prismjs/components/prism-markdown";
import "prismjs/themes/prism-tomorrow.css";
import Markdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

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
}: CodeEditorProps) {
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

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

  // Syntax highlighting function
  const highlight = useCallback(
    (code: string) => {
      const grammar =
        language === "yaml" ? Prism.languages.yaml : Prism.languages.markdown;
      return Prism.highlight(code, grammar, language);
    },
    [language],
  );

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

  // Check if path looks like a valid file (has allowed extension) or is a stock README
  const isValidFilePath = path && /\.(yaml|yml|md)$/i.test(path);
  const isFolderPath = path && !path.includes("/") && !isValidFilePath;

  // No file selected state
  if (!connection || !path) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <div className="text-center">
          <p>Select a file from the tree to view or edit.</p>
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
            <span className="text-orange-500 text-xs" title="Git enabled">
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
            </>
          )}
          {isStockReadme && (
            <Button
              variant="outline"
              size="sm"
              onClick={onCreateFile}
              className="text-xs border-green-800 bg-gray-900 text-green-400 hover:bg-green-950"
            >
              <PlusIcon className="mr-1" />
              Create File
            </Button>
          )}
        </div>
      </div>

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
        )}
      </div>
    </div>
  );
}
