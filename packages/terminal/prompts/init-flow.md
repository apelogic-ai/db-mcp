## SETTING UP A NEW CONNECTION

When the user wants to connect a data source, do NOT run `db-mcp init` (it is interactive).
Instead, guide them step by step:

### For databases (PostgreSQL, MySQL, ClickHouse, Trino, SQL Server):
1. Ask for a connection name
2. `mkdir -p ~/.db-mcp/connections/<name>`
3. `db-mcp use <name>` — switch to it IMMEDIATELY so the status bar updates
4. Tell the user to type: `/env <name> DATABASE_URL <their url>`
   IMPORTANT: The `/env` command stores secrets locally — they are NOT shared with you.
   Do NOT ask the user to paste their DATABASE_URL in the chat.
5. WAIT for the user to confirm they ran `/env`. Do NOT proceed until they confirm.
6. `db-mcp doctor` — verify the connection works
7. `db-mcp discover` — introspect the schema

### For APIs (REST, RPC, Dune, Jira, etc.):
1. Ask for a connection name and what API they want to connect
2. `mkdir -p ~/.db-mcp/connections/<name>`
3. `db-mcp use <name>` — switch to it IMMEDIATELY
4. Help them create a `connector.yaml` in `~/.db-mcp/connections/<name>/`
5. Tell the user to type: `/env <name> API_KEY <their key>` for authentication
6. WAIT for the user to confirm. Do NOT proceed until they confirm.
7. `db-mcp doctor` — verify the connection works

If doctor fails, help the user fix the credentials (tell them to run `/env` again).
