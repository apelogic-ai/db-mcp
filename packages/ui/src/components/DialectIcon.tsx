/**
 * Gray contour icons for database flavors.
 * Official logo silhouettes rendered as monochrome SVGs.
 */

interface DialectIconProps {
  dialect: string | null;
  className?: string;
  size?: number;
}

export function DialectIcon({ dialect, className = "", size = 20 }: DialectIconProps) {
  const color = "currentColor";
  const props = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", className: `text-gray-400 ${className}` };

  switch (dialect) {
    case "postgresql":
      // PostgreSQL elephant silhouette
      return (
        <svg {...props} viewBox="0 0 24 24">
          <path d="M17.5 3.5c-1.5-1-3.5-1.5-5.5-1.5S8 2.5 6.5 3.5C5 4.5 4 6 3.5 8s-.5 4.5 0 6.5 1.5 3.5 3 4.5c.5.5 1.2.5 1.8.2.5-.3.7-.8.7-1.4v-2.5c0-.5.2-1 .5-1.3.3-.3.8-.5 1.3-.5h2.5c.5 0 1-.2 1.3-.5.3-.3.5-.8.5-1.3V8.5c0-1-.3-2-.8-2.8s-1.2-1.4-2-1.8" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M14.5 13.5v4.3c0 .5.2 1 .6 1.3.4.3.9.4 1.4.2 1.5-.5 2.7-1.5 3.5-2.8s1.2-2.8 1-4.5c-.2-1.5-.8-2.8-1.8-3.8" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          <circle cx="10" cy="8" r="1" fill={color}/>
          <circle cx="14" cy="8" r="1" fill={color}/>
        </svg>
      );

    case "mysql":
      // MySQL dolphin simplified
      return (
        <svg {...props} viewBox="0 0 24 24">
          <path d="M12 3C7 3 3 6.5 3 11c0 2.5 1.2 4.7 3 6.2V21l3-2c1 .3 2 .5 3 .5 5 0 9-3.5 9-8s-4-8.5-9-8.5z" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M8 10h2l1 4 1-4h2" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      );

    case "clickhouse":
      // ClickHouse column bars
      return (
        <svg {...props} viewBox="0 0 24 24">
          <rect x="4" y="4" width="2.5" height="16" rx="0.5" fill={color} opacity="0.7"/>
          <rect x="8" y="7" width="2.5" height="13" rx="0.5" fill={color} opacity="0.7"/>
          <rect x="12" y="4" width="2.5" height="16" rx="0.5" fill={color} opacity="0.7"/>
          <rect x="16" y="9" width="2.5" height="11" rx="0.5" fill={color} opacity="0.7"/>
        </svg>
      );

    case "trino":
      // Trino rabbit ear silhouette
      return (
        <svg {...props} viewBox="0 0 24 24">
          <path d="M12 20c-3 0-5.5-2-6-5-.3-2 .3-4 1.5-5.5L9 6V3c0-.5.5-1 1-1s1 .5 1 1v2h2V3c0-.5.5-1 1-1s1 .5 1 1v3l1.5 3.5c1.2 1.5 1.8 3.5 1.5 5.5-.5 3-3 5-6 5z" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          <circle cx="10" cy="13" r="1" fill={color}/>
          <circle cx="14" cy="13" r="1" fill={color}/>
        </svg>
      );

    case "mssql":
      // SQL Server — simplified database with "S"
      return (
        <svg {...props} viewBox="0 0 24 24">
          <ellipse cx="12" cy="6" rx="7" ry="3" stroke={color} strokeWidth="1.5"/>
          <path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6" stroke={color} strokeWidth="1.5"/>
          <path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3" stroke={color} strokeWidth="1.5"/>
        </svg>
      );

    case "sqlite":
      // SQLite — feather/lightweight
      return (
        <svg {...props} viewBox="0 0 24 24">
          <path d="M12 2L4 8v8l8 6 8-6V8l-8-6z" stroke={color} strokeWidth="1.5" strokeLinejoin="round"/>
          <path d="M12 8v8M8 12h8" stroke={color} strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
      );

    case "duckdb":
      // DuckDB — duck bill silhouette
      return (
        <svg {...props} viewBox="0 0 24 24">
          <path d="M8 6c-2 0-3.5 1.5-3.5 3.5S6 13 8 13h2c1.5 0 3 .5 4 1.5 1 1 1.5 2.5 1.5 4v1.5h3V18c0-2-1-3.8-2.5-5S12.5 11 10 11H8c-.8 0-1.5-.7-1.5-1.5S7.2 8 8 8h6l2-2H8z" fill={color} opacity="0.7"/>
          <circle cx="7" cy="9.5" r="1" fill="currentColor" className="text-gray-900"/>
        </svg>
      );

    default:
      // Generic database icon
      return (
        <svg {...props} viewBox="0 0 24 24">
          <ellipse cx="12" cy="6" rx="7" ry="3" stroke={color} strokeWidth="1.5"/>
          <path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6" stroke={color} strokeWidth="1.5"/>
          <path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3" stroke={color} strokeWidth="1.5"/>
        </svg>
      );
  }
}
