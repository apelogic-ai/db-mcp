# db-mcp Skills

Skills that ship with db-mcp for agent-assisted data querying.

## Available skills

| Skill | What it does |
|---|---|
| `query` | Query any db-mcp connection — auto-resolves connections, validates SQL, retry budget |
| `connections` | Generate connection topology map to eliminate blind exploration |

## Installation

Skills are installed via `db-mcp skills install`, which detects available
agents on the system and prompts the user to choose which ones to
configure.

Skills are stored here (source of truth) and copied to each agent's
native skill location in the appropriate format.

## Agent formats

| Agent | Skill location | Format |
|---|---|---|
| Claude Code | `~/.claude/skills/{name}/SKILL.md` | Markdown + YAML frontmatter |
| Codex | `~/.codex/skills/{name}/SKILL.md` | Markdown + YAML frontmatter |
| Cursor | `.cursor/rules/{name}.md` | Markdown (no frontmatter) |
| AGENTS.md | `~/.codex/AGENTS.md` or project `AGENTS.md` | Appended section |

The source skills are in Claude Code SKILL.md format. The installer
transforms them for each target agent.
