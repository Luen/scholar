#!/bin/sh
set -e
# Fix volume permissions (Docker volumes are root-owned by default; Ulixee needs to write here)
chown -R ulixee:ulixee /tmp/.ulixee /home/ulixee/.cache/ulixee 2>/dev/null || true
# Run as ulixee; gosu/setuid may be restricted in containers, so run as root after chown.
# Root can write to the chowned dirs; Ulixee prefers non-root but works as root.
exec "$@"
