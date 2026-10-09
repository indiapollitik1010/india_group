"""Regression coverage for python/check_python_dependencies.py.

Bug this guards against: a real fresh-student Codex test found the
correct branch, AGENTS.md, Canada snapshot, and preflight script, then
correctly attempted to build the local reference index - but the build
crashed with `ModuleNotFoundError: No module named 'duckdb'` instead of
stopping with one clear setup instruction. `duckdb` was already declared
in requirements.txt; the missing piece was a dependency-readiness check
that runs before preflight/index-build and fails closed with a plain
setup step, not a traceback.

These tests run the real python/check_python_dependencies.py as a
subprocess (same convention as test_assignment_preflight.py), and check
requirements.txt directly. Nothing here installs a package, fetches the
web, stages a candidate, or touches production data.
"""

import json

from .conftest import REPO_ROOT, run_script


def run_dep_check(project_dir, extra_args=None):
    proc = run_script(
        "check_python_dependencies.py", project_dir,
        args=[*(extra_args or [])],
    )
    return proc, json.loads(proc.stdout)


def test_requirements_txt_declares_all_pipeline_dependencies():
    """Requirement 1/2: confirm duckdb (and every other package the
    preflight -> index-build -> lookup -> validate -> stage -> visualize
    chain needs) is already declared in the one canonical dependency
    file - never a second requirements list."""
    requirements_text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    for expected in ("duckdb", "pandas", "openpyxl", "PyYAML"):
        assert expected in requirements_text, (
            "{} must be declared in requirements.txt".format(expected)
        )


def test_normal_configured_environment_reports_ready(tmp_path):
    """The real dev/CI environment (the one running pytest) has already
    had requirements.txt installed, so the default module list must
    report ready with no missing modules - this is the environment
    every real preflight/index-build run also uses."""
    proc, result = run_dep_check(tmp_path)
    assert proc.returncode == 0
    assert result["dependencies_ready"] is True
    assert result["missing_modules"] == []
    assert "duckdb" in result["checked_modules"]
    assert "pandas" in result["checked_modules"]


def test_missing_dependency_produces_setup_failure_not_data_record(tmp_path):
    """A missing module must stop as an environment/setup problem - exit
    non-zero with a plain install instruction - never something that
    looks like a NOT_FOUND/REVIEW/REJECTED pipeline result."""
    proc, result = run_dep_check(
        tmp_path, extra_args=["--required", "totally_not_a_real_module_xyz"],
    )
    assert proc.returncode == 1
    assert result["dependencies_ready"] is False
    assert result["missing_modules"] == [
        {"module": "totally_not_a_real_module_xyz", "requirement": "totally_not_a_real_module_xyz"}
    ]
    assert result["setup_command"] == "pip install -r requirements.txt"
    # Must read as an environment instruction, not a data-pipeline status:
    # no pipeline-status field/value anywhere in the result, and the
    # instruction explicitly names this an environment/setup problem.
    assert "status" not in result
    assert "environment/setup problem" in result["instruction"]
    assert "pip install" in result["instruction"]


def test_partial_missing_dependency_lists_only_the_missing_one(tmp_path):
    """A real, importable stdlib-adjacent module mixed with a fake one
    should report exactly the fake one as missing - proves the check
    inspects each module independently rather than failing all-or-nothing
    on the first miss."""
    proc, result = run_dep_check(
        tmp_path, extra_args=["--required", "json", "totally_not_a_real_module_xyz"],
    )
    assert proc.returncode == 1
    assert result["dependencies_ready"] is False
    missing_names = [m["module"] for m in result["missing_modules"]]
    assert missing_names == ["totally_not_a_real_module_xyz"]
    assert "json" in result["checked_modules"]


def test_dependency_check_never_writes_or_installs(tmp_path):
    """Read-only guarantee: running the check (in either state) must not
    create any file under the isolated project dir - it only inspects
    the interpreter's already-installed packages."""
    before = set(tmp_path.rglob("*"))
    run_dep_check(tmp_path)
    run_dep_check(tmp_path, extra_args=["--required", "totally_not_a_real_module_xyz"])
    after = set(tmp_path.rglob("*"))
    assert before == after
