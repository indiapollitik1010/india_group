"""Startup / liveness checks.

Verifies the pieces the whole pipeline depends on actually exist before
claiming the service is healthy: the Skill, the hook, the seven agent
definitions, the domain allow-list, and the deterministic python/
scripts. Deliberately does NOT require the master workbook to exist
(Skill section 30 / project rule: never fabricate one) - its absence is
reported as a warning, not a failure. A production-write job that
actually needs it will fail clearly at that point instead (see
python/apply_changes.py, which already refuses cleanly).
"""

from . import config


def run_checks() -> dict:
    path_checks = {name: path.exists() for name, path in config.REQUIRED_PATHS.items()}

    agents_found = []
    agents_missing = []
    for name in config.REQUIRED_AGENTS:
        (agents_found if (config.AGENTS_DIR / f"{name}.md").exists() else agents_missing).append(name)

    required_ok = all(path_checks.values()) and not agents_missing

    warnings = []
    if not config.MASTER_WORKBOOK.exists():
        warnings.append(
            "No master workbook at {}. Research/staging jobs still work; "
            "any job that reaches the write-authorization step will fail "
            "clearly instead of writing anywhere.".format(config.MASTER_WORKBOOK)
        )
    if not config.has_anthropic_auth():
        warnings.append(
            "Neither ANTHROPIC_API_KEY nor CLAUDE_CODE_OAUTH_TOKEN is set. "
            "Job execution will fail until one is configured."
        )
    if not config.API_TOKEN:
        warnings.append(
            "POLLITIK_API_TOKEN is not set. All mutating endpoints are "
            "currently disabled (fail closed)."
        )

    return {
        "status": "ok" if required_ok else "degraded",
        "checks": {
            **path_checks,
            "agents_found": agents_found,
            "agents_missing": agents_missing,
            "master_workbook_present": config.MASTER_WORKBOOK.exists(),
            "anthropic_auth_configured": config.has_anthropic_auth(),
            "api_token_configured": bool(config.API_TOKEN),
        },
        "warnings": warnings,
    }
