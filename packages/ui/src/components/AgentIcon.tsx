/**
 * Gray contour icons for MCP-compatible agents.
 */

interface AgentIconProps {
  agentId: string;
  className?: string;
  size?: number;
}

export function AgentIcon({ agentId, className = "", size = 20 }: AgentIconProps) {
  const color = "currentColor";
  const props = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", className: `text-gray-400 ${className}` };

  const id = agentId.toLowerCase();

  if (id.includes("claude") && id.includes("desktop")) {
    // Claude Desktop — sparkle/star shape
    return (
      <svg {...props} viewBox="0 0 24 24">
        <path d="M12 2l2.4 7.2H22l-6 4.8 2.4 7.2L12 16.4l-6.4 4.8 2.4-7.2-6-4.8h7.6L12 2z" stroke={color} strokeWidth="1.5" strokeLinejoin="round"/>
      </svg>
    );
  }

  if (id.includes("claude") && id.includes("code")) {
    // Claude Code — terminal prompt
    return (
      <svg {...props} viewBox="0 0 24 24">
        <rect x="3" y="4" width="18" height="16" rx="2" stroke={color} strokeWidth="1.5"/>
        <path d="M7 12l3-3M7 12l3 3M14 15h3" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    );
  }

  if (id.includes("cursor")) {
    // Cursor — cursor/pointer
    return (
      <svg {...props} viewBox="0 0 24 24">
        <path d="M5 3l14 8-6 2 4 8-3 1-4-8-5 4V3z" stroke={color} strokeWidth="1.5" strokeLinejoin="round"/>
      </svg>
    );
  }

  if (id.includes("zed")) {
    // Zed — lightning bolt / Z shape
    return (
      <svg {...props} viewBox="0 0 24 24">
        <path d="M7 4h10l-7 8h8l-11 8 3-8H7l0 0z" stroke={color} strokeWidth="1.5" strokeLinejoin="round"/>
      </svg>
    );
  }

  if (id.includes("codex") || id.includes("openai")) {
    // OpenAI Codex — hexagon
    return (
      <svg {...props} viewBox="0 0 24 24">
        <path d="M12 2l8 4.5v9L12 20l-8-4.5v-9L12 2z" stroke={color} strokeWidth="1.5" strokeLinejoin="round"/>
        <circle cx="12" cy="11" r="3" stroke={color} strokeWidth="1.5"/>
      </svg>
    );
  }

  if (id.includes("vscode") || id.includes("copilot")) {
    // VS Code — bracket pair
    return (
      <svg {...props} viewBox="0 0 24 24">
        <path d="M8 4l-4 4 4 4M16 4l4 4-4 4M8 16l-4-4M16 16l4-4" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    );
  }

  if (id.includes("jetbrains") || id.includes("intellij") || id.includes("webstorm") || id.includes("pycharm") || id.includes("datagrip")) {
    // JetBrains — diamond
    return (
      <svg {...props} viewBox="0 0 24 24">
        <rect x="4" y="4" width="16" height="16" rx="1" stroke={color} strokeWidth="1.5"/>
        <path d="M7 17h5" stroke={color} strokeWidth="2" strokeLinecap="round"/>
        <path d="M8 8h3v3H8z" fill={color} opacity="0.7"/>
      </svg>
    );
  }

  if (id.includes("windsurf")) {
    // Windsurf — wave
    return (
      <svg {...props} viewBox="0 0 24 24">
        <path d="M3 12c2-3 4-3 6 0s4 3 6 0 4-3 6 0" stroke={color} strokeWidth="1.5" strokeLinecap="round"/>
        <path d="M3 17c2-3 4-3 6 0s4 3 6 0 4-3 6 0" stroke={color} strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    );
  }

  // Default — generic agent/robot
  return (
    <svg {...props} viewBox="0 0 24 24">
      <rect x="5" y="8" width="14" height="12" rx="2" stroke={color} strokeWidth="1.5"/>
      <circle cx="9" cy="14" r="1.5" fill={color}/>
      <circle cx="15" cy="14" r="1.5" fill={color}/>
      <path d="M12 4v4M8 4h8" stroke={color} strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  );
}
