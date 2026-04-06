## ANSWERING DATA QUESTIONS (SQL queries)

When the user asks a question about data, YOU write the SQL:

1. `db-mcp rules list`                          — check business rules FIRST
2. `db-mcp examples search --grep '<keyword>'`   — find similar query patterns
3. `db-mcp schema show | grep -A20 '<table>'`    — check columns for relevant tables
4. Write SQL yourself based on rules, examples, and schema.
5. `db-mcp query run --confirmed '<SQL>'`         — execute your SQL

Do NOT delegate SQL generation. YOU are the analyst.
