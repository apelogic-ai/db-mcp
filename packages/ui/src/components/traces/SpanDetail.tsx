"use client";

import type { TraceSpan } from "@/lib/bicp";
import { Badge } from "@/components/ui/badge";

interface SpanDetailProps {
  span: TraceSpan;
}

export function SpanDetail({ span }: SpanDetailProps) {
  const attributes = Object.entries(span.attributes || {});

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-md p-4 space-y-3">
      <div className="flex items-center gap-2">
        <h4 className="text-sm font-medium text-white font-mono">
          {span.name}
        </h4>
        <Badge
          variant="secondary"
          className={
            span.status === "error"
              ? "bg-red-900/50 text-red-300"
              : "bg-green-900/50 text-green-300"
          }
        >
          {span.status}
        </Badge>
        {span.duration_ms !== null && (
          <span className="text-xs text-gray-500">
            {span.duration_ms.toFixed(1)}ms
          </span>
        )}
      </div>

      <div className="text-xs text-gray-500 font-mono space-y-0.5">
        <div>span_id: {span.span_id}</div>
        <div>trace_id: {span.trace_id}</div>
        {span.parent_span_id && (
          <div>parent: {span.parent_span_id}</div>
        )}
      </div>

      {attributes.length > 0 && (
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-800">
              <th className="text-left text-gray-500 py-1 pr-4 font-medium">
                Attribute
              </th>
              <th className="text-left text-gray-500 py-1 font-medium">
                Value
              </th>
            </tr>
          </thead>
          <tbody>
            {attributes.map(([key, value]) => {
              const strValue = typeof value === "string" ? value : JSON.stringify(value);
              const isLong = strValue.length > 80;

              return (
                <tr key={key} className="border-b border-gray-800/50">
                  <td className="text-gray-400 py-1.5 pr-4 font-mono align-top whitespace-nowrap">
                    {key}
                  </td>
                  <td className="text-gray-300 py-1.5 font-mono">
                    {isLong ? (
                      <pre className="whitespace-pre-wrap break-all text-xs">
                        {strValue}
                      </pre>
                    ) : (
                      strValue
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {span.events && span.events.length > 0 && (
        <div className="space-y-1">
          <h5 className="text-xs text-gray-500 font-medium">Events</h5>
          {span.events.map((event, i) => (
            <div key={i} className="text-xs text-gray-400 font-mono">
              {event.name}
              {event.attributes && Object.keys(event.attributes).length > 0 && (
                <span className="text-gray-600 ml-2">
                  {JSON.stringify(event.attributes)}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
