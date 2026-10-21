"""Tests for python/student_workspace_setup.py - the dependency-free
classroom entry point that wraps init_country_workspace.py,
build_country_reference_snapshot.py, and build_country_ead_snapshot.py
into one command for the three basic student setup tasks:

  1. create a country workspace
  2. generate the country reference snapshot
  3. generate the country EAD series/question-wording CSV

Every test here runs against an isolated sandbox (never the real repo's
countries/ or data/master/), seeded with the REAL tracked shared CSVs
(data/reference/pollitik_reference.csv,
data/reference/ead_series_question_wording.csv) - these are NOT
git-ignored, so a genuine fresh clone always has them. This is
deliberately the real "fresh clone, no hidden Excel workbook" shape:
data/master/ exists but is empty, exactly like a real student checkout.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from .conftest import REPO_ROOT, run_script

REAL_SHARED_REFERENCE_CSV = REPO_ROOT / "data" / "reference" / "pollitik_reference.csv"
REAL_SHARED_EAD_CSV = REPO_ROOT / "data" / "reference" / "ead_series_question_wording.csv"


def run_setup(sandbox, args):
    return run_script("student_workspace_setup.py", sandbox, args=args)


def seed_real_shared_csvs(sandbox):
    """Copies the repo's actual tracked shared CSVs into an isolated
    sandbox's data/reference/ - simulating exactly what a fresh clone
    ships (these two files are tracked, not git-ignored), without ever
    writing into the real repo tree."""
    dest = sandbox / "data" / "reference"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(REAL_SHARED_REFERENCE_CSV, dest / "pollitik_reference.csv")
    shutil.copy(REAL_SHARED_EAD_CSV, dest / "ead_series_question_wording.csv")


# --- fresh-clone / no-hidden-Excel: full 3-step run against real shared CSVs ---

def test_argentina_full_setup_from_real_shared_csvs_no_master_workbook(sandbox):
    seed_real_shared_csvs(sandbox)
    assert not (sandbox / "data" / "master" / "pollitik_master.xlsx").exists()
    assert not (sandbox / "data" / "master" / "EAD Series and Question Wording.xlsx").exists()

    proc = run_setup(sandbox, ["--country", "Argentina"])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["ok"] is True
    assert result["steps_run"] == ["workspace", "reference", "ead"]

    ws = result["results"]["workspace"]
    assert ws["ok"] is True and ws["skipped"] is False
    assert ws["country_slug"] == "argentina"

    ref = result["results"]["reference"]
    assert ref["ok"] is True and ref["skipped"] is False
    assert ref["source"] == "shared_reference_csv"
    assert ref["row_count"] > 0
    assert os.path.exists(ref["output_path"])

    ead = result["results"]["ead"]
    assert ead["ok"] is True and ead["skipped"] is False
    assert ead["source"] == "shared_ead_reference_csv"
    assert ead["row_count"] > 0
    assert os.path.exists(ead["output_path"])

    out_ref = sandbox / "countries" / "argentina" / "data" / "argentina_reference_snapshot.csv"
    out_ead = sandbox / "countries" / "argentina" / "data" / "argentina_ead_series_question_wording.csv"
    assert out_ref.exists() and out_ead.exists()


def test_rerun_is_a_safe_noop_skip_not_a_failure(sandbox):
    seed_real_shared_csvs(sandbox)
    first = run_setup(sandbox, ["--country", "Argentina"])
    assert first.returncode == 0, first.stderr

    second = run_setup(sandbox, ["--country", "Argentina"])
    assert second.returncode == 0, second.stderr
    result = json.loads(second.stdout)
    assert result["ok"] is True
    assert result["results"]["workspace"]["skipped"] is True
    assert result["results"]["reference"]["skipped"] is True
    assert result["results"]["ead"]["skipped"] is True


def test_reference_step_alone_requires_workspace_first(sandbox):
    seed_real_shared_csvs(sandbox)
    proc = run_setup(sandbox, ["--country", "Argentina", "--steps", "reference"])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["ok"] is False
    assert "init_country_workspace.py" in result["results"]["reference"]["error"]


# --- UK / USA alias resolution -------------------------------------------

def test_uk_alias_resolves_to_united_kingdom(sandbox):
    seed_real_shared_csvs(sandbox)
    proc = run_setup(sandbox, ["--country", "UK"])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["ok"] is True
    assert result["results"]["workspace"]["country_slug"] == "united-kingdom"
    assert result["results"]["reference"]["resolved_country"] == "United Kingdom"
    assert result["results"]["ead"]["resolved_country"] == "United Kingdom"


def test_usa_alias_resolves_to_united_states(sandbox):
    seed_real_shared_csvs(sandbox)
    proc = run_setup(sandbox, ["--country", "USA"])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["ok"] is True
    assert result["results"]["workspace"]["country_slug"] == "united-states"
    assert result["results"]["reference"]["resolved_country"] == "United States"
    assert result["results"]["ead"]["resolved_country"] == "United States"


# --- France President / France Prime Minister / plain France -------------

def test_france_president_resolves_and_never_touches_pm_rows(sandbox):
    seed_real_shared_csvs(sandbox)
    proc = run_setup(sandbox, ["--country", "France President"])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["ok"] is True
    assert result["results"]["workspace"]["country_slug"] == "france-president"
    assert result["results"]["reference"]["resolved_country"] == "France_Pres"
    out_path = Path(result["results"]["reference"]["output_path"])
    contents = out_path.read_text(encoding="utf-8")
    assert "France_PM" not in contents


def test_france_pm_resolves_and_never_touches_president_rows(sandbox):
    seed_real_shared_csvs(sandbox)
    proc = run_setup(sandbox, ["--country", "France Prime Minister"])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["ok"] is True
    assert result["results"]["workspace"]["country_slug"] == "france-prime-minister"
    assert result["results"]["reference"]["resolved_country"] == "France_PM"
    out_path = Path(result["results"]["reference"]["output_path"])
    contents = out_path.read_text(encoding="utf-8")
    assert "France_Pres" not in contents


def test_plain_france_is_rejected_before_writing_anything(sandbox):
    seed_real_shared_csvs(sandbox)
    proc = run_setup(sandbox, ["--country", "France"])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["ok"] is False
    err = result["results"]["workspace"]["error"]
    assert "France_Pres" in err and "France_PM" in err
    assert not (sandbox / "countries" / "france").exists()
    assert not (sandbox / "countries" / "france-president").exists()
    assert not (sandbox / "countries" / "france-prime-minister").exists()


# --- dependency-free: works with duckdb/pandas/PyYAML/openpyxl unimportable ---

@pytest.fixture
def blocked_third_party_env():
    """A PYTHONPATH-prefix directory containing stub modules named
    duckdb/pandas/yaml/openpyxl that raise ImportError the instant
    Python tries to import them - the same failure shape as those
    packages genuinely not being installed (a real ModuleNotFoundError
    IS an ImportError), without touching the real environment's actual
    installed packages."""
    stub_dir = Path(tempfile.mkdtemp(prefix="pollitik_blocked_deps_"))
    for name in ("duckdb", "pandas", "yaml", "openpyxl"):
        (stub_dir / "{}.py".format(name)).write_text(
            "raise ImportError('{} deliberately blocked for dependency-free "
            "student path test')\n".format(name),
            encoding="utf-8",
        )
    yield stub_dir
    shutil.rmtree(stub_dir, ignore_errors=True)


def test_full_setup_succeeds_with_no_third_party_packages_importable(sandbox, blocked_third_party_env):
    seed_real_shared_csvs(sandbox)
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(sandbox)
    env["PYTHONPATH"] = str(blocked_third_party_env) + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "python" / "student_workspace_setup.py"), "--country", "Argentina"],
        capture_output=True, text=True, env=env, cwd=str(sandbox),
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["ok"] is True
    assert result["results"]["reference"]["source"] == "shared_reference_csv"
    assert result["results"]["ead"]["source"] == "shared_ead_reference_csv"

    # Sanity check: confirm the stub really does block a real import, so a
    # green result above means "worked without the package" and not
    # "the stub silently did nothing."
    sanity = subprocess.run(
        [sys.executable, "-c", "import duckdb"], capture_output=True, text=True, env=env,
    )
    assert sanity.returncode != 0
    assert "deliberately blocked" in sanity.stderr
