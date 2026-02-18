# Superset + Trino + Chinook Example

This example demonstrates how to set up Apache Superset with Trino as a query engine, querying the Chinook sample database via PostgreSQL. It's designed for testing db-mcp integrations with Superset.

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    Superset     │    │      Trino      │    │   PostgreSQL    │
│   (port 8088)   │────│   (port 8085)   │────│ Chinook Database│
│                 │    │                 │    │   (port 5433)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │
         │
         │
┌─────────────────┐
│   PostgreSQL    │
│ Metadata Store  │
│   (port 5434)   │
└─────────────────┘
```

## Services

- **chinook-db** (PostgreSQL 16): Contains the Chinook sample database with music store data
- **superset-db** (PostgreSQL 16): Superset's metadata store
- **trino**: Query engine that connects to the Chinook database
- **superset**: BI platform that uses Trino as its query engine

## Prerequisites

- Docker and Docker Compose
- At least 4GB of available RAM
- Ports 5433, 5434, 8085, and 8088 available

## Quick Start

1. **Clone and setup:**
   ```bash
   cd ~/dev/db-mcp/examples/superset-trino
   bash scripts/setup.sh
   ```

2. **Wait for initialization** (first run takes ~3-5 minutes)

3. **Test the setup:**
   ```bash
   bash scripts/test-api.sh
   ```

4. **Access the services:**
   - Superset: http://localhost:8088 (admin/admin)
   - Trino Web UI: http://localhost:8085
   - Direct DB access: localhost:5433 (chinook/chinook123)

## Manual Setup

If you prefer to set up step by step:

```bash
# Copy environment variables
cp .env.example .env

# Edit .env if needed (defaults work for development)
# vim .env

# Start all services
docker compose up -d

# Check service health
docker compose ps

# View logs if needed
docker compose logs -f superset
```

## Using with db-mcp

Once the stack is running, you can test db-mcp integration:

### Direct PostgreSQL Connection
```bash
# Connect to Chinook database directly
PGHOST=localhost PGPORT=5433 PGUSER=chinook PGPASSWORD=chinook123 PGDATABASE=chinook
```

### Trino Connection
```bash
# Connect via Trino
trino --server localhost:8085 --catalog chinook --schema public
```

### Superset API
```bash
# Get access token
curl -X POST http://localhost:8088/api/v1/security/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin","provider":"db"}'

# List databases
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8088/api/v1/database/
```

## Sample Queries

Try these queries in Superset's SQL Lab:

```sql
-- Count of artists
SELECT COUNT(*) as total_artists FROM chinook.public.artist;

-- Top 10 customers by total spent
SELECT 
    c.firstname || ' ' || c.lastname as customer_name,
    SUM(i.total) as total_spent
FROM chinook.public.customer c
JOIN chinook.public.invoice i ON c.customerid = i.customerid
GROUP BY c.customerid, customer_name
ORDER BY total_spent DESC
LIMIT 10;

-- Albums by genre
SELECT 
    g.name as genre,
    COUNT(DISTINCT al.albumid) as album_count,
    COUNT(t.trackid) as track_count
FROM chinook.public.genre g
JOIN chinook.public.track t ON g.genreid = t.genreid
JOIN chinook.public.album al ON t.albumid = al.albumid
GROUP BY g.genreid, g.name
ORDER BY album_count DESC;
```

## Chinook Database Schema

The Chinook database contains these tables:
- `artist` - Music artists
- `album` - Albums by artists
- `track` - Individual tracks
- `genre` - Music genres
- `mediatype` - Track media types
- `playlist` / `playlisttrack` - Playlists and their tracks
- `customer` - Store customers
- `employee` - Store employees
- `invoice` / `invoiceline` - Sales transactions

## Configuration Details

### Trino Configuration
- Single-node development setup
- No authentication
- PostgreSQL connector for Chinook catalog
- 2GB max memory allocation

### Superset Configuration
- Admin user: admin/admin
- CSRF disabled for API testing
- Connected to Trino as "Chinook (Trino)" database
- SQLAlchemy URI: `trino://trino@trino:8080/chinook`

## Troubleshooting

### Services won't start
```bash
# Check Docker resources
docker system df
docker system prune

# View service logs
docker compose logs chinook-db
docker compose logs trino
docker compose logs superset
```

### Superset can't connect to Trino
```bash
# Test Trino connectivity
curl http://localhost:8085/v1/info

# Check Trino logs
docker compose logs trino

# Restart Superset
docker compose restart superset
```

### Database connection issues
```bash
# Test PostgreSQL connectivity
docker compose exec chinook-db psql -U chinook -d chinook -c "SELECT COUNT(*) FROM artist;"

# Check database logs
docker compose logs chinook-db
```

### Performance issues
- Ensure Docker has at least 4GB RAM allocated
- Close unnecessary applications
- Consider reducing JVM heap size in `trino/etc/jvm.config`

## Cleanup

```bash
# Stop all services
docker compose down

# Remove volumes (deletes data)
docker compose down -v

# Remove images
docker compose down --rmi all
```

## Port Reference

- `5433` - Chinook PostgreSQL database
- `5434` - Superset metadata PostgreSQL
- `8085` - Trino coordinator
- `8088` - Superset web interface

## Development Notes

- All passwords and keys are hardcoded for development convenience
- CSRF protection is disabled for easier API testing
- Services are configured for development, not production use
- Data persists in Docker volumes between restarts

## Testing with db-mcp

This setup is designed to work with db-mcp for testing database connectivity and query capabilities. The stack provides multiple connection methods:

1. **Direct SQL** - Connect to PostgreSQL directly
2. **Federated queries** - Use Trino for cross-database queries
3. **BI integration** - Test Superset API and dashboard features

Each component can be tested independently or as part of an integrated workflow.