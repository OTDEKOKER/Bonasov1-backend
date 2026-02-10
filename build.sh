#!/usr/bin/env bash
set -euo pipefail

echo "Installing Python dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "Running migrations..."
python manage.py migrate --noinput

if [[ -n "${ADMIN_USERNAME:-}" && -n "${ADMIN_PASSWORD:-}" ]]; then
  echo "Ensuring admin user..."
  python manage.py shell -c "from django.contrib.auth import get_user_model; \
U=get_user_model(); \
u,created=U.objects.get_or_create(username='${ADMIN_USERNAME}', defaults={'email':'${ADMIN_EMAIL:-admin@example.com}'}); \
u.set_password('${ADMIN_PASSWORD}'); \
u.is_staff=True; u.is_superuser=True; \
u.email='${ADMIN_EMAIL:-admin@example.com}'; \
u.save(); \
print('Admin user ready:', u.username, 'created' if created else 'updated')"
fi

echo "Collecting static files..."
python manage.py collectstatic --noinput
