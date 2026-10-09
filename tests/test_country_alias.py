"""Tests for the controlled country-alias resolver in
python/pollitik_common.py (resolve_country_input, canonical_country_slug,
AmbiguousCountryError) and its use by python/build_country_reference_snapshot.py
and python/build_country_ead_snapshot.py.

Unit tests below exercise the resolver directly (pure functions, no
filesystem). Integration tests at the bottom run the two exporter scripts
as subprocesses against synthetic shared CSVs in an isolated sandbox -
never the real repo's data/master/ or data/reference/.
"""

import csv
import json

import pytest

import pollitik_common as pc
from .conftest import run_script
from .test_country_reference_snapshot import make_country_workspace

REF_HEADER = ["Series", "Date", "Total Count", "Positive", "Neutral", "Negative", "Source", "Country"]
EAD_HEADER = ["Country", "Series", "Description", "Question Type", "Question Wording", "Method"]


# --- resolve_country_input(): the alias table -------------------------------

@pytest.mark.parametrize("alias,expected", [
    ("UK", "United Kingdom"),
    ("uk", "United Kingdom"),
    ("  UK  ", "United Kingdom"),
    ("U.K.", "United Kingdom"),
    ("US", "United States"),
    ("U.S.", "United States"),
    ("USA", "United States"),
    ("usa", "United States"),
    ("South-Korea", "South Korea"),
    ("south-korea", "South Korea"),
    ("México", "Mexico"),
    ("MÉXICO", "Mexico"),
    ("Perú", "Peru"),
    ("Brasil", "Brazil"),
    ("France President", "France_Pres"),
    ("France Pres", "France_Pres"),
    ("france president", "France_Pres"),
    ("France Prime Minister", "France_PM"),
    ("France PM", "France_PM"),
    ("france pm", "France_PM"),
])
def test_resolve_country_input_known_aliases(alias, expected):
    assert pc.resolve_country_input(alias) == expected


@pytest.mark.parametrize("passthrough", [
    "Canada", "Australia", "New Zealand", "Germany", "France_Pres", "France_PM",
    "United Kingdom", "United States", "Mexico", "Peru", "Brazil", "South Korea",
])
def test_resolve_country_input_passthrough_for_non_aliased_or_already_canonical(passthrough):
    """Anything not in the alias table - including a country never
    assigned this course, and an already-canonical Master value like
    "France_Pres" itself - must come back completely unchanged."""
    assert pc.resolve_country_input(passthrough) == passthrough


# --- AmbiguousCountryError: bare "France" -----------------------------------

@pytest.mark.parametrize("value", ["France", "france", "  France  ", "FRANCE"])
def test_resolve_country_input_bare_france_is_ambiguous(value):
    with pytest.raises(pc.AmbiguousCountryError) as exc_info:
        pc.resolve_country_input(value)
    message = str(exc_info.value)
    assert "France_Pres" in message
    assert "France_PM" in message


def test_france_pres_and_france_pm_are_not_ambiguous():
    assert pc.resolve_country_input("France_Pres") == "France_Pres"
    assert pc.resolve_country_input("France_PM") == "France_PM"
    assert pc.resolve_country_input("France President") == "France_Pres"
    assert pc.resolve_country_input("France Prime Minister") == "France_PM"


# --- canonical_country_slug(): human-readable folder names -----------------

def test_canonical_country_slug_overrides_france_offices():
    assert pc.canonical_country_slug("France_Pres") == "france-president"
    assert pc.canonical_country_slug("France_PM") == "france-prime-minister"
    assert pc.canonical_country_slug("France President") == "france-president"
    assert pc.canonical_country_slug("France Prime Minister") == "france-prime-minister"
    assert pc.canonical_country_slug("France Pres") == "france-president"
    assert pc.canonical_country_slug("France PM") == "france-prime-minister"


def test_canonical_country_slug_unaffected_for_ordinary_countries():
    assert pc.canonical_country_slug("Canada") == "canada"
    assert pc.canonical_country_slug("New Zealand") == "new-zealand"
    assert pc.canonical_country_slug("UK") == "united-kingdom"
    assert pc.canonical_country_slug("USA") == "united-states"


def test_canonical_country_slug_bare_france_is_ambiguous():
    with pytest.raises(pc.AmbiguousCountryError):
        pc.canonical_country_slug("France")


# --- integration: build_country_reference_snapshot.py -----------------------

def _write_shared_reference_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REF_HEADER)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def _ref_row(country, series="X"):
    return {"Series": series, "Date": "2020-01-01", "Total Count": "1000",
            "Positive": "50", "Neutral": "", "Negative": "40",
            "Source": "https://example", "Country": country}


def test_reference_snapshot_resolves_uk_alias(sandbox):
    make_country_workspace(sandbox, "united-kingdom")
    shared_csv = sandbox / "shared_reference.csv"
    _write_shared_reference_csv(shared_csv, [_ref_row("United Kingdom"), _ref_row("France")])

    proc = run_script("build_country_reference_snapshot.py", sandbox, args=[
        "--country", "UK",
        "--workbook", str(sandbox / "does_not_exist.xlsx"),
        "--shared-reference-csv", str(shared_csv),
    ])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["resolved_country"] == "United Kingdom"
    assert result["country_slug"] == "united-kingdom"
    assert result["row_count"] == 1


def test_reference_snapshot_resolves_france_president_alias_and_excludes_bare_france(sandbox):
    make_country_workspace(sandbox, "france-president")
    shared_csv = sandbox / "shared_reference.csv"
    _write_shared_reference_csv(shared_csv, [
        _ref_row("France_Pres", "PRES_APPROVAL"),
        _ref_row("France_PM", "PM_APPROVAL"),
        _ref_row("France", "UNCATEGORIZED"),
    ])

    proc = run_script("build_country_reference_snapshot.py", sandbox, args=[
        "--country", "France President",
        "--workbook", str(sandbox / "does_not_exist.xlsx"),
        "--shared-reference-csv", str(shared_csv),
    ])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["resolved_country"] == "France_Pres"
    assert result["country_slug"] == "france-president"
    assert result["row_count"] == 1

    out_path = sandbox / "countries" / "france-president" / "data" / "france-president_reference_snapshot.csv"
    with open(out_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["Country"] == "France_Pres"
    assert rows[0]["Series"] == "PRES_APPROVAL"


def test_reference_snapshot_resolves_france_pm_alias(sandbox):
    make_country_workspace(sandbox, "france-prime-minister")
    shared_csv = sandbox / "shared_reference.csv"
    _write_shared_reference_csv(shared_csv, [
        _ref_row("France_Pres", "PRES_APPROVAL"),
        _ref_row("France_PM", "PM_APPROVAL"),
    ])

    proc = run_script("build_country_reference_snapshot.py", sandbox, args=[
        "--country", "France Prime Minister",
        "--workbook", str(sandbox / "does_not_exist.xlsx"),
        "--shared-reference-csv", str(shared_csv),
    ])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["resolved_country"] == "France_PM"
    assert result["row_count"] == 1


def test_reference_snapshot_bare_france_refuses_with_clear_error(sandbox):
    shared_csv = sandbox / "shared_reference.csv"
    _write_shared_reference_csv(shared_csv, [_ref_row("France_Pres"), _ref_row("France_PM"), _ref_row("France")])

    proc = run_script("build_country_reference_snapshot.py", sandbox, args=[
        "--country", "France",
        "--workbook", str(sandbox / "does_not_exist.xlsx"),
        "--shared-reference-csv", str(shared_csv),
    ])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["built"] is False
    assert "France_Pres" in result["error"]
    assert "France_PM" in result["error"]
    # Must refuse before ever touching the shared CSV or a workspace dir.
    assert not (sandbox / "countries" / "france").exists()


# --- integration: build_country_ead_snapshot.py -----------------------------

def _write_shared_ead_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EAD_HEADER)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def _ead_row(country, series="X"):
    return {"Country": country, "Series": series, "Description": "d",
            "Question Type": "Approval", "Question Wording": "Do you approve...",
            "Method": ""}


def test_ead_snapshot_resolves_usa_alias(sandbox):
    make_country_workspace(sandbox, "united-states")
    shared_csv = sandbox / "shared_ead.csv"
    _write_shared_ead_csv(shared_csv, [_ead_row("United States"), _ead_row("Canada")])

    proc = run_script("build_country_ead_snapshot.py", sandbox, args=[
        "--country", "USA",
        "--ead-workbook", str(sandbox / "does_not_exist.xlsx"),
        "--shared-ead-csv", str(shared_csv),
    ])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["resolved_country"] == "United States"
    assert result["country_slug"] == "united-states"
    assert result["row_count"] == 1


def test_ead_snapshot_resolves_france_pm_alias_and_excludes_bare_france(sandbox):
    make_country_workspace(sandbox, "france-prime-minister")
    shared_csv = sandbox / "shared_ead.csv"
    _write_shared_ead_csv(shared_csv, [
        _ead_row("France_Pres", "PRES_SAT"),
        _ead_row("France_PM", "PM_SAT"),
        _ead_row("France", "UNCATEGORIZED"),
    ])

    proc = run_script("build_country_ead_snapshot.py", sandbox, args=[
        "--country", "France PM",
        "--ead-workbook", str(sandbox / "does_not_exist.xlsx"),
        "--shared-ead-csv", str(shared_csv),
    ])
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["resolved_country"] == "France_PM"
    assert result["row_count"] == 1

    out_path = sandbox / "countries" / "france-prime-minister" / "data" / "france-prime-minister_ead_series_question_wording.csv"
    with open(out_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["Series"] == "PM_SAT"


def test_ead_snapshot_bare_france_refuses_with_clear_error(sandbox):
    shared_csv = sandbox / "shared_ead.csv"
    _write_shared_ead_csv(shared_csv, [_ead_row("France_Pres"), _ead_row("France_PM"), _ead_row("France")])

    proc = run_script("build_country_ead_snapshot.py", sandbox, args=[
        "--country", "France",
        "--ead-workbook", str(sandbox / "does_not_exist.xlsx"),
        "--shared-ead-csv", str(shared_csv),
    ])
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["built"] is False
    assert "France_Pres" in result["error"]
    assert "France_PM" in result["error"]
    assert not (sandbox / "countries" / "france").exists()


def test_shared_csvs_never_modified_by_alias_resolution(sandbox):
    """Resolving an alias must never rewrite the shared CSV it reads
    from - it only changes which Country value gets matched."""
    shared_csv = sandbox / "shared_reference.csv"
    _write_shared_reference_csv(shared_csv, [_ref_row("United Kingdom")])
    before = shared_csv.read_bytes()

    make_country_workspace(sandbox, "united-kingdom")
    proc = run_script("build_country_reference_snapshot.py", sandbox, args=[
        "--country", "UK",
        "--workbook", str(sandbox / "does_not_exist.xlsx"),
        "--shared-reference-csv", str(shared_csv),
    ])
    assert proc.returncode == 0, proc.stderr
    assert shared_csv.read_bytes() == before
