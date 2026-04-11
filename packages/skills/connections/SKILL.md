---
name: connections
description: List, describe, and map all db-mcp database connections. Shows connection topology for routing queries to the right data source.
---

# Connection Map

Generate a connection topology map showing all configured db-mcp
connections, their types, available schemas, and what data they contain.

## What to do

1. List all connections:
```
list_connections()
```

2. For each connection, gather:
   - Type (SQL database, API, file)
   - Database URL or API base URL (redacted)
   - Available schemas/tables (top 10)
   - Whether examples exist
   - Whether business rules are configured

```
shell(command="for conn in ~/.db-mcp/connections/*/; do name=$(basename $conn); echo \"=== $name ===\"; cat $conn/connector.yaml 2>/dev/null | head -5; echo '---'; ls $conn/schema/ 2>/dev/null; echo; done")
```

3. Output a formatted connection map:

```
## Connection Map

| Connection | Type | Key Tables/Endpoints | Examples | Rules |
|---|---|---|---|---|
| playground | SQLite | Album, Artist, Track, Invoice... | 12 | 2 |
| nova | PostgreSQL | users, orders, events... | 45 | 8 |
| dune | API (SQL) | dex_solana.trades, tokens... | 3 | 0 |
| solana-mainnet | API (RPC) | getBalance, getTransaction... | 0 | 0 |
```

4. Suggest adding this map to the user's CLAUDE.md or project instructions
   so future sessions don't need to rediscover connections.

## Purpose

This skill eliminates the #1 friction point in db-mcp usage: Claude
cycling through wrong connections and schemas before finding the right
data source. Run `/connections` once, save the output, and every future
query session starts with full context.
