#!/bin/bash
set -e

echo "Setting up Superset + Trino + Chinook Docker environment..."

# Check if .env exists, if not copy from example
if [ ! -f .env ]; then
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo "Please review and modify .env if needed, then run this script again."
    echo "Default values should work for local development."
fi

echo "Starting Docker services..."
docker compose down --remove-orphans
docker compose up -d --build

echo "Waiting for all services to be healthy..."
echo "This may take a few minutes on first run..."

# Wait for services to be healthy
check_service() {
    service_name=$1
    max_attempts=${2:-30}
    attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if docker compose ps $service_name | grep -q "(healthy)"; then
            echo "$service_name is healthy!"
            return 0
        fi
        echo "Waiting for $service_name... (attempt $attempt/$max_attempts)"
        sleep 10
        attempt=$((attempt + 1))
    done
    
    echo "ERROR: $service_name failed to become healthy"
    docker compose logs $service_name
    return 1
}

# Check all services
check_service chinook-db 20
check_service superset-db 20
check_service trino 30
check_service superset 60

echo ""
echo "✅ All services are healthy!"
echo ""
echo "Access URLs:"
echo "- Superset: http://localhost:8088 (admin/admin)"
echo "- Trino: http://localhost:8085"
echo "- Chinook Database: localhost:5433 (chinook/chinook123)"
echo "- Superset Metadata DB: localhost:5434 (superset/superset123)"
echo ""
echo "To test the setup, run: bash scripts/test-api.sh"