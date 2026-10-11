# First User worker: Python 3.11, Google Chrome (headless) and the worker's pinned dependencies.
#
# Build (from the repository root):
#   docker build -t first-user-worker --build-arg AGENT_VERSION=$(git rev-parse --short HEAD) worker/
# Secrets are never part of the image: they are passed at run time with --env-file (see DEPLOY.md).

FROM python:3.11-slim-bookworm

ARG AGENT_VERSION=unknown

# HEADLESS            Chrome has no window: a server has no display.
# Chrome's own sandbox is left ON (CHROME_SANDBOX is not set here). It is what keeps a hostile
# page's renderer away from this process's environment, which holds the API keys: Chrome runs as
# the same user as the worker. Docker's default seccomp profile blocks the namespaces the sandbox
# needs, so the run command passes worker/chrome-seccomp.json (see DEPLOY.md). The worker checks
# at startup that Chrome starts, and says so clearly if it does not. Do not set CI or run as root:
# Stagehand turns the sandbox off in both cases.
# CHROME_PATH         where Stagehand's local mode looks for the browser.
# CLEAN_RUN_FILES     delete a run's local screenshots once saved; they are uploaded to storage.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    HEADLESS=true \
    CHROME_PATH=/usr/bin/google-chrome-stable \
    CLEAN_RUN_FILES=true \
    HEALTH_FILE=/tmp/first-user-worker.heartbeat \
    AGENT_VERSION=${AGENT_VERSION}

# Google Chrome from Google's apt repository. The package pulls in the shared libraries it needs;
# the fonts are so pages render text (and emoji) instead of empty boxes.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && install -d -m 0755 /etc/apt/keyrings \
 && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends google-chrome-stable fonts-liberation fonts-noto-color-emoji \
 && apt-get purge -y --auto-remove gnupg \
 && rm -rf /var/lib/apt/lists/* \
 && google-chrome-stable --version

# A non-root user for everything that runs.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin worker \
 && mkdir -p /app/runs \
 && chown -R worker:worker /app

WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY requirements.lock.txt .
RUN pip install -r requirements.lock.txt

COPY --chown=worker:worker *.py ./

USER worker

# Healthy while the worker's heartbeat file is fresh (healthcheck.py).
HEALTHCHECK --interval=60s --timeout=10s --start-period=90s --retries=3 CMD ["python", "healthcheck.py"]

# docker stop sends SIGTERM: the worker finishes the run in progress, then exits.
STOPSIGNAL SIGTERM

CMD ["python", "main.py"]
