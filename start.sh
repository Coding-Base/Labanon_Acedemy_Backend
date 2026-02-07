#!/usr/bin/env bash
set -euo pipefail

FILE="${GA_SERVICE_ACCOUNT_FILE:-/app/secrets/ga-service-account.json}"
DIR="$(dirname "$FILE")"
mkdir -p "$DIR"

if [ -n "${GA_SERVICE_ACCOUNT_HEX:-}" ]; then
  echo "Writing GA service account from GA_SERVICE_ACCOUNT_HEX -> $FILE"
  python - <<'PY'
import os,binascii,sys
fp = os.environ.get('GA_SERVICE_ACCOUNT_FILE','/app/secrets/ga-service-account.json')
hexs = os.environ.get('GA_SERVICE_ACCOUNT_HEX','')
if not hexs:
    sys.exit(0)
with open(fp,'wb') as f:
    f.write(binascii.unhexlify(hexs))
PY
elif [ -n "${GA_SERVICE_ACCOUNT_JSON:-}" ]; then
  echo "Writing GA service account from GA_SERVICE_ACCOUNT_JSON -> $FILE"
  python - <<'PY'
import os,base64,sys
fp = os.environ.get('GA_SERVICE_ACCOUNT_FILE','/app/secrets/ga-service-account.json')
b64 = os.environ.get('GA_SERVICE_ACCOUNT_JSON','')
if not b64:
    sys.exit(0)
with open(fp,'wb') as f:
    f.write(base64.b64decode(b64))
PY
else
  echo "No GA_SERVICE_ACCOUNT_HEX or GA_SERVICE_ACCOUNT_JSON set; skipping GA file write"
fi

echo "Running migrations"
python manage.py migrate --noinput

echo "Starting Gunicorn"
exec gunicorn lep_backend.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${GUNICORN_WORKERS:-3}