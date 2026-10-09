"""Shared test fixtures.

CRITICAL ISOLATION NOTE: the env vars below are set at module import time,
before anything imports `service.*` or `python/pollitik_common`, on
purpose. `python/pollitik_common.PROJECT_DIR` (and therefore
STAGING_FILE/ALLOWED_DOMAINS_PATH/ARCHIVE_DIR/etc.) and
`service.job_store`'s storage directory are both computed once, from
these env vars, the first time those modules are imported. Setting them
here - before any test module does `from service import ...` - is what
keeps every test in this suite off the real repo's
data/staging/candidates.jsonl, config/allowed_domains.txt, and
service_data/jobs/. `service.config.PROJECT_DIR`/`AGENT_CWD` are
deliberately NOT redirected: those come from `service/config.py`'s own
file location and always point at the real repo, because several tests
(health, hook-protection) intentionally check the real Skill/hook/agents
files still exist and still work.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_SESSION_SANDBOX = Path(tempfile.mkdtemp(prefix="pollitik_test_session_"))
(_SESSION_SANDBOX / "config").mkdir(parents=True, exist_ok=True)
(_SESSION_SANDBOX / "config" / "allowed_domains.txt").write_text(
    "# test-session fixture allow-list\napproved-pollster.example\n"
)
(_SESSION_SANDBOX / "data" / "staging").mkdir(parents=True, exist_ok=True)
(_SESSION_SANDBOX / "data" / "master").mkdir(parents=True, exist_ok=True)
(_SESSION_SANDBOX / "data" / "archive").mkdir(parents=True, exist_ok=True)
(_SESSION_SANDBOX / "logs" / "writes").mkdir(parents=True, exist_ok=True)
(_SESSION_SANDBOX / "logs" / "validation").mkdir(parents=True, exist_ok=True)

os.environ["CLAUDE_PROJECT_DIR"] = str(_SESSION_SANDBOX)
os.environ["POLLITIK_JOB_STORE_DIR"] = str(_SESSION_SANDBOX / "service_data" / "jobs")
os.environ["POLLITIK_API_TOKEN"] = "test-token-do-not-use-in-prod"
# Deliberately left unset unless already present in the real environment -
# tests must never be able to reach the live Anthropic API.
os.environ.setdefault("ANTHROPIC_API_KEY", "")

import pytest  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "python"))

SESSION_SANDBOX = _SESSION_SANDBOX
TEST_API_TOKEN = os.environ["POLLITIK_API_TOKEN"]
AUTH_HEADERS = {"Authorization": f"Bearer {TEST_API_TOKEN}"}


@pytest.fixture
def sandbox(tmp_path):
    """A fresh, fully isolated CLAUDE_PROJECT_DIR-like tree, for tests
    that need their own allow-list/staging state independent of the
    shared session sandbox (e.g. domain-allowlist tests)."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "allowed_domains.txt").write_text(
        "# test fixture allow-list\napproved-pollster.example\n"
    )
    (tmp_path / "data" / "staging").mkdir(parents=True)
    (tmp_path / "data" / "master").mkdir(parents=True)
    (tmp_path / "data" / "archive").mkdir(parents=True)
    (tmp_path / "logs" / "writes").mkdir(parents=True)
    (tmp_path / "logs" / "validation").mkdir(parents=True)
    return tmp_path


def run_script(script_name: str, project_dir: Path, args=None, input_json=None, extra_env=None, raw_input=None):
    """Run one of the repo's real python/*.py pipeline scripts as a
    subprocess against an isolated CLAUDE_PROJECT_DIR, exactly the way
    service/agent.py invokes apply_changes.py in production. Returns the
    completed subprocess.CompletedProcess.

    `raw_input`, if given, is piped to stdin verbatim (e.g. hand-written
    JSONL text) instead of being JSON-encoded like `input_json` - used for
    exercising batch-mode JSONL input, which isn't a single JSON value."""
    cmd = [sys.executable, str(REPO_ROOT / "python" / script_name), *(args or [])]
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project_dir)}
    if extra_env:
        env.update(extra_env)
    if raw_input is not None:
        stdin_text = raw_input
    elif input_json is not None:
        stdin_text = json.dumps(input_json)
    else:
        stdin_text = None
    return subprocess.run(
        cmd,
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(project_dir),
    )


def run_hook(tool_name: str, tool_input: dict) -> dict:
    """Run the real .claude/hooks/pollitik_guard.py against a synthetic
    PreToolUse payload and return its parsed JSON decision (empty dict
    means "no opinion" / allow)."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
    }
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / ".claude" / "hooks" / "pollitik_guard.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    out = proc.stdout.strip()
    return json.loads(out) if out else {}
