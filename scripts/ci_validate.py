#!/usr/bin/env python3
"""Structural validation used by CI (.github/workflows/ci.yml) and safe
to run locally too. Checks:

  - every tracked *.py file compiles (syntax check)
  - every *.json file parses
  - every *.yaml/*.yml file parses
  - the Skill's frontmatter is well-formed and has the required keys
  - every .claude/agents/*.md file's frontmatter is well-formed and has
    the required keys

Does not run tests (see pytest), does not touch the network, does not
require production data or ANTHROPIC_API_KEY.
"""

import glob
import json
import py_compile
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

EXCLUDE_DIR_PARTS = {".venv", ".venv_service", "venv", "__pycache__", ".git", "node_modules"}


def _excluded(path: Path) -> bool:
    return any(part in EXCLUDE_DIR_PARTS for part in path.parts)


def check_python_syntax():
    errors = []
    checked = 0
    for path in sorted(REPO_ROOT.rglob("*.py")):
        if _excluded(path):
            continue
        checked += 1
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"{path}: {exc}")
    return checked, errors


def check_json():
    errors = []
    checked = 0
    for path in sorted(REPO_ROOT.rglob("*.json")):
        if _excluded(path):
            continue
        checked += 1
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            errors.append(f"{path}: {exc}")
    return checked, errors


def check_yaml():
    import yaml

    errors = []
    checked = 0
    for pattern in ("*.yaml", "*.yml"):
        for path in sorted(REPO_ROOT.rglob(pattern)):
            if _excluded(path):
                continue
            checked += 1
            try:
                yaml.safe_load(path.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                errors.append(f"{path}: {exc}")
    return checked, errors


def _parse_frontmatter(path: Path):
    import yaml

    content = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
    if not match:
        return None
    return yaml.safe_load(match.group(1))


def check_skill_frontmatter():
    errors = []
    skill_path = REPO_ROOT / ".claude" / "skills" / "pollitik-executive-support" / "SKILL.md"
    if not skill_path.exists():
        return 0, [f"{skill_path}: missing"]

    fm = _parse_frontmatter(skill_path)
    if fm is None:
        return 1, [f"{skill_path}: missing or malformed frontmatter"]
    if fm.get("name") != "pollitik-executive-support":
        errors.append(f"{skill_path}: frontmatter 'name' must be 'pollitik-executive-support'")
    if not fm.get("description"):
        errors.append(f"{skill_path}: frontmatter missing 'description'")
    return 1, errors


def check_agent_frontmatter():
    errors = []
    checked = 0
    required_agents = {
        "researcher", "multilingual-extractor", "reference-analyst",
        "matcher", "validator", "excel-writer", "r-analyst",
    }
    found_names = set()

    for path in sorted(glob.glob(str(REPO_ROOT / ".claude" / "agents" / "*.md"))):
        path = Path(path)
        checked += 1
        fm = _parse_frontmatter(path)
        if fm is None:
            errors.append(f"{path}: missing or malformed frontmatter")
            continue
        if not fm.get("name"):
            errors.append(f"{path}: frontmatter missing 'name'")
        else:
            found_names.add(fm["name"])
        if not fm.get("description"):
            errors.append(f"{path}: frontmatter missing 'description'")
        if not fm.get("tools"):
            errors.append(f"{path}: frontmatter missing 'tools'")

    missing_agents = required_agents - found_names
    if missing_agents:
        errors.append(f".claude/agents/: missing required agent definitions: {sorted(missing_agents)}")

    return checked, errors


def main():
    checks = [
        ("Python syntax", check_python_syntax),
        ("JSON validity", check_json),
        ("YAML validity", check_yaml),
        ("Skill frontmatter", check_skill_frontmatter),
        ("Agent frontmatter", check_agent_frontmatter),
    ]

    total_errors = []
    for label, fn in checks:
        checked, errors = fn()
        status = "OK" if not errors else "FAIL"
        print(f"[{status}] {label}: {checked} file(s) checked, {len(errors)} error(s)")
        for err in errors:
            print(f"    {err}")
        total_errors.extend(errors)

    if total_errors:
        print(f"\n{len(total_errors)} validation error(s) found.")
        sys.exit(1)

    print("\nAll structural validation checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
