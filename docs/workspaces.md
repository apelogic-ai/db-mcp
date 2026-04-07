# Workspaces & Hierarchy

Design document for multi-workspace support in db-mcp.

**Status**: Proposal
**Author**: Leonid Belyaev + Claude
**Date**: 2026-04-07

---

## Problem

Today every connection is a silo. Business rules, query examples, metrics, and domain models are scoped to a single connection. When a team has multiple data sources that share the same domain (e.g., a marketing team with Postgres, Snowflake, and Google Ads API), knowledge must be duplicated across connections.

There is also no concept of user-wide or organization-wide defaults. A convention like "revenue always means net revenue" must be manually added to every connection.

## Goals

1. **Share knowledge across connections** — rules, examples, metrics, domain models
2. **Hierarchical inheritance** — global → workspace → connection, with additive merge
3. **Team collaboration unit** — one git repo per workspace, not per connection
4. **Backward compatible** — existing flat connections continue to work unchanged
5. **Simple CLI/TUI UX** — workspaces are optional, not required

## Non-goals (for now)

- RBAC or access control (enterprise feature)
- Cross-workspace joins or federated queries (data gateway concern)
- Remote workspace registry or hosted workspaces
- Multi-user conflict resolution (git handles this)

---

## Directory structure

```
~/.db-mcp/
  config.yaml                          # active workspace, active connection, user prefs
  global/                              # user-wide defaults (or org-wide via git)
    rules/
      business_rules.yaml
    metrics/
      catalog.yaml
    instructions/
      sql_rules.md
  workspaces/
    marketing/
      workspace.yaml                   # name, description, git remote, member list
      rules/
        business_rules.yaml            # shared across all connections in workspace
      examples/                        # shared query patterns
      metrics/
        catalog.yaml                   # shared metric definitions (DAU, revenue, etc.)
      domain/
        model.yaml                     # shared domain model
      instructions/
        sql_rules.md                   # workspace-specific SQL conventions
      connections/
        analytics-db/
          .env                         # credentials (gitignored)
          schema/
            descriptions.yaml          # connection-specific schema
          rules/
            business_rules.yaml        # connection-specific overrides
          examples/
          training/
        google-ads/
          .env
          connector.yaml               # API connector config
          schema/
    engineering/
      workspace.yaml
      connections/
        production/
        staging/
  connections/                         # legacy flat connections (backward compat)
    playground/
    nova/
```

## Knowledge inheritance

When the agent queries rules, examples, or metrics for a connection, it sees the **union** of three layers:

```
global/rules/ + workspace/rules/ + connection/rules/ → merged rules
```

### Merge strategy

- **Rules**: additive. All rules from all layers apply. Connection rules can override a workspace rule by using the same rule ID.
- **Examples**: additive. All examples are available. Connection examples rank higher in search results.
- **Metrics**: additive with override. A connection can redefine a metric (e.g., "DAU" means something different for this specific database).
- **Domain model**: connection-specific. The domain model describes one database's schema, not a shared concept.
- **Schema**: connection-specific only. Each database has its own schema.
- **SQL rules/instructions**: concatenated. Global instructions + workspace instructions + connection instructions.

### Resolution order

```python
def resolve_rules(connection_path, workspace_path=None, global_path=None):
    rules = {}
    for path in [global_path, workspace_path, connection_path]:
        if path and (path / "rules" / "business_rules.yaml").exists():
            layer = load_yaml(path / "rules" / "business_rules.yaml")
            for rule in layer:
                rules[rule["id"]] = rule  # later layers override by ID
    return list(rules.values())
```

## Git sync

### Current model (per-connection)
```
git remote → ~/.db-mcp/connections/nova/
```

### Workspace model (per-workspace)
```
git remote → ~/.db-mcp/workspaces/marketing/
```

The git repo contains the workspace config, shared knowledge, and all connection directories. Credentials (`.env` files) are gitignored. Team members clone the workspace and add their own `.env` files.

This is cleaner for collaboration:
- One repo to clone, not N
- Shared rules are version-controlled in one place
- New team members get all the knowledge immediately

### Global sync

The `global/` directory can also be git-synced for org-wide standards:
```
git remote → ~/.db-mcp/global/
```

## CLI UX

### Workspace commands

```bash
# List workspaces
db-mcp workspace list

# Create a workspace
db-mcp workspace create marketing

# Switch active workspace
db-mcp workspace use marketing

# Show active workspace
db-mcp workspace status

# Sync workspace with git
db-mcp workspace sync

# Clone a shared workspace
db-mcp workspace clone git@github.com:acme/marketing-data.git
```

### Connection commands (workspace-aware)

```bash
# Within active workspace
db-mcp init analytics-db              # creates in active workspace
db-mcp use analytics-db               # switches connection within workspace
db-mcp list                           # lists connections in active workspace

# Explicit workspace
db-mcp use marketing/analytics-db     # switches workspace + connection
db-mcp list --all                     # lists all connections across all workspaces

# Legacy (no workspace)
db-mcp use playground                 # flat connections still work
```

### TUI changes

- Status bar: `marketing / analytics-db` (workspace / connection)
- `/workspace` slash command: list, switch, create
- `/init` flow: "Add to workspace 'marketing' or create standalone?"
- Autocomplete: `/use` shows connections grouped by workspace

## Config file

```yaml
# ~/.db-mcp/config.yaml
active_workspace: marketing
active_connection: analytics-db

# Legacy fallback — used when no workspace is active
# active_connection: nova

workspaces:
  marketing:
    git_remote: git@github.com:acme/marketing-data.git
  engineering:
    git_remote: git@github.com:acme/eng-data.git

global:
  git_remote: git@github.com:acme/db-mcp-global.git
```

## Migration path

### Phase 1: Directory structure only
- Add `workspaces/` and `global/` directories
- Existing `connections/` continues to work as "default workspace"
- No code changes to knowledge resolution — just directory layout

### Phase 2: Workspace-aware resolution
- `resolve_connection()` checks active workspace first, then flat connections
- Knowledge merge logic: global + workspace + connection
- `db-mcp workspace` CLI commands

### Phase 3: Git sync for workspaces
- `db-mcp workspace clone` / `db-mcp workspace sync`
- `.env` files excluded from sync (gitignored)
- Conflict resolution via standard git merge

### Phase 4: TUI integration
- Workspace-aware status bar, autocomplete, `/workspace` command
- `/init` asks about workspace membership

## Open questions

1. **Default workspace**: Should ungrouped connections automatically belong to a "default" workspace, or remain outside the workspace system?
2. **Cross-workspace rules**: Should there be a way to explicitly import rules from another workspace?
3. **Workspace templates**: Should we support workspace templates (e.g., "marketing-starter" with pre-built rules)?
4. **Connection sharing**: Can one connection belong to multiple workspaces, or is it always one-to-one?
5. **Workspace discovery**: How does a new team member discover available workspaces? Git URL list in org config?
