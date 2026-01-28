"use client";

import { useCallback, useEffect, useState } from "react";
import { bicpCall } from "@/lib/bicp";
import { cn } from "@/lib/utils";

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
    <path d="M18 6L6 18" />
    <path d="M6 6l12 12" />
  </svg>
);

const ChevronRightIcon = ({ className }: { className?: string }) => (
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
    <path d="m9 18 6-6-6-6" />
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

const TableIcon = ({ className }: { className?: string }) => (
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
    <path d="M12 3v18" />
    <rect width="18" height="18" x="3" y="3" rx="2" />
    <path d="M3 9h18" />
    <path d="M3 15h18" />
  </svg>
);

const ColumnIcon = ({ className }: { className?: string }) => (
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
    <path d="M3 3h18" />
    <path d="M3 9h18" />
    <path d="M3 15h18" />
    <path d="M3 21h18" />
  </svg>
);

const KeyIcon = ({ className }: { className?: string }) => (
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
    <circle cx="7.5" cy="15.5" r="5.5" />
    <path d="m21 2-9.6 9.6" />
    <path d="m15.5 7.5 3 3L22 7l-3-3" />
  </svg>
);

const SearchIcon = ({ className }: { className?: string }) => (
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
    <circle cx="11" cy="11" r="8" />
    <path d="m21 21-4.3-4.3" />
  </svg>
);

// Types
interface SchemaInfo {
  name: string;
  catalog: string | null;
  tableCount: number | null;
}

interface TableInfo {
  name: string;
  description: string | null;
}

interface ColumnInfo {
  name: string;
  type: string;
  nullable: boolean;
  description: string | null;
  isPrimaryKey: boolean;
}

interface ParsedLink {
  catalog: string | null;
  schema: string | null;
  table: string | null;
  column: string | null;
}

interface SchemaExplorerProps {
  isOpen: boolean;
  onClose: () => void;
  /** Navigate to a specific location from a db:// link */
  targetLink?: ParsedLink | null;
  /** Callback when user clicks on a schema element to insert a link */
  onInsertLink?: (link: string) => void;
}

export function SchemaExplorer({
  isOpen,
  onClose,
  targetLink,
  onInsertLink,
}: SchemaExplorerProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Data
  const [catalogs, setCatalogs] = useState<string[]>([]);
  const [schemas, setSchemas] = useState<Record<string, SchemaInfo[]>>({});
  const [tables, setTables] = useState<Record<string, TableInfo[]>>({});
  const [columns, setColumns] = useState<Record<string, ColumnInfo[]>>({});

  // Expansion state
  const [expandedCatalogs, setExpandedCatalogs] = useState<Set<string>>(
    new Set()
  );
  const [expandedSchemas, setExpandedSchemas] = useState<Set<string>>(
    new Set()
  );
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set());

  // Highlighted element from targetLink
  const [highlightedPath, setHighlightedPath] = useState<string | null>(null);

  // Load catalogs on open
  useEffect(() => {
    if (isOpen) {
      loadCatalogs();
    }
  }, [isOpen]);

  // Navigate to target when it changes
  useEffect(() => {
    if (isOpen && targetLink) {
      navigateToTarget(targetLink);
    }
  }, [isOpen, targetLink]);

  const loadCatalogs = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await bicpCall<{
        success: boolean;
        catalogs: string[];
        error?: string;
      }>("schema/catalogs", {});

      if (result.success) {
        setCatalogs(result.catalogs);
        // Auto-expand if only one catalog
        if (result.catalogs.length === 1) {
          setExpandedCatalogs(new Set([result.catalogs[0]]));
          loadSchemas(result.catalogs[0]);
        }
      } else {
        setError(result.error || "Failed to load catalogs");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load catalogs");
    } finally {
      setIsLoading(false);
    }
  };

  const loadSchemas = async (catalog: string) => {
    try {
      const result = await bicpCall<{
        success: boolean;
        schemas: SchemaInfo[];
        error?: string;
      }>("schema/schemas", { catalog });

      if (result.success) {
        setSchemas((prev) => ({ ...prev, [catalog]: result.schemas }));
      }
    } catch (e) {
      console.error("Failed to load schemas:", e);
    }
  };

  const loadTables = async (catalog: string, schema: string) => {
    const key = `${catalog}/${schema}`;
    try {
      const result = await bicpCall<{
        success: boolean;
        tables: TableInfo[];
        error?: string;
      }>("schema/tables", { catalog, schema });

      if (result.success) {
        setTables((prev) => ({ ...prev, [key]: result.tables }));
      }
    } catch (e) {
      console.error("Failed to load tables:", e);
    }
  };

  const loadColumns = async (
    catalog: string,
    schema: string,
    table: string
  ) => {
    const key = `${catalog}/${schema}/${table}`;
    try {
      const result = await bicpCall<{
        success: boolean;
        columns: ColumnInfo[];
        error?: string;
      }>("schema/columns", { catalog, schema, table });

      if (result.success) {
        setColumns((prev) => ({ ...prev, [key]: result.columns }));
      }
    } catch (e) {
      console.error("Failed to load columns:", e);
    }
  };

  const navigateToTarget = async (target: ParsedLink) => {
    const { catalog, schema, table, column } = target;

    // Build highlight path
    let path = "";
    if (catalog) path += catalog;
    if (schema) path += `/${schema}`;
    if (table) path += `/${table}`;
    if (column) path += `/${column}`;
    setHighlightedPath(path);

    // Expand path to target
    if (catalog) {
      setExpandedCatalogs((prev) => new Set([...prev, catalog]));
      await loadSchemas(catalog);

      if (schema) {
        const schemaKey = `${catalog}/${schema}`;
        setExpandedSchemas((prev) => new Set([...prev, schemaKey]));
        await loadTables(catalog, schema);

        if (table) {
          const tableKey = `${catalog}/${schema}/${table}`;
          setExpandedTables((prev) => new Set([...prev, tableKey]));
          await loadColumns(catalog, schema, table);
        }
      }
    }

    // Scroll to highlighted element after a short delay
    setTimeout(() => {
      const element = document.querySelector(`[data-path="${path}"]`);
      if (element) {
        element.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 100);
  };

  const toggleCatalog = useCallback(
    (catalog: string) => {
      setExpandedCatalogs((prev) => {
        const next = new Set(prev);
        if (next.has(catalog)) {
          next.delete(catalog);
        } else {
          next.add(catalog);
          if (!schemas[catalog]) {
            loadSchemas(catalog);
          }
        }
        return next;
      });
    },
    [schemas]
  );

  const toggleSchema = useCallback(
    (catalog: string, schema: string) => {
      const key = `${catalog}/${schema}`;
      setExpandedSchemas((prev) => {
        const next = new Set(prev);
        if (next.has(key)) {
          next.delete(key);
        } else {
          next.add(key);
          if (!tables[key]) {
            loadTables(catalog, schema);
          }
        }
        return next;
      });
    },
    [tables]
  );

  const toggleTable = useCallback(
    (catalog: string, schema: string, table: string) => {
      const key = `${catalog}/${schema}/${table}`;
      setExpandedTables((prev) => {
        const next = new Set(prev);
        if (next.has(key)) {
          next.delete(key);
        } else {
          next.add(key);
          if (!columns[key]) {
            loadColumns(catalog, schema, table);
          }
        }
        return next;
      });
    },
    [columns]
  );

  const handleElementClick = (
    catalog: string,
    schema?: string,
    table?: string,
    column?: string
  ) => {
    if (onInsertLink) {
      let link = `db://${catalog}`;
      if (schema) link += `/${schema}`;
      if (table) link += `/${table}`;
      if (column) link += `/${column}`;
      onInsertLink(link);
    }
  };

  const filterMatches = (text: string): boolean => {
    if (!searchQuery) return true;
    return text.toLowerCase().includes(searchQuery.toLowerCase());
  };

  if (!isOpen) return null;

  return (
    <div className="w-96 border-l border-gray-700 bg-gray-900 flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <DatabaseIcon className="text-blue-400" />
          <h2 className="text-sm font-medium text-gray-200">Database Schema</h2>
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-200 p-1 rounded hover:bg-gray-800"
        >
          <CloseIcon />
        </button>
      </div>

      {/* Search */}
      <div className="px-3 py-2 border-b border-gray-800">
        <div className="relative">
          <SearchIcon className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search tables, columns..."
            className="w-full pl-8 pr-3 py-1.5 bg-gray-950 border border-gray-700 rounded text-sm text-gray-300 placeholder-gray-500 focus:outline-none focus:border-gray-600"
          />
        </div>
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto p-2">
        {isLoading && catalogs.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-gray-500 text-sm">
            Loading...
          </div>
        ) : error ? (
          <div className="p-3 text-red-400 text-sm">{error}</div>
        ) : catalogs.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-gray-500 text-sm">
            No catalogs found
          </div>
        ) : (
          <div className="space-y-0.5">
            {catalogs.map((catalog) => (
              <CatalogNode
                key={catalog}
                catalog={catalog}
                schemas={schemas[catalog] || []}
                tables={tables}
                columns={columns}
                isExpanded={expandedCatalogs.has(catalog)}
                expandedSchemas={expandedSchemas}
                expandedTables={expandedTables}
                highlightedPath={highlightedPath}
                searchQuery={searchQuery}
                onToggleCatalog={toggleCatalog}
                onToggleSchema={toggleSchema}
                onToggleTable={toggleTable}
                onElementClick={handleElementClick}
                filterMatches={filterMatches}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer hint */}
      <div className="px-3 py-2 border-t border-gray-800 text-xs text-gray-500">
        Click an element to copy its db:// link
      </div>
    </div>
  );
}

// Catalog node component
interface CatalogNodeProps {
  catalog: string;
  schemas: SchemaInfo[];
  tables: Record<string, TableInfo[]>;
  columns: Record<string, ColumnInfo[]>;
  isExpanded: boolean;
  expandedSchemas: Set<string>;
  expandedTables: Set<string>;
  highlightedPath: string | null;
  searchQuery: string;
  onToggleCatalog: (catalog: string) => void;
  onToggleSchema: (catalog: string, schema: string) => void;
  onToggleTable: (catalog: string, schema: string, table: string) => void;
  onElementClick: (
    catalog: string,
    schema?: string,
    table?: string,
    column?: string
  ) => void;
  filterMatches: (text: string) => boolean;
}

function CatalogNode({
  catalog,
  schemas,
  tables,
  columns,
  isExpanded,
  expandedSchemas,
  expandedTables,
  highlightedPath,
  searchQuery,
  onToggleCatalog,
  onToggleSchema,
  onToggleTable,
  onElementClick,
  filterMatches,
}: CatalogNodeProps) {
  const path = catalog;
  const isHighlighted = highlightedPath === path;

  // Filter schemas if searching
  const visibleSchemas = searchQuery
    ? schemas.filter((s) => filterMatches(s.name))
    : schemas;

  if (searchQuery && visibleSchemas.length === 0 && !filterMatches(catalog)) {
    return null;
  }

  return (
    <div>
      <div
        data-path={path}
        className={cn(
          "flex items-center gap-1 px-2 py-1 rounded cursor-pointer hover:bg-gray-800",
          isHighlighted && "bg-blue-900/30 ring-1 ring-blue-500"
        )}
        onClick={() => onToggleCatalog(catalog)}
        onDoubleClick={() => onElementClick(catalog)}
      >
        <ChevronRightIcon
          className={cn(
            "text-gray-500 transition-transform",
            isExpanded && "rotate-90"
          )}
        />
        <DatabaseIcon className="text-purple-400" />
        <span className="text-sm text-gray-300 flex-1 truncate">{catalog}</span>
      </div>

      {isExpanded && (
        <div className="ml-4">
          {visibleSchemas.map((schema) => (
            <SchemaNode
              key={schema.name}
              catalog={catalog}
              schema={schema}
              tables={tables[`${catalog}/${schema.name}`] || []}
              columns={columns}
              isExpanded={expandedSchemas.has(`${catalog}/${schema.name}`)}
              expandedTables={expandedTables}
              highlightedPath={highlightedPath}
              searchQuery={searchQuery}
              onToggleSchema={onToggleSchema}
              onToggleTable={onToggleTable}
              onElementClick={onElementClick}
              filterMatches={filterMatches}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// Schema node component
interface SchemaNodeProps {
  catalog: string;
  schema: SchemaInfo;
  tables: TableInfo[];
  columns: Record<string, ColumnInfo[]>;
  isExpanded: boolean;
  expandedTables: Set<string>;
  highlightedPath: string | null;
  searchQuery: string;
  onToggleSchema: (catalog: string, schema: string) => void;
  onToggleTable: (catalog: string, schema: string, table: string) => void;
  onElementClick: (
    catalog: string,
    schema?: string,
    table?: string,
    column?: string
  ) => void;
  filterMatches: (text: string) => boolean;
}

function SchemaNode({
  catalog,
  schema,
  tables,
  columns,
  isExpanded,
  expandedTables,
  highlightedPath,
  searchQuery,
  onToggleSchema,
  onToggleTable,
  onElementClick,
  filterMatches,
}: SchemaNodeProps) {
  const path = `${catalog}/${schema.name}`;
  const isHighlighted = highlightedPath === path;

  // Filter tables if searching
  const visibleTables = searchQuery
    ? tables.filter((t) => filterMatches(t.name))
    : tables;

  if (
    searchQuery &&
    visibleTables.length === 0 &&
    !filterMatches(schema.name)
  ) {
    return null;
  }

  return (
    <div>
      <div
        data-path={path}
        className={cn(
          "flex items-center gap-1 px-2 py-1 rounded cursor-pointer hover:bg-gray-800",
          isHighlighted && "bg-blue-900/30 ring-1 ring-blue-500"
        )}
        onClick={() => onToggleSchema(catalog, schema.name)}
        onDoubleClick={() => onElementClick(catalog, schema.name)}
      >
        <ChevronRightIcon
          className={cn(
            "text-gray-500 transition-transform",
            isExpanded && "rotate-90"
          )}
        />
        <DatabaseIcon className="text-cyan-400" />
        <span className="text-sm text-gray-300 flex-1 truncate">
          {schema.name}
        </span>
        {schema.tableCount !== null && (
          <span className="text-xs text-gray-500">{schema.tableCount}</span>
        )}
      </div>

      {isExpanded && (
        <div className="ml-4">
          {visibleTables.map((table) => (
            <TableNode
              key={table.name}
              catalog={catalog}
              schema={schema.name}
              table={table}
              columns={columns[`${catalog}/${schema.name}/${table.name}`] || []}
              isExpanded={expandedTables.has(
                `${catalog}/${schema.name}/${table.name}`
              )}
              highlightedPath={highlightedPath}
              searchQuery={searchQuery}
              onToggleTable={onToggleTable}
              onElementClick={onElementClick}
              filterMatches={filterMatches}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// Table node component
interface TableNodeProps {
  catalog: string;
  schema: string;
  table: TableInfo;
  columns: ColumnInfo[];
  isExpanded: boolean;
  highlightedPath: string | null;
  searchQuery: string;
  onToggleTable: (catalog: string, schema: string, table: string) => void;
  onElementClick: (
    catalog: string,
    schema?: string,
    table?: string,
    column?: string
  ) => void;
  filterMatches: (text: string) => boolean;
}

function TableNode({
  catalog,
  schema,
  table,
  columns,
  isExpanded,
  highlightedPath,
  searchQuery,
  onToggleTable,
  onElementClick,
  filterMatches,
}: TableNodeProps) {
  const path = `${catalog}/${schema}/${table.name}`;
  const isHighlighted = highlightedPath === path;

  // Filter columns if searching
  const visibleColumns = searchQuery
    ? columns.filter((c) => filterMatches(c.name))
    : columns;

  if (
    searchQuery &&
    visibleColumns.length === 0 &&
    !filterMatches(table.name)
  ) {
    return null;
  }

  return (
    <div>
      <div
        data-path={path}
        className={cn(
          "flex items-center gap-1 px-2 py-1 rounded cursor-pointer hover:bg-gray-800 group",
          isHighlighted && "bg-blue-900/30 ring-1 ring-blue-500"
        )}
        onClick={() => onToggleTable(catalog, schema, table.name)}
        onDoubleClick={() => onElementClick(catalog, schema, table.name)}
      >
        <ChevronRightIcon
          className={cn(
            "text-gray-500 transition-transform",
            isExpanded && "rotate-90"
          )}
        />
        <TableIcon className="text-green-400" />
        <span className="text-sm text-gray-300 flex-1 truncate">
          {table.name}
        </span>
      </div>

      {table.description && (
        <div className="ml-8 px-2 text-xs text-gray-500 truncate">
          {table.description}
        </div>
      )}

      {isExpanded && (
        <div className="ml-4">
          {visibleColumns.map((column) => (
            <ColumnNode
              key={column.name}
              catalog={catalog}
              schema={schema}
              table={table.name}
              column={column}
              highlightedPath={highlightedPath}
              onElementClick={onElementClick}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// Column node component
interface ColumnNodeProps {
  catalog: string;
  schema: string;
  table: string;
  column: ColumnInfo;
  highlightedPath: string | null;
  onElementClick: (
    catalog: string,
    schema?: string,
    table?: string,
    column?: string
  ) => void;
}

function ColumnNode({
  catalog,
  schema,
  table,
  column,
  highlightedPath,
  onElementClick,
}: ColumnNodeProps) {
  const path = `${catalog}/${schema}/${table}/${column.name}`;
  const isHighlighted = highlightedPath === path;

  return (
    <div
      data-path={path}
      className={cn(
        "flex items-center gap-1 px-2 py-1 rounded cursor-pointer hover:bg-gray-800 ml-4",
        isHighlighted && "bg-blue-900/30 ring-1 ring-blue-500"
      )}
      onClick={() => onElementClick(catalog, schema, table, column.name)}
      title={column.description || `${column.type}${column.nullable ? " (nullable)" : ""}`}
    >
      {column.isPrimaryKey ? (
        <KeyIcon className="text-yellow-400" />
      ) : (
        <ColumnIcon className="text-gray-500" />
      )}
      <span className="text-sm text-gray-300 truncate">{column.name}</span>
      <span className="text-xs text-gray-600 ml-auto">{column.type}</span>
      {!column.nullable && (
        <span className="text-xs text-red-400 ml-1">*</span>
      )}
    </div>
  );
}

// Helper to parse db:// links
export function parseDbLink(link: string): ParsedLink | null {
  if (!link.startsWith("db://")) return null;

  const parts = link.slice(5).split("/");
  return {
    catalog: parts[0] || null,
    schema: parts[1] || null,
    table: parts[2] || null,
    column: parts[3] || null,
  };
}
