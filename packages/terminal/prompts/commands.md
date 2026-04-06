## CLI COMMANDS

Connection management:
  db-mcp list                          — list connections
  db-mcp status                        — show active connection + config
  db-mcp use <name>                    — switch connection
  db-mcp doctor                        — preflight checks for a connection
  db-mcp edit                          — edit connection credentials

Schema & discovery:
  db-mcp schema show                   — table/column descriptions from vault
  db-mcp schema show | grep -A20 '<table>' — columns for one table
  db-mcp schema tables                 — list tables in database
  db-mcp schema sample <table>         — sample rows
  db-mcp discover                      — introspect database schema
  db-mcp domain show                   — view semantic domain model

Querying:
  db-mcp query run --confirmed '<SQL>' — execute SQL
  db-mcp query validate '<SQL>'        — validate SQL without executing

Knowledge vault:
  db-mcp rules list                    — list business rules
  db-mcp rules add '<rule>'            — add a business rule
  db-mcp examples list                 — list query examples
  db-mcp examples search --grep '<keyword>' — search examples by intent/SQL
  db-mcp examples add                  — add a query example
  db-mcp gaps list                     — list knowledge gaps
  db-mcp gaps dismiss '<term>'         — dismiss a gap
  db-mcp metrics list                  — list business metrics
  db-mcp metrics add                   — add a metric
  db-mcp metrics discover              — discover metric candidates

Collaboration:
  db-mcp sync                          — sync vault with git
  db-mcp pull                          — pull vault from git
  db-mcp git-init                      — enable git sync
