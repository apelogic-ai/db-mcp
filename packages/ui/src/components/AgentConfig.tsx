"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useBICP } from "@/lib/bicp-context";
import { AgentIcon } from "@/components/AgentIcon";

interface Agent {
  id: string;
  name: string;
  installed: boolean;
  configPath: string;
  configExists: boolean;
  configFormat: string;
  dbmcpConfigured: boolean;
  binaryPath: string | null;
}

interface AgentsListResult {
  agents: Agent[];
}

interface ConfigureResult {
  success: boolean;
  configPath?: string;
  error?: string;
}

interface RemoveResult {
  success: boolean;
  error?: string;
}

interface SnippetResult {
  success: boolean;
  snippet: string;
  format: string;
  configKey: string;
}

interface WriteResult {
  success: boolean;
  error?: string;
}

export default function AgentConfig() {
  const { call, isInitialized } = useBICP();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [editedSnippet, setEditedSnippet] = useState<Record<string, string>>(
    {},
  );
  const [originalSnippet, setOriginalSnippet] = useState<
    Record<string, string>
  >({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await call<AgentsListResult>("agents/list");
      setAgents(result.agents);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [call]);

  useEffect(() => {
    if (isInitialized) {
      loadAgents();
    }
  }, [isInitialized, loadAgents]);

  const handleConfigure = async (agentId: string) => {
    setActionLoading(agentId);
    try {
      const result = await call<ConfigureResult>("agents/configure", {
        agentId,
      });
      if (!result.success) {
        setError(result.error || "Failed to configure agent");
      }
      await loadAgents();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionLoading(null);
    }
  };

  const handleRemove = async (agentId: string) => {
    setActionLoading(agentId);
    try {
      const result = await call<RemoveResult>("agents/remove", { agentId });
      if (!result.success) {
        setError(result.error || "Failed to remove configuration");
      }
      await loadAgents();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionLoading(null);
    }
  };

  const handleEditConfig = async (agentId: string) => {
    if (editing === agentId) {
      setEditing(null);
      setSaveError(null);
      return;
    }
    // Fetch snippet if we don't have it yet
    if (!originalSnippet[agentId]) {
      try {
        const result = await call<SnippetResult>("agents/config-snippet", {
          agentId,
        });
        if (result.success) {
          setOriginalSnippet((prev) => ({
            ...prev,
            [agentId]: result.snippet,
          }));
          setEditedSnippet((prev) => ({
            ...prev,
            [agentId]: result.snippet,
          }));
        }
      } catch {
        return;
      }
    } else {
      setEditedSnippet((prev) => ({
        ...prev,
        [agentId]: originalSnippet[agentId],
      }));
    }
    setEditing(agentId);
    setSaveError(null);
  };

  const handleCancel = () => {
    setEditing(null);
    setSaveError(null);
  };

  const handleSave = async (agentId: string) => {
    setSaving(true);
    setSaveError(null);
    try {
      const result = await call<WriteResult>("agents/config-write", {
        agentId,
        snippet: editedSnippet[agentId],
      });
      if (result.success) {
        setOriginalSnippet((prev) => ({
          ...prev,
          [agentId]: editedSnippet[agentId],
        }));
        setEditing(null);
        await loadAgents();
      } else {
        setSaveError(result.error || "Failed to save config");
      }
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="bg-gray-900 border-gray-800">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-white flex items-center gap-2">
              Agent Configuration
              {loading && (
                <Badge
                  variant="secondary"
                  className="bg-gray-800 text-gray-300"
                >
                  Loading...
                </Badge>
              )}
            </CardTitle>
            <CardDescription className="text-gray-400">
              Add or remove db-mcp from MCP-compatible agents.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {error && (
          <div className="p-3 mb-4 bg-red-950 border border-red-800 rounded text-red-300 text-sm">
            {error}
          </div>
        )}
        {!loading && agents.length === 0 && (
          <p className="text-gray-500 text-sm">No agents detected.</p>
        )}
        {agents.length > 0 && (
          <div className="space-y-3">
            {agents.map((agent) => (
              <div
                key={agent.id}
                data-testid={`agent-${agent.id}`}
                className={`p-4 rounded-lg border ${
                  agent.installed
                    ? "border-gray-700 bg-gray-800/50"
                    : "border-gray-800 bg-gray-900/50 opacity-60"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <AgentIcon agentId={agent.id} size={20} />
                    <span className="text-white font-medium">{agent.name}</span>
                  </div>
                  {agent.installed && (
                    <div className="flex items-center gap-2">
                      {agent.configExists && editing !== agent.id && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleEditConfig(agent.id)}
                          className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300 text-xs"
                        >
                          Edit Config
                        </Button>
                      )}
                      {agent.dbmcpConfigured ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleRemove(agent.id)}
                          disabled={actionLoading === agent.id}
                          className="border-red-800 bg-gray-900 hover:bg-red-950 text-red-400 text-xs"
                        >
                          {actionLoading === agent.id
                            ? "Removing..."
                            : "Remove"}
                        </Button>
                      ) : (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleConfigure(agent.id)}
                          disabled={actionLoading === agent.id}
                          className="border-green-800 bg-gray-900 hover:bg-green-950 text-green-400 text-xs"
                        >
                          {actionLoading === agent.id ? "Adding..." : "Add"}
                        </Button>
                      )}
                    </div>
                  )}
                </div>
                <p className="text-gray-500 text-xs mt-1 font-mono">
                  {agent.configPath}
                </p>
                {editing === agent.id && (
                  <div className="mt-3">
                    <textarea
                      data-testid={`snippet-editor-${agent.id}`}
                      value={editedSnippet[agent.id] ?? ""}
                      onChange={(e) =>
                        setEditedSnippet((prev) => ({
                          ...prev,
                          [agent.id]: e.target.value,
                        }))
                      }
                      className="w-full p-3 bg-gray-950 border border-gray-700 rounded text-xs text-gray-300 font-mono resize-y min-h-[120px] focus:outline-none focus:border-blue-600"
                      spellCheck={false}
                    />
                    {saveError && (
                      <div
                        data-testid={`save-error-${agent.id}`}
                        className="mt-2 p-2 bg-red-950 border border-red-800 rounded text-red-300 text-xs"
                      >
                        {saveError}
                      </div>
                    )}
                    <div className="flex items-center gap-2 mt-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleSave(agent.id)}
                        disabled={saving}
                        className="border-green-800 bg-gray-900 hover:bg-green-950 text-green-400 text-xs"
                      >
                        {saving ? "Saving..." : "Save"}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleCancel}
                        disabled={saving}
                        className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300 text-xs"
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
