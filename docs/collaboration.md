# Team Collaboration

db-mcp's knowledge vault gets smarter with every query. Collaboration lets your whole team benefit from that accumulated knowledge — and contribute back to it.

## How it works

The vault is a directory of YAML, Markdown, and config files. It syncs through Git. Two roles control the flow:

- **Master of Knowledge** — creates and curates the canonical vault. Think open-source maintainer.
- **Collaborator** — uses the vault and contributes improvements back via branches.

The master's vault is the source of truth. Collaborators clone it, query against it, and their usage generates new examples, learnings, and refinements that flow back for review.

## Roles

### Master of Knowledge

The master owns the canonical vault. They:

- Define the schema descriptions, SQL rules, and domain model
- Push directly to the `main` branch
- Review and merge collaborator contributions
- Control what becomes shared truth

Typically this is the person who knows the database best — a data engineer, analytics lead, or DBA.

### Collaborator

Collaborators consume the vault and improve it through usage. They:

- Clone the vault via a shared Git repo
- Query their database using the same knowledge base
- Generate new examples, learnings, and traces locally
- Push contributions to `collaborator/{username}` branches automatically

Safe additions (new examples, learnings) auto-merge. Changes to shared state (schema descriptions, SQL rules) create a PR for the master to review.

## Setup: Master

### 1. Create the connection and build the vault

```bash
db-mcp init analytics
```

Walk through the interactive setup — pick your database type, enter credentials. Then use Claude to query your database. Every query builds the vault: schema descriptions, examples, learnings.

### 2. Initialize Git and push

```bash
cd ~/.db-mcp/connections/analytics
git init
git add .
git commit -m "Initial knowledge vault"
git remote add origin git@github.com:your-org/db-mcp-analytics.git
git push -u origin main
```

Your `.env` file (database credentials) is gitignored by default. The vault is safe to push.

### 3. Share the repo URL

Give your team the repo URL. They'll use it in the next section.

## Setup: Collaborator

### Option A: New connection from a shared repo

```bash
db-mcp init analytics git@github.com:your-org/db-mcp-analytics.git
```

This clones the vault, then prompts for your own database credentials. You get the full knowledge base immediately.

### Option B: Attach a repo to an existing connection

Already have a local connection? Attach the shared repo:

```bash
db-mcp collab attach git@github.com:your-org/db-mcp-analytics.git
```

This pulls the shared vault into your existing connection. Your local `.env` stays untouched.

## What syncs and what doesn't

### Automatic (additive files)

These are safe to merge without review — they only add new knowledge:

| Path | Content |
|---|---|
| `examples/*.yaml` | Query examples (NL → SQL pairs) |
| `learnings/*.md` | Error patterns and gotchas |
| `traces/` | Query trace logs |

When a collaborator generates new examples or learnings, they push to `collaborator/{username}` and auto-merge into main.

### Requires review (shared files)

These affect how the agent interprets the database for everyone:

| Path | Content |
|---|---|
| `schema/descriptions.yaml` | Table and column descriptions |
| `instructions/sql_rules.md` | SQL generation rules |
| `PROTOCOL.md` | Agent instructions |
| `domain/model.md` | Business domain docs |

Changes to shared files create a pull request for the master to review. This prevents one person's local fix from breaking everyone's queries.

## The .collab.yaml manifest

Each connection has a `.collab.yaml` that defines the collaboration role:

**Master:**

```yaml
role: "master"
repo: "git@github.com:your-org/db-mcp-analytics.git"
```

**Collaborator:**

```yaml
role: "collaborator"
repo: "git@github.com:your-org/db-mcp-analytics.git"
username: "alice"
```

This file is created automatically during `db-mcp init` or `db-mcp collab attach`.

## Sync

Collaborators sync automatically in the background. You can also sync manually:

```bash
db-mcp collab sync
```

This pulls the latest vault from the remote and pushes any local contributions.

## Detaching

To disconnect from the shared repo while keeping your local vault files:

```bash
db-mcp collab detach
```

The vault stays intact — you just stop syncing. Useful if you want to fork off or work independently.

## Merge flow summary

```
Collaborator uses Claude → generates new examples/learnings
         │
         ▼
  Push to collaborator/{username} branch
         │
         ├── Additive files (examples, learnings) → auto-merge to main
         │
         └── Shared files (schema, rules) → PR created → master reviews → merge
```

## Commands reference

| Command | Description |
|---|---|
| `db-mcp collab attach URL` | Attach a shared repo to the current connection |
| `db-mcp collab detach` | Remove repo link, keep local files |
| `db-mcp collab sync` | Manually sync with remote |
| `db-mcp init NAME URL` | Create a new connection from a shared repo |

## Tips

- **Start solo, collaborate later.** Build your vault alone first. Once it's useful, push it and invite collaborators.
- **One master per vault.** Multiple masters leads to conflicts. If you need different schema interpretations, use separate connections.
- **Credentials never sync.** Each person configures their own `.env` with their own database credentials.
- **Review shared changes carefully.** A bad schema description affects every collaborator's query quality.
