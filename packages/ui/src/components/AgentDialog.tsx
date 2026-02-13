"use client";

import { useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { bicpCall } from "@/lib/bicp";

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

function getAgentUrlScheme(agentId: string): string | null {
  switch (agentId) {
    case "claude-desktop":
    case "claude-code":
      return "claude://";
    case "codex":
      return "codex://";
    default:
      return null;
  }
}

function CopyablePrompt({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Ignore clipboard errors
    }
  };

  return (
    <li
      onClick={handleCopy}
      className="relative cursor-pointer text-gray-400 text-xs hover:text-gray-200 transition-colors"
    >
      {copied && (
        <span className="absolute -top-6 left-1/2 -translate-x-1/2 bg-gray-700 text-green-400 text-[10px] px-2 py-0.5 rounded whitespace-nowrap transition-opacity duration-300">
          Copied!
        </span>
      )}
      &ldquo;{text}&rdquo;
    </li>
  );
}

export interface AgentDialogProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  prompts: string[];
}

export function AgentDialog({
  open,
  onClose,
  title = "Add via Agent",
  description = "Most context files use structured formats that are best created through your AI agent.",
  prompts,
}: AgentDialogProps) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(false);

  const loadAgents = useCallback(async () => {
    setAgentsLoading(true);
    try {
      const result = await bicpCall<AgentsListResult>("agents/list", {});
      setAgents(result.agents);
    } catch {
      setAgents([]);
    } finally {
      setAgentsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      loadAgents();
    }
  }, [open, loadAgents]);

  if (!open) return null;

  const installedAgents = agents.filter(
    (agent) => agent.installed && getAgentUrlScheme(agent.id),
  );

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 w-96">
        <h3 className="text-white font-medium mb-4">{title}</h3>
        <div className="space-y-4 text-gray-300 text-sm">
          <p>{description}</p>
          {prompts.length > 0 && (
            <div>
              <p className="text-gray-400 mb-2">Example prompts (click to copy):</p>
              <ul className="list-disc list-inside space-y-2">
                {prompts.map((prompt, i) => (
                  <CopyablePrompt key={i} text={prompt} />
                ))}
              </ul>
            </div>
          )}
          {agentsLoading ? (
            <p className="text-gray-400 text-xs">Loading agents...</p>
          ) : (
            <div>
              <p className="text-gray-400 mb-2 text-xs">Open in agent:</p>
              <div className="space-y-2">
                {installedAgents.map((agent) => (
                  <a
                    key={agent.id}
                    href={getAgentUrlScheme(agent.id)!}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block border border-gray-700 rounded-lg bg-gray-800 hover:bg-gray-700 p-3 text-left transition-colors"
                  >
                    <div className="text-white text-sm font-medium">
                      {agent.name}
                    </div>
                    <div className="text-gray-400 text-xs">Open agent</div>
                  </a>
                ))}
                {installedAgents.length === 0 && (
                  <p className="text-gray-500 text-xs">
                    No supported agents installed
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
        <div className="flex justify-end mt-6">
          <Button
            variant="outline"
            size="sm"
            onClick={onClose}
            className="border-gray-700 bg-gray-900 hover:bg-gray-800 text-gray-300"
          >
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
