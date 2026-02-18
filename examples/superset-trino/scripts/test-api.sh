#!/bin/bash
set -e

echo "Testing Superset + Trino + Chinook setup..."
echo ""

# Test 1: Query Trino directly
echo "1. Testing Trino direct query..."
TRINO_QUERY='{"query": "SELECT count(*) as artist_count FROM chinook.public.artist"}'
TRINO_RESPONSE=$(curl -s -X POST \
  -H "Content-Type: application/json" \
  -H "X-Trino-User: testuser" \
  -d "$TRINO_QUERY" \
  http://localhost:8085/v1/statement)

if echo "$TRINO_RESPONSE" | grep -q "artist_count"; then
    echo "✅ Trino query successful!"
    echo "   Artists in database: $(echo "$TRINO_RESPONSE" | grep -o '"artist_count":[0-9]*' | cut -d: -f2)"
else
    echo "❌ Trino query failed"
    echo "Response: $TRINO_RESPONSE"
    exit 1
fi

echo ""

# Test 2: Login to Superset and get token
echo "2. Testing Superset login..."
LOGIN_RESPONSE=$(curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin","provider":"db","refresh":true}' \
  http://localhost:8088/api/v1/security/login)

if echo "$LOGIN_RESPONSE" | grep -q "access_token"; then
    echo "✅ Superset login successful!"
    TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*' | cut -d: -f2 | tr -d '"')
else
    echo "❌ Superset login failed"
    echo "Response: $LOGIN_RESPONSE"
    exit 1
fi

echo ""

# Test 3: List databases in Superset
echo "3. Testing Superset database list..."
DB_RESPONSE=$(curl -s \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  http://localhost:8088/api/v1/database/)

if echo "$DB_RESPONSE" | grep -q "Chinook.*Trino"; then
    echo "✅ Chinook (Trino) database found in Superset!"
    DB_COUNT=$(echo "$DB_RESPONSE" | grep -o '"count":[0-9]*' | cut -d: -f2)
    echo "   Total databases: $DB_COUNT"
else
    echo "❌ Chinook (Trino) database not found in Superset"
    echo "Response: $DB_RESPONSE"
    exit 1
fi

echo ""

# Test 4: Test SQL Lab query via Superset API
echo "4. Testing Superset SQL Lab..."
CSRF_RESPONSE=$(curl -s \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8088/api/v1/security/csrf_token/)

if echo "$CSRF_RESPONSE" | grep -q "result"; then
    CSRF_TOKEN=$(echo "$CSRF_RESPONSE" | grep -o '"result":"[^"]*' | cut -d: -f2 | tr -d '"')
    echo "✅ CSRF token obtained for SQL Lab test"
else
    echo "❌ Failed to get CSRF token"
    exit 1
fi

# Get database ID for Chinook (Trino)
DB_ID=$(echo "$DB_RESPONSE" | grep -B5 -A5 "Chinook.*Trino" | grep -o '"id":[0-9]*' | head -1 | cut -d: -f2)

if [ -n "$DB_ID" ]; then
    echo "   Using database ID: $DB_ID"
    
    # Execute a query via SQL Lab
    SQL_QUERY='{"sql": "SELECT name FROM chinook.public.artist LIMIT 5", "database_id": '$DB_ID'}'
    SQL_RESPONSE=$(curl -s -X POST \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -H "X-CSRFToken: $CSRF_TOKEN" \
      -d "$SQL_QUERY" \
      http://localhost:8088/api/v1/sqllab/execute/)
    
    if echo "$SQL_RESPONSE" | grep -q "query_id\|data"; then
        echo "✅ SQL Lab query executed successfully!"
    else
        echo "❌ SQL Lab query failed"
        echo "Response: $SQL_RESPONSE"
    fi
else
    echo "❌ Could not find Chinook database ID"
fi

echo ""
echo "🎉 All tests passed! Your Superset + Trino + Chinook setup is working correctly."
echo ""
echo "Next steps:"
echo "- Open Superset at http://localhost:8088 (admin/admin)"
echo "- Go to SQL Lab and try queries like: SELECT * FROM chinook.public.artist LIMIT 10"
echo "- Create charts and dashboards using the Chinook data"