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

function normalizeCatalogKey(catalog: string | null): string {
  return catalog ?? "__default__";
}

function catalogLabel(catalog: string | null): string {
  return catalog || "default";
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
  const [catalogs, setCatalogs] = useState<Array<string | null>>([]);
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

  const loadCatalogs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await bicpCall<{
        success: boolean;
        catalogs: Array<string | null>;
        error?: string;
      }>("schema/catalogs", {});

      if (result.success) {
        setCatalogs(result.catalogs);
        // Auto-expand if only one catalog
        if (result.catalogs.length === 1) {
          setExpandedCatalogs(new Set([normalizeCatalogKey(result.catalogs[0] ?? null)]));
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
  }, []);

  const loadSchemas = useCallback(async (catalog: string | null) => {
    try {
      const result = await bicpCall<{
        success: boolean;
        schemas: SchemaInfo[];
        error?: string;
      }>("schema/schemas", { catalog });

      if (result.success) {
        setSchemas((prev) => ({ ...prev, [normalizeCatalogKey(catalog)]: result.schemas }));
      }
    } catch (e) {
      console.error("Failed to load schemas:", e);
    }
  }, []);

  const loadTables = useCallback(async (catalog: string | null, schema: string) => {
    const key = `${normalizeCatalogKey(catalog)}/${schema}`;
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
  }, []);

  const loadColumns = useCallback(async (
    catalog: string | null,
    schema: string,
    table: string
  ) => {
    const key = `${normalizeCatalogKey(catalog)}/${schema}/${table}`;
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
  }, []);

  const navigateToTarget = useCallback(async (target: ParsedLink) => {
    const { catalog, schema, table, column } = target;
    const catalogKey = normalizeCatalogKey(catalog);

    // Build highlight path
    const path = [catalogKey, schema, table, column].filter(Boolean).join("/");
    setHighlightedPath(path);

    // Expand path to target
    if (catalogKey) {
      setExpandedCatalogs((prev) => new Set([...prev, catalogKey]));
      await loadSchemas(catalog);

      if (schema) {
        const schemaKey = `${catalogKey}/${schema}`;
        setExpandedSchemas((prev) => new Set([...prev, schemaKey]));
        await loadTables(catalog, schema);

        if (table) {
          const tableKey = `${catalogKey}/${schema}/${table}`;
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
  }, [loadColumns, loadSchemas, loadTables]);

  const toggleCatalog = useCallback(
    (catalog: string | null) => {
      const catalogKey = normalizeCatalogKey(catalog);
      setExpandedCatalogs((prev) => {
        const next = new Set(prev);
        if (next.has(catalogKey)) {
          next.delete(catalogKey);
        } else {
          next.add(catalogKey);
          if (!schemas[catalogKey]) {
            loadSchemas(catalog);
          }
        }
        return next;
      });
    },
    [schemas]
  );

  const toggleSchema = useCallback(
    (catalog: string | null, schema: string) => {
      const key = `${normalizeCatalogKey(catalog)}/${schema}`;
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
    (catalog: string | null, schema: string, table: string) => {
      const key = `${normalizeCatalogKey(catalog)}/${schema}/${table}`;
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
    catalog: string | null,
    schema?: string,
    table?: string,
    column?: string
  ) => {
    if (onInsertLink) {
      const path = [normalizeCatalogKey(catalog), schema, table, column].filter(Boolean).join("/");
      const link = `db://${path}`;
      onInsertLink(link);
    }
  };

  const filterMatches = (text: string): boolean => {
    if (!searchQuery) return true;
    return text.toLowerCase().includes(searchQuery.toLowerCase());
  };

  if (!isOpen) return null;

  return (
    <div className="w-full min-w-0 border-l border-gray-700 bg-gray-900 flex h-full flex-col">
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
                key={normalizeCatalogKey(catalog)}
                catalog={catalog}
                schemas={schemas[normalizeCatalogKey(catalog)] || []}
                tables={tables}
                columns={columns}
                isExpanded={expandedCatalogs.has(normalizeCatalogKey(catalog))}
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
  catalog: string | null;
  schemas: SchemaInfo[];
  tables: Record<string, TableInfo[]>;
  columns: Record<string, ColumnInfo[]>;
  isExpanded: boolean;
  expandedSchemas: Set<string>;
  expandedTables: Set<string>;
  highlightedPath: string | null;
  searchQuery: string;
  onToggleCatalog: (catalog: string | null) => void;
  onToggleSchema: (catalog: string | null, schema: string) => void;
  onToggleTable: (catalog: string | null, schema: string, table: string) => void;
  onElementClick: (
    catalog: string | null,
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
  const path = normalizeCatalogKey(catalog);
  const isHighlighted = highlightedPath === path;

  // Filter schemas if searching
  const visibleSchemas = searchQuery
    ? schemas.filter((s) => filterMatches(s.name))
    : schemas;

  if (searchQuery && visibleSchemas.length === 0 && !filterMatches(catalog || "")) {
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
        <span className="text-sm text-gray-300 flex-1 truncate">{catalogLabel(catalog)}</span>
      </div>

      {isExpanded && (
        <div className="ml-4">
          {visibleSchemas.map((schema) => (
            <SchemaNode
              key={schema.name}
              catalog={catalog}
              schema={schema}
              tables={tables[`${normalizeCatalogKey(catalog)}/${schema.name}`] || []}
              columns={columns}
              isExpanded={expandedSchemas.has(`${normalizeCatalogKey(catalog)}/${schema.name}`)}
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
  catalog: string | null;
  schema: SchemaInfo;
  tables: TableInfo[];
  columns: Record<string, ColumnInfo[]>;
  isExpanded: boolean;
  expandedTables: Set<string>;
  highlightedPath: string | null;
  searchQuery: string;
  onToggleSchema: (catalog: string | null, schema: string) => void;
  onToggleTable: (catalog: string | null, schema: string, table: string) => void;
  onElementClick: (
    catalog: string | null,
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
  const path = `${normalizeCatalogKey(catalog)}/${schema.name}`;
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
              columns={columns[`${normalizeCatalogKey(catalog)}/${schema.name}/${table.name}`] || []}
              isExpanded={expandedTables.has(
                `${normalizeCatalogKey(catalog)}/${schema.name}/${table.name}`
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
  catalog: string | null;
  schema: string;
  table: TableInfo;
  columns: ColumnInfo[];
  isExpanded: boolean;
  highlightedPath: string | null;
  searchQuery: string;
  onToggleTable: (catalog: string | null, schema: string, table: string) => void;
  onElementClick: (
    catalog: string | null,
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
  const path = `${normalizeCatalogKey(catalog)}/${schema}/${table.name}`;
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
        onClick={() => {
          onToggleTable(catalog, schema, table.name);
          onElementClick(catalog, schema, table.name);
        }}
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
  catalog: string | null;
  schema: string;
  table: string;
  column: ColumnInfo;
  highlightedPath: string | null;
  onElementClick: (
    catalog: string | null,
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
  const path = `${normalizeCatalogKey(catalog)}/${schema}/${table}/${column.name}`;
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
    catalog: parts[0] && parts[0] !== "__default__" ? parts[0] : null,
    schema: parts[1] || null,
    table: parts[2] || null,
    column: parts[3] || null,
  };
}
