#!/usr/bin/env bash
set -o errexit  # exit on error
set -o pipefail # exit on error in pipes
set -o nounset  # error on unset variables

echo "🔍 Checking Django and database status..."
python -c "
import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'blog_recommend.settings')

try:
    django.setup()
    print('✅ Django setup successful')
    
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute('SELECT version()')
        db_version = cursor.fetchone()
        print(f'✅ Database connection successful: {db_version[0] if db_version else \"Unknown\"}')
        
except Exception as e:
    print(f'❌ Django setup failed: {e}')
    sys.exit(1)
"

echo "📋 Checking current migration state..."
python manage.py showmigrations 2>/dev/null || echo "⚠️ Could not show migrations, continuing..."

echo "🚀 Attempting to create migrations..."
if python manage.py makemigrations --noinput --dry-run 2>/dev/null; then
    echo "📦 Creating migrations..."
    python manage.py makemigrations --noinput || echo "⚠️ Migration creation had issues"
else
    echo "✅ No new migrations needed"
fi

echo "🔄 Applying migrations..."
python manage.py migrate --noinput || {
    echo "⚠️ Standard migration failed, trying --fake-initial..."
    python manage.py migrate --fake-initial --noinput || echo "⚠️ Fake initial also failed"
}

echo "🔍 Final database check..."
python -c "
import django
django.setup()
from django.db import connection

tables = connection.introspection.table_names()
print(f'📊 Found {len(tables)} tables in database')

# Check for essential tables
essential_tables = ['django_migrations', 'auth_user', 'blog_post', 'blog_recommendationlog']
for table in essential_tables:
    if table in tables:
        print(f'✅ {table} exists')
    else:
        print(f'❌ {table} missing')
"

echo "📥 Importing blogs from CSV (will skip if already loaded)..."
python manage.py import_blogs_from_csv_testing || {
    echo "⚠️ Blog import failed or skipped"
    # Continue anyway
}

echo "🌐 Starting Gunicorn..."
exec gunicorn blog_recommend.wsgi:application --bind 0.0.0.0:$PORT --workers 4 --threads 2 --timeout 120