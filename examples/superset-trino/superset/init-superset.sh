#!/bin/bash
set -e

echo "Waiting for Superset metadata database to be ready..."
while ! pg_isready -h superset-db -p 5432 -U superset; do
    echo "Waiting for superset-db..."
    sleep 2
done

echo "Waiting for Trino to be ready..."
while ! curl -s http://trino:8080/v1/info > /dev/null; do
    echo "Waiting for trino..."
    sleep 2
done

echo "Initializing Superset database..."
superset db upgrade

echo "Creating admin user..."
superset fab create-admin \
    --username admin \
    --firstname Admin \
    --lastname Admin \
    --email admin@example.com \
    --password ${SUPERSET_ADMIN_PASSWORD:-admin}

echo "Initializing Superset..."
superset init

echo "Registering Trino database..."
# Create a Python script to register the database via Superset API
cat > /tmp/register_trino.py << 'EOF'
import requests
import json
import time
import os

# Wait for Superset to be fully initialized
print("Waiting for Superset to be ready...")
for i in range(30):
    try:
        response = requests.get('http://localhost:8088/health', timeout=5)
        if response.status_code == 200:
            break
    except:
        pass
    time.sleep(2)
    print(f"Attempt {i+1}/30...")

# Login to get CSRF token and session
session = requests.Session()
login_data = {
    'username': 'admin',
    'password': os.environ.get('SUPERSET_ADMIN_PASSWORD', 'admin'),
    'provider': 'db'
}

print("Logging in to Superset...")
login_response = session.post('http://localhost:8088/api/v1/security/login', json=login_data)
if login_response.status_code == 200:
    access_token = login_response.json()['access_token']
    session.headers.update({'Authorization': f'Bearer {access_token}'})
    print("Login successful!")
else:
    print(f"Login failed: {login_response.status_code} {login_response.text}")
    exit(1)

# Get CSRF token
csrf_response = session.get('http://localhost:8088/api/v1/security/csrf_token/')
if csrf_response.status_code == 200:
    csrf_token = csrf_response.json()['result']
    session.headers.update({'X-CSRFToken': csrf_token})
    print("CSRF token obtained!")

# Register Trino database
database_data = {
    'database_name': 'Chinook (Trino)',
    'sqlalchemy_uri': 'trino://trino@trino:8080/chinook',
    'expose_in_sqllab': True
}

print("Registering Trino database...")
db_response = session.post('http://localhost:8088/api/v1/database/', json=database_data)
if db_response.status_code == 201:
    print("Trino database registered successfully!")
elif 'already exists' in db_response.text.lower():
    print("Trino database already exists!")
else:
    print(f"Failed to register database: {db_response.status_code} {db_response.text}")
EOF

python /tmp/register_trino.py

echo "Superset initialization complete!"
echo "Superset will be available at http://localhost:8088"
echo "Login with admin/admin"