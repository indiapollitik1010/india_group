"""Environment-driven configuration for the Pollitik Manager service.

No secrets are hard-coded here. Everything sensitive comes from process
environment variables (see .env.example for the full list of names —
never real values).
"""

import os
from pathlib import Path

# The repository root - service/ is one level below it.
PROJECT_DIR = Path(__file__).resolve().parent.parent

# Where the Claude Agent SDK session should treat as `cwd` so it discovers
# CLAUDE.md, .claude/settings.json (and therefore pollitik_guard.py),
# .claude/agents/*.md, and .claude/skills/. See docs/REMOTE_DEPLOYMENT.md
# for why this must stay pinned to the repo root.
AGENT_CWD = PROJECT_DIR

PYTHON_BIN = os.environ.get("POLLITIK_PYTHON_BIN", "python3")

# --- MVP job storage -----------------------------------------------------
# Simple JSON-file-per-job store. See job_store.py for the documented
# restart-recovery behavior. Replace with PostgreSQL/Redis for multi-worker
# deployment (see docs/REMOTE_DEPLOYMENT.md).
JOB_STORE_DIR = Path(
    os.environ.get("POLLITIK_JOB_STORE_DIR", str(PROJECT_DIR / "service_data" / "jobs"))
)

# --- MVP API authentication -----------------------------------------------
# A single shared bearer token. This is explicitly MVP-grade (see
# security.py and docs/REMOTE_DEPLOYMENT.md) and should be replaced with a
# proper identity provider before wider deployment.
API_TOKEN = os.environ.get("POLLITIK_API_TOKEN")

# --- Claude Agent SDK ------------------------------------------------------
# The SDK itself reads ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN directly
# from the process environment (see claude_agent_sdk._internal.session_resume,
# and docs/REMOTE_DEPLOYMENT.md for the citation). This service never reads
# or forwards the key value itself - it only checks presence at startup.
ANTHROPIC_AUTH_ENV_VARS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")


def has_anthropic_auth() -> bool:
    return any(os.environ.get(var) for var in ANTHROPIC_AUTH_ENV_VARS)


MAX_TURNS = int(os.environ.get("POLLITIK_MAX_TURNS", "40"))

# --- Directories/files whose existence startup health checks verify ------
REQUIRED_PATHS = {
    "skill": PROJECT_DIR / ".claude" / "skills" / "pollitik-executive-support" / "SKILL.md",
    "hook": PROJECT_DIR / ".claude" / "hooks" / "pollitik_guard.py",
    "settings": PROJECT_DIR / ".claude" / "settings.json",
    "allowed_domains": PROJECT_DIR / "config" / "allowed_domains.txt",
    "verify_source": PROJECT_DIR / "python" / "verify_source.py",
    "validate_record": PROJECT_DIR / "python" / "validate_record.py",
    "stage_changes": PROJECT_DIR / "python" / "stage_changes.py",
    "apply_changes": PROJECT_DIR / "python" / "apply_changes.py",
    "inspect_workbook": PROJECT_DIR / "python" / "inspect_workbook.py",
}

REQUIRED_AGENTS = (
    "researcher",
    "multilingual-extractor",
    "reference-analyst",
    "matcher",
    "validator",
    "excel-writer",
    "r-analyst",
)

AGENTS_DIR = PROJECT_DIR / ".claude" / "agents"

# Not required at startup (Skill section 30 / this project's own rule: never
# fabricate a workbook). A production job that needs it will fail clearly
# instead, via apply_changes.py's own existing check.
MASTER_WORKBOOK = PROJECT_DIR / "data" / "master" / "pollitik_master.xlsx"

STAGING_FILE = PROJECT_DIR / "data" / "staging" / "candidates.jsonl"
