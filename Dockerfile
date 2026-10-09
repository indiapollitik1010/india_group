# Pollitik Manager service container.
#
# - Runs as a non-root user.
# - Installs only what requirements.txt lists.
# - claude-agent-sdk bundles its own native `claude` CLI binary inside the
#   wheel it installs (confirmed by inspecting the installed package - see
#   docs/REMOTE_DEPLOYMENT.md) - no separate Node.js/npm install is needed
#   here for that.
# - R is NOT installed here. No R/ scripts exist in this repo yet (see
#   README.md's "What's intentionally not built yet"). Once R
#   functionality is actually built, add an `apt-get install -y r-base`
#   layer (and any R package installation) here rather than shipping an
#   unused R toolchain today.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copies the whole Pollitik repository - the Skill, hooks, agent
# definitions, config, and python/ scripts all need to be present at the
# same relative paths service/config.py expects.
COPY . .

# Non-root user. Directories the pipeline writes to are created up front
# and owned by this user (docker-compose.yml mounts named volumes over
# the persistent ones - data/master, data/staging, data/archive,
# data/cache, feedback, logs, outputs - so container recreation doesn't
# lose state).
RUN useradd --create-home --uid 10001 pollitik \
    && mkdir -p data/master data/raw data/processed data/staging data/archive data/cache \
               feedback logs/research logs/validation logs/writes \
               outputs/figures outputs/reports service_data/jobs \
    && chown -R pollitik:pollitik /app

USER pollitik

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Only the application port is exposed. No other network surface.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000"]
