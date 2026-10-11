"""Docker HEALTHCHECK: exit 0 while the worker's heartbeat file is fresh, 1 otherwise.

The worker touches the file every 5 seconds for as long as its event loop is running, so a
stale file means the process is hung (the container is still "up", but not working).
Uses only the standard library so it starts instantly.
"""

import os
import sys
import time

HEALTH_FILE = os.environ.get("HEALTH_FILE", "/tmp/first-user-worker.heartbeat")
MAX_AGE_SECONDS = int(os.environ.get("HEALTHCHECK_MAX_AGE_SECONDS", "120"))

try:
    age = time.time() - os.path.getmtime(HEALTH_FILE)
except OSError:
    print(f"unhealthy: no heartbeat file at {HEALTH_FILE}")
    sys.exit(1)
if age > MAX_AGE_SECONDS:
    print(f"unhealthy: last heartbeat {int(age)} s ago")
    sys.exit(1)
print(f"healthy: last heartbeat {int(age)} s ago")
