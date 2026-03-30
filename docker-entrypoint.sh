#!/bin/sh
set -eu

is_truthy() {
  case "${1:-}" in
    1|true|TRUE|True|yes|YES|on|ON)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

if is_truthy "${LOAD_FIXTURE:-False}"; then
  FIXTURE_PATH="${FIXTURE_PATH:-data/bonaso_fixture.json}"
  if [ -f "${FIXTURE_PATH}" ]; then
    echo "Loading fixture ${FIXTURE_PATH}..."
    python manage.py loaddata "${FIXTURE_PATH}"
  else
    echo "Fixture not found: ${FIXTURE_PATH}"
  fi
fi

if [ -n "${ADMIN_USERNAME:-}" ] && [ -n "${ADMIN_PASSWORD:-}" ]; then
  echo "Ensuring admin user..."
  python manage.py shell -c "import os; from django.contrib.auth import get_user_model; U=get_user_model(); username=os.environ['ADMIN_USERNAME']; password=os.environ['ADMIN_PASSWORD']; email=os.environ.get('ADMIN_EMAIL', 'admin@example.com'); u, created = U.objects.get_or_create(username=username, defaults={'email': email}); u.set_password(password); u.is_staff=True; u.is_superuser=True; u.is_active=True; u.email=email; u.save(); print('Admin user ready:', u.username, 'created' if created else 'updated')"
fi

if is_truthy "${ACTIVATE_ALL_USERS:-False}"; then
  echo "Activating all users..."
  python manage.py shell -c "from django.contrib.auth import get_user_model; U=get_user_model(); updated = U.objects.filter(is_active=False).update(is_active=True); print('Activated users:', updated)"
fi

if is_truthy "${GRANT_ADMIN_ROLE_SUPERUSER:-False}"; then
  echo "Granting admin role users staff/superuser..."
  python manage.py shell -c "from django.contrib.auth import get_user_model; U=get_user_model(); updated = U.objects.filter(role='admin').update(is_staff=True, is_superuser=True, is_active=True); print('Updated admin role users:', updated)"
fi

if [ "$#" -eq 0 ]; then
  set -- gunicorn core.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers ${GUNICORN_WORKERS:-3} \
    --timeout ${GUNICORN_TIMEOUT:-120}
fi

exec "$@"
