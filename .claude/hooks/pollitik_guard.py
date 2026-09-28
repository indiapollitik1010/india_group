#!/usr/bin/env python3
"""Pollitik Database PreToolUse enforcement hook.

Deterministic backstop for the pollitik-executive-support Skill
(.claude/skills/pollitik-executive-support/SKILL.md). Instructions in the
Skill are advisory; this hook is what actually blocks tool calls.

Reads a single PreToolUse event as JSON on stdin and, when a rule is
violated, prints a `hookSpecificOutput.permissionDecision: "deny"`
response and exits 0. When nothing is violated it stays silent and
exits 0, deferring to the normal Claude Code permission flow — it never
force-allows a call.

Enforced rules (see the accompanying task/skill for full rationale):

  1. No direct Write/Edit, and no Bash-driven write, to a production/
     master Pollitik workbook, unless routed through a script explicitly
     listed in APPROVED_WRITER_SCRIPTS below.
  2. No deletion, renaming, or other destructive shell operation against
     a production/master Pollitik workbook, ever (no writer-script
     exception).
  3. No Write/Edit, and no destructive/write-looking Bash command,
     against anything under docs/ead/ - read-only reference material
     supplied by the project owner (the EAD Data Collection Manual and
     the EAD Series/Question-Wording reference workbook). Unlike the
     production workbook, there is NO approved-writer-script exception
     here at all.
  4. No WebFetch to a host outside config/allowed_domains.txt.
  5. No shell-based networking (curl/wget/python http libs/etc.) that
     could be used to route around rule 4.
  6. Read-only inspection of production files and docs/ead/,
     staging-directory writes, and WebFetch to approved domains are left
     alone.

HEURISTIC LIMITATIONS: this hook detects production-workbook paths and
destructive/networking shell commands using pattern matching over the
tool_input it is given (see PRODUCTION_INDICATOR_RE, EXCEL_EXT_RE,
DESTRUCTIVE_BASH_RE, WRITE_BASH_RE, NETWORK_TOOL_RE). It cannot see
inside shell variables, encoded commands, or scripts it did not read.
As the real Pollitik workbook filename(s) and directory layout become
known, tighten these patterns rather than relying on the generic
placeholders below.
"""

import json
import os
import re
import sys
import urllib.parse


def project_dir():
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def read_allowed_domains():
    path = os.path.join(project_dir(), "config", "allowed_domains.txt")
    domains = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                domains.append(line.lower())
    except OSError:
        pass
    return domains


def host_allowed(host, allowed_domains):
    host = (host or "").lower().rstrip(".")
    for domain in allowed_domains:
        domain = domain.lower().rstrip(".")
        if not domain:
            continue
        if host == domain or host.endswith("." + domain):
            return True
    return False


# --- Production-workbook detection -----------------------------------
#
# Placeholder heuristic: matches paths that look like a Pollitik
# production/master Excel workbook and are NOT under a "staging"
# directory. Tighten once the real workbook path is known.

EXCEL_EXT_RE = re.compile(r"\.(xlsx|xlsm|xls)$", re.IGNORECASE)
PRODUCTION_INDICATOR_RE = re.compile(r"(pollitik|master|production)", re.IGNORECASE)
STAGING_PATH_RE = re.compile(r"(^|[/\\])staging([/\\]|$|[_-])", re.IGNORECASE)
POLLITIK_TOKEN_RE = re.compile(r"pollitik", re.IGNORECASE)

# Scripts explicitly approved to perform validated production writes.
# python/apply_changes.py is the reviewed writer for this project (see
# that file's docstring): it re-validates every record itself, backs up
# the workbook first, only maps onto columns that already exist, and
# verifies the write afterward. Anything not listed here fails closed
# (Skill section 35, "Write policy", and section 42, "Core academic
# rule") - if you add another writer script, review it as carefully as
# that one before adding it.
APPROVED_WRITER_SCRIPTS = [
    "python/apply_changes.py",
]

DESTRUCTIVE_BASH_RE = re.compile(r"\b(rm|shred|unlink|mv|rename)\b", re.IGNORECASE)

WRITE_BASH_RE = re.compile(
    r"(>>?[^=]|\btruncate\b|\bdd\b|\bsed\s+-i\b|\.to_excel\(|\bopenpyxl\b"
    r"|\bwb\.save\(|\bworkbook\.save\(|\bsave_workbook\()",
    re.IGNORECASE,
)

# A script invocation can write to the workbook internally without any
# write-pattern substring appearing in the Bash command line itself
# (e.g. `python3 python/apply_changes.py --workbook ...`). Treat any
# script whose filename looks like a writer as equivalent to a detected
# write, so it still has to be in APPROVED_WRITER_SCRIPTS.
WRITER_SCRIPT_NAME_RE = re.compile(
    r"[\w./\\-]*(write|apply_changes|excel_writer|writer)[\w./\\-]*\.py\b",
    re.IGNORECASE,
)

# --- Read-only reference material (docs/ead/) --------------------------
#
# The EAD Data Collection Manual and the EAD Series/Question-Wording
# reference workbook are project-owner-supplied reference material that
# must never be modified - no approved-writer-script exception exists
# for this directory at all, unlike the production workbook above.

READONLY_REFERENCE_DIR_RE = re.compile(r"(^|[/\\])docs[/\\]ead([/\\]|$)", re.IGNORECASE)


def is_readonly_reference_path(path):
    if not path:
        return False
    norm = path.replace("\\", "/")
    return bool(READONLY_REFERENCE_DIR_RE.search(norm))


def command_mentions_readonly_reference_path(command):
    for token in re.split(r"[\s'\"]+", command):
        if is_readonly_reference_path(token):
            return True
    return False


# A stderr/stdout redirect to /dev/null (e.g. `2>/dev/null` in an
# otherwise read-only diagnostic command) is extremely common and writes
# nowhere of concern. WRITE_BASH_RE's generic `>` pattern would otherwise
# flag it as a write on any command that merely mentions a docs/ead path
# elsewhere in the same line - exclude it before checking for a write
# pattern in the docs/ead rule specifically.
_DEVNULL_REDIRECT_RE = re.compile(r">>?\s*/dev/null")


def _looks_like_write_bash(command):
    stripped = _DEVNULL_REDIRECT_RE.sub("", command)
    return bool(WRITE_BASH_RE.search(stripped) or WRITER_SCRIPT_NAME_RE.search(command))


NETWORK_TOOL_RE = re.compile(
    r"\b(curl|wget|httpie|ncat|telnet)\b"
    r"|\bnc\s+-"
    r"|\bhttp\s+(get|post|put|delete|patch)\b"
    r"|Invoke-WebRequest|Invoke-RestMethod"
    r"|\b(requests|urllib|urllib2|httpx|aiohttp)\b"
    r"|\bhttp\.client\b"
    r"|\bfetch\s*\("
    r"|\baxios\b",
    re.IGNORECASE,
)


def is_production_workbook_path(path):
    if not path:
        return False
    norm = path.replace("\\", "/")
    if not EXCEL_EXT_RE.search(norm):
        return False
    if STAGING_PATH_RE.search(norm):
        return False
    return bool(PRODUCTION_INDICATOR_RE.search(norm))


def command_mentions_production_workbook(command):
    for token in re.split(r"[\s'\"]+", command):
        if is_production_workbook_path(token):
            return True
    return False


def command_mentions_pollitik_path(command):
    """Broader signal for destructive ops: any path-like token containing
    'pollitik', regardless of extension (covers `rm -rf` on a whole
    production directory, not just a single workbook file)."""
    for token in re.split(r"[\s'\"]+", command):
        norm = token.replace("\\", "/")
        if STAGING_PATH_RE.search(norm):
            continue
        if POLLITIK_TOKEN_RE.search(norm):
            return True
    return False


def command_invokes_approved_writer(command):
    for script in APPROVED_WRITER_SCRIPTS:
        if script and script in command:
            return True
    return False


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def allow_silent():
    sys.exit(0)


def check_bash(tool_input):
    command = tool_input.get("command", "") or ""

    if NETWORK_TOOL_RE.search(command):
        deny(
            "pollitik_guard: shell-based networking (curl/wget/an HTTP "
            "client library/etc.) is blocked. It can bypass the WebFetch "
            "domain allow-list required by the pollitik-executive-support "
            "Skill. Use the WebFetch tool against a domain approved in "
            "config/allowed_domains.txt instead."
        )

    destructive = DESTRUCTIVE_BASH_RE.search(command)

    if command_mentions_readonly_reference_path(command):
        looks_like_write_or_destroy = destructive or _looks_like_write_bash(command)
        if looks_like_write_or_destroy:
            deny(
                "pollitik_guard: this command appears to modify, delete, "
                "or write to a path under docs/ead/ - read-only reference "
                "material (the EAD manual / EAD Series-Question-Wording "
                "reference workbook). This is never permitted, and there "
                "is no approved-writer-script exception for this "
                "directory, unlike the production workbook."
            )

    if destructive and command_mentions_pollitik_path(command):
        deny(
            "pollitik_guard: this command looks like a destructive "
            "operation (rm/mv/shred/unlink/rename) touching a Pollitik "
            "production path. Deletion, renaming, or other destructive "
            "modification of the master Pollitik workbook/data is never "
            "permitted, regardless of any approved writer script."
        )

    if command_mentions_production_workbook(command):
        if destructive:
            deny(
                "pollitik_guard: this command looks like a destructive "
                "operation (rm/mv/shred/unlink/rename) on a production "
                "Pollitik workbook. Destructive modification of the "
                "master workbook is never permitted."
            )
        looks_like_write = WRITE_BASH_RE.search(command) or WRITER_SCRIPT_NAME_RE.search(command)
        if looks_like_write and not command_invokes_approved_writer(command):
            deny(
                "pollitik_guard: this command appears to write to a "
                "production Pollitik workbook directly from Bash, but "
                "does not invoke a script listed in APPROVED_WRITER_SCRIPTS "
                "(.claude/hooks/pollitik_guard.py). Use python/apply_changes.py "
                "to write validated, staged records to production instead."
            )

    allow_silent()


def check_write_or_edit(tool_input):
    file_path = tool_input.get("file_path", "") or ""
    if is_readonly_reference_path(file_path):
        deny(
            "pollitik_guard: '{}' is under docs/ead/, read-only reference "
            "material supplied by the project owner (EAD manual / EAD "
            "Series-Question-Wording reference workbook). It must never "
            "be modified - there is no approved-writer exception for "
            "this directory, unlike the production workbook.".format(file_path)
        )
    if is_production_workbook_path(file_path):
        deny(
            "pollitik_guard: direct Write/Edit of a production Pollitik "
            "workbook ('{}') is blocked. Research agents must not write "
            "production data directly; stage the candidate observation "
            "and route validated writes through an approved writer "
            "script instead (Skill sections 30-35).".format(file_path)
        )
    allow_silent()


def check_webfetch(tool_input):
    url = tool_input.get("url", "") or ""
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        deny("pollitik_guard: could not parse WebFetch URL '{}'.".format(url))
        return

    host = parsed.hostname
    if not host:
        deny("pollitik_guard: WebFetch URL '{}' has no resolvable host.".format(url))
        return

    allowed_domains = read_allowed_domains()
    if not allowed_domains:
        deny(
            "pollitik_guard: config/allowed_domains.txt has no approved "
            "domains yet, so NOT_FOUND_ON_APPROVED_SOURCES applies to "
            "every WebFetch request. Ask the project owner to approve "
            "specific source domains before fetching '{}'.".format(host)
        )
        return

    if not host_allowed(host, allowed_domains):
        deny(
            "pollitik_guard: '{}' is not listed in "
            "config/allowed_domains.txt. Per the "
            "pollitik-executive-support Skill, WebFetch is restricted to "
            "explicitly approved domains. Do not retry with a shortener, "
            "mirror, proxy, or cached copy to work around this."
            .format(host)
        )
        return

    allow_silent()


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        # Malformed input: nothing safe to enforce against, so defer to
        # the normal permission flow rather than crash the hook.
        allow_silent()
        return

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    if tool_name == "Bash":
        check_bash(tool_input)
    elif tool_name in ("Write", "Edit", "NotebookEdit"):
        check_write_or_edit(tool_input)
    elif tool_name == "WebFetch":
        check_webfetch(tool_input)
    else:
        allow_silent()


if __name__ == "__main__":
    main()
