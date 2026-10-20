#!/bin/sh
set -eu
# Railway mounts the volume when the container starts; this is not a build-time step.
mkdir -p /app/instance
chown -R tunely:tunely /app/instance
: "${TUNELY_FERNET_KEY:?Set TUNELY_FERNET_KEY in Railway Variables}"
: "${TUNELY_SIGNUP_CODE:?Set TUNELY_SIGNUP_CODE in Railway Variables}"
case "${PORT:-8765}" in
  *[!0-9]*|'') echo 'PORT must be numeric' >&2; exit 2;;
esac
exec gosu tunely uvicorn server:app --host 0.0.0.0 --port "${PORT:-8765}" --workers 1 --no-access-log
