import os
from datetime import timedelta

# Flask App Configuration
SECRET_KEY = os.environ.get('SUPERSET_SECRET_KEY', 'supersecretkey123456789')

# Database Configuration for Superset metadata
SQLALCHEMY_DATABASE_URI = 'postgresql://superset:superset123@superset-db:5432/superset'

# Disable CSRF for API testing
TALISMAN_ENABLED = False
WTF_CSRF_ENABLED = False

# API Configuration
ENABLE_PROXY_FIX = True

# Security Configuration for development
SECRET_KEY = SECRET_KEY
PERMANENT_SESSION_LIFETIME = timedelta(days=31)

# Cache Configuration
CACHE_CONFIG = {
    'CACHE_TYPE': 'simple',
}

# Additional configurations for development
SQLLAB_ASYNC_TIME_LIMIT_SEC = 300
SUPERSET_WEBSERVER_TIMEOUT = 300

# Feature flags
FEATURE_FLAGS = {
    'ENABLE_TEMPLATE_PROCESSING': True,
    'DASHBOARD_NATIVE_FILTERS': True,
    'DASHBOARD_CROSS_FILTERS': True,
    'DASHBOARD_RBAC': True,
    'ENABLE_EXPLORE_JSON_CSRF_PROTECTION': False,
}

# Public role configuration
PUBLIC_ROLE_LIKE = "Gamma"

# Languages
LANGUAGES = {
    'en': {'flag': 'us', 'name': 'English'},
}