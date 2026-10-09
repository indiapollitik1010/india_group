#!/usr/bin/env python3
"""Read-only Python dependency check for the student workflow.

Root cause this guards against (real Codex fresh-student test): a brand
new workspace can have the repo code, AGENTS.md, the Canada snapshot,
and the preflight script - all correctly discovered - while the Python
*environment* running them has never had `pip install -r
requirements.txt` executed. `duckdb` (imported inside
python/build_reference_index.py and python/reference_lookup.py, not at
their top level) is already declared in the canonical requirements.txt
- this was never a missing declaration. The failure mode is a raw
`ModuleNotFoundError` surfacing deep inside the index-build step, which
is not a clear setup instruction for a student.

This script never installs anything and introduces no second
dependency-management system - it only checks, via
`importlib.util.find_spec` (which detects an installed distribution
without importing/executing it), whether the third-party modules the
pipeline actually needs are importable in the *current* interpreter,
and if not, reports exactly one canonical fix: `pip install -r
requirements.txt`. Keep REQUIRED_MODULES in sync with requirements.txt;
this is a check against that one file, never a second place to declare
a dependency.

Covers every third-party import used by:
  - preflight (python/check_assignment_preflight.py - stdlib only, but
    checked here anyway since it's the first workflow step)
  - reference-index build (python/build_reference_index.py: duckdb, pandas)
  - reference lookup (python/reference_lookup.py: duckdb)
  - validation / staging (python/validate_record.py, stage_changes.py -
    stdlib only)
  - visualization (python/generate_visualization.py: PyYAML)
  - reading the master workbook / a country snapshot via pandas (openpyxl,
    pandas' .xlsx engine)

Usage:
    python3 python/check_python_dependencies.py
"""

import argparse
import importlib.util
import json
import os
import sys

import pollitik_common as pc

# name -> the exact requirements.txt line that declares it. Import name
# and PyPI/requirements name differ for PyYAML (imported as `yaml`).
REQUIRED_MODULES = {
    "duckdb": "duckdb>=0.10",
    "pandas": "pandas>=2.0",
    "openpyxl": "openpyxl>=3.1",
    "yaml": "PyYAML>=6.0",
}

SETUP_COMMAND = "pip install -r requirements.txt"


def check_dependencies(required=None, finder=None, requirements_path=None):
    """Pure inspection: never imports the heavy module itself (find_spec
    locates it without executing it), never installs anything, never
    writes any file. `required` defaults to REQUIRED_MODULES; a caller
    (tests only) may override it with an arbitrary {module_name: label}
    mapping - e.g. a deliberately-nonexistent module name - to exercise
    the missing-dependency path without touching the real environment.
    `finder` defaults to importlib.util.find_spec; overridable for the
    same reason."""
    required = required if required is not None else REQUIRED_MODULES
    finder = finder or importlib.util.find_spec
    requirements_path = requirements_path or os.path.join(pc.PROJECT_DIR, "requirements.txt")

    missing = []
    checked = []
    for module_name in sorted(required):
        label = required[module_name]
        checked.append(module_name)
        try:
            found = finder(module_name) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            missing.append({"module": module_name, "requirement": label})

    dependencies_ready = len(missing) == 0

    if dependencies_ready:
        instruction = (
            "DEPENDENCIES_READY=true. Continue: run the assignment "
            "preflight check next."
        )
    else:
        instruction = (
            "DEPENDENCIES_READY=false. STOP before preflight, before any "
            "reference-index build, and before any research or staging. "
            "This is an environment/setup problem, not a data problem - "
            "do not record a NOT_FOUND/REVIEW/REJECTED observation "
            "because of it. Run `{}` once (from the repo root), then "
            "retry.".format(SETUP_COMMAND)
        )

    return {
        "checked_modules": checked,
        "missing_modules": missing,
        "dependencies_ready": dependencies_ready,
        "requirements_file": requirements_path,
        "setup_command": SETUP_COMMAND,
        "instruction": instruction,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--required", nargs="*", default=None,
        help="Override the module name list (testing only). Each name is "
             "checked with importlib.util.find_spec exactly like the "
             "default list.",
    )
    args = parser.parse_args()

    required = None
    if args.required:
        required = {name: name for name in args.required}

    result = check_dependencies(required=required)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["dependencies_ready"] else 1)


if __name__ == "__main__":
    main()
