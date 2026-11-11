#!/bin/sh
set -e

need() { [ -s "$1" ] || { echo "[ERROR] falta $1" >&2; exit 1; }; }
need /secrets/app/django_secret_key
need /secrets/app/django_admin_password

if [ -f /secrets/s3/garage_s3.env ]; then
    set -a
    . /secrets/s3/garage_s3.env
    set +a
fi

if [ -z "${DJANGO_SECRET_KEY:-}" ]; then
    export DJANGO_SECRET_KEY="$(cat /secrets/app/django_secret_key)"
fi
export DJANGO_SUPERUSER_PASSWORD="$(cat /secrets/app/django_admin_password)"

python manage.py migrate --noinput
python manage.py ensure_superuser
[ "$SEED_DEMO" = "true" ] && python manage.py seed_demo

exec "$@"