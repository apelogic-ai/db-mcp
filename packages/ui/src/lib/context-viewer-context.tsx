"use client";

import {
  createContext,
  useContext,
  useState,
  useCallback,
  ReactNode,
} from "react";
import { ConnectionNode } from "@/components/context/TreeView";

interface SelectedFile {
  connection: string;
  path: string;
}

interface ContextViewerState {
  // Tree data
  connections: ConnectionNode[];
  setConnections: (connections: ConnectionNode[]) => void;

  // Selection state
  selectedFile: SelectedFile | null;
  setSelectedFile: (file: SelectedFile | null) => void;

  // Editor content
  content: string;
  setContent: (content: string) => void;
  originalContent: string;
  setOriginalContent: (content: string) => void;
  isStockReadme: boolean;
  setIsStockReadme: (isStock: boolean) => void;

  // Expansion state
  expandedConnections: Set<string>;
  toggleConnection: (name: string) => void;
  expandedFolders: Set<string>;
  toggleFolder: (key: string) => void;

  // Tree panel width
  treeWidth: number;
  setTreeWidth: (width: number) => void;

  // Dirty state helper
  isDirty: boolean;
}

const ContextViewerContext = createContext<ContextViewerState | null>(null);

export function ContextViewerProvider({ children }: { children: ReactNode }) {
  // Tree data
  const [connections, setConnections] = useState<ConnectionNode[]>([]);

  // Selection state
  const [selectedFile, setSelectedFile] = useState<SelectedFile | null>(null);

  // Editor content
  const [content, setContent] = useState("");
  const [originalContent, setOriginalContent] = useState("");
  const [isStockReadme, setIsStockReadme] = useState(false);

  // Expansion state
  const [expandedConnections, setExpandedConnections] = useState<Set<string>>(
    new Set()
  );
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(
    new Set()
  );

  // Tree panel width
  const [treeWidth, setTreeWidth] = useState(280);

  const toggleConnection = useCallback((name: string) => {
    setExpandedConnections((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  }, []);

  const toggleFolder = useCallback((key: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  const isDirty = content !== originalContent;

  return (
    <ContextViewerContext.Provider
      value={{
        connections,
        setConnections,
        selectedFile,
        setSelectedFile,
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
      }}
    >
      {children}
    </ContextViewerContext.Provider>
  );
}

export function useContextViewer() {
  const context = useContext(ContextViewerContext);
  if (!context) {
    throw new Error(
      "useContextViewer must be used within a ContextViewerProvider"
    );
  }
  return context;
}
