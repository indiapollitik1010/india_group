"""Unit tests for the shared Country/Series normalization helpers in
python/pollitik_common.py (normalize_identifier, series_skeleton,
group_raw_variants, compare_series).

These are pure-function tests - no subprocess, no filesystem, no real
workbook - covering exactly the bug class found and root-caused during
the Canada/Australia data-integrity audit: the EAD workbook stores every
Australia Country cell as 'Australia ' (one trailing ASCII space), and a
plain `==` comparison silently treated that as "no rows found"."""

import pollitik_common as pc


def test_normalize_identifier_strips_trailing_ascii_space():
    assert pc.normalize_identifier("Australia ") == pc.normalize_identifier("Australia")


def test_normalize_identifier_strips_leading_and_trailing_whitespace():
    assert pc.normalize_identifier("  Canada  ") == pc.normalize_identifier("Canada")


def test_normalize_identifier_strips_nbsp():
    assert pc.normalize_identifier("Australia ") == pc.normalize_identifier("Australia")


def test_normalize_identifier_strips_zero_width_chars_and_bom():
    assert pc.normalize_identifier("Australia​") == pc.normalize_identifier("Australia")
    assert pc.normalize_identifier("Australia‌") == pc.normalize_identifier("Australia")
    assert pc.normalize_identifier("Australia‍") == pc.normalize_identifier("Australia")
    assert pc.normalize_identifier("﻿Australia") == pc.normalize_identifier("Australia")


def test_normalize_identifier_strips_tabs_and_newlines():
    assert pc.normalize_identifier("Australia\t\r\n") == pc.normalize_identifier("Australia")


def test_normalize_identifier_casefolds():
    assert pc.normalize_identifier("AUSTRALIA") == pc.normalize_identifier("australia")
    assert pc.normalize_identifier("NEWSPOLL/YouGov") == pc.normalize_identifier("NEWSPOLL/YOUGOV")


# --- normalize_country_slug: countries/<slug>/ folder-name derivation ------
#
# Covers the bug class root-caused when adding the shared all-country
# reference CSV: a plain .strip().lower() left "New Zealand" as "new
# zealand" (a space), which never matched the existing countries/
# new-zealand/ folder. Every script that needs a country's slug
# (check_assignment_preflight.py, init_country_workspace.py,
# build_country_reference_snapshot.py, report_country_ead_coverage.py,
# build_country_assignment_snapshot.py, resolve_assignment_dataset.py)
# imports this single implementation rather than reimplementing it.

def test_normalize_country_slug_single_word_names_unchanged():
    assert pc.normalize_country_slug("Canada") == "canada"
    assert pc.normalize_country_slug("Australia") == "australia"


def test_normalize_country_slug_hyphenates_internal_whitespace():
    assert pc.normalize_country_slug("New Zealand") == "new-zealand"


def test_normalize_country_slug_collapses_multiple_internal_spaces():
    assert pc.normalize_country_slug("New   Zealand") == "new-zealand"
    assert pc.normalize_country_slug("New\tZealand") == "new-zealand"


def test_normalize_country_slug_strips_outer_whitespace_without_hyphenating_it():
    assert pc.normalize_country_slug("  New Zealand  ") == "new-zealand"
    assert pc.normalize_country_slug("  Canada  ") == "canada"


def test_normalize_country_slug_casefolds():
    assert pc.normalize_country_slug("NEW ZEALAND") == "new-zealand"
    assert pc.normalize_country_slug("new zealand") == "new-zealand"


def test_normalize_identifier_nfkc_normalizes():
    # Fullwidth Latin 'A' (U+FF21) NFKC-normalizes to ASCII 'A'.
    assert pc.normalize_identifier("Ａustralia") == pc.normalize_identifier("Australia")


def test_normalize_identifier_none_and_empty():
    assert pc.normalize_identifier(None) == ""
    assert pc.normalize_identifier("") == ""
    assert pc.normalize_identifier("   ") == ""


def test_normalize_identifier_never_mutates_input():
    original = "Australia "
    pc.normalize_identifier(original)
    assert original == "Australia "  # unchanged - normalization is comparison-only


def test_series_skeleton_strips_punctuation_and_spacing():
    assert pc.series_skeleton("Freshwater Strategy") == pc.series_skeleton("FreshwaterStrategy")
    assert pc.series_skeleton("NEWSPOLL/YouGov") != pc.series_skeleton("NEWSPOLL")


def test_group_raw_variants_flags_multiple_raw_spellings_without_rewriting():
    raw_values = ["Australia", "Australia ", "AUSTRALIA", "australia "]
    groups = pc.group_raw_variants(raw_values)
    assert set(groups.keys()) == {"australia"}
    variants = groups["australia"]
    # Every distinct raw spelling is preserved and counted separately -
    # never silently merged into a single rewritten value.
    assert variants == {
        "Australia": 1,
        "Australia ": 1,
        "AUSTRALIA": 1,
        "australia ": 1,
    }


def test_group_raw_variants_single_clean_value_is_not_flagged_as_multiple():
    groups = pc.group_raw_variants(["Canada", "Canada", "Canada"])
    assert groups == {"canada": {"Canada": 3}}
    assert len(groups["canada"]) == 1  # exactly one raw spelling - nothing to flag


def test_compare_series_exact_matches():
    master = {"ACNIELSEN": 113, "IPSOS": 35}
    ead = {"ACNIELSEN": 1, "IPSOS": 1}
    result = pc.compare_series(master, ead)
    assert {m["series"] for m in result["exact_matches"]} == {"ACNIELSEN", "IPSOS"}
    assert result["normalized_case_matches"] == []
    assert result["alias_candidates"] == []
    assert result["unmatched_master"] == []
    assert result["unmatched_ead"] == []


def test_compare_series_normalized_case_match():
    master = {"NEWSPOLL/YouGov": 10}
    ead = {"NEWSPOLL/YOUGOV": 1}
    result = pc.compare_series(master, ead)
    assert result["exact_matches"] == []
    assert result["normalized_case_matches"] == [
        {"master": "NEWSPOLL/YouGov", "ead": "NEWSPOLL/YOUGOV", "master_rows": 10, "ead_rows": 1}
    ]
    assert result["unmatched_master"] == []
    assert result["unmatched_ead"] == []


def test_compare_series_alias_candidate_flagged_but_not_merged():
    """Mirrors the real Australia case: Master has BOTH 'FreshwaterStrategy'
    (which exact-matches EAD) and 'Freshwater Strategy' (a formatting
    variant with no exact EAD counterpart). The variant must be surfaced
    as an alias candidate against EAD's 'FreshwaterStrategy' even though
    that EAD series was already claimed by the exact match - and it must
    still show up as unmatched, never silently merged away."""
    master = {"FreshwaterStrategy": 22, "Freshwater Strategy": 4}
    ead = {"FreshwaterStrategy": 1}
    result = pc.compare_series(master, ead)
    assert {m["series"] for m in result["exact_matches"]} == {"FreshwaterStrategy"}
    assert result["alias_candidates"] == [
        {"master": "Freshwater Strategy", "ead": "FreshwaterStrategy", "master_rows": 4, "ead_rows": 1}
    ]
    # Flagged for review, but NOT removed from unmatched - never auto-merged.
    assert result["unmatched_master"] == [{"series": "Freshwater Strategy", "master_rows": 4}]
    assert result["unmatched_ead"] == []


def test_compare_series_unmatched_both_sides():
    master = {"ONLYINMASTER": 5}
    ead = {"ONLYINEAD": 1}
    result = pc.compare_series(master, ead)
    assert result["exact_matches"] == []
    assert result["normalized_case_matches"] == []
    assert result["alias_candidates"] == []
    assert result["unmatched_master"] == [{"series": "ONLYINMASTER", "master_rows": 5}]
    assert result["unmatched_ead"] == [{"series": "ONLYINEAD", "ead_rows": 1}]


def test_compare_series_full_australia_shaped_scenario():
    """The exact four-group shape required for the real Australia data:
    14 exact matches, one case-normalized match, one alias candidate,
    and one EAD-only unmatched series."""
    master = {
        "ACNIELSEN": 113, "CSES": 3, "ESSENTIALRESEARCH": 140, "FOX&HEDGEHOG": 1,
        "Freshwater Strategy": 4, "FreshwaterStrategy": 22, "GALLUPWORLD_LDR": 1,
        "GALLUPWORLD_LSHP": 19, "IPSOS": 35, "MORGAN": 331, "MorningConsult": 247,
        "NEWSPOLL": 812, "NEWSPOLL/YouGov": 10, "NIELSEN": 26, "Resolve Strategic": 49,
        "YouGov": 23,
    }
    ead = {
        "ACNIELSEN": 1, "CSES": 1, "ESSENTIALRESEARCH": 1, "FOX&HEDGEHOG": 1,
        "FreshwaterStrategy": 1, "GALLUPWORLD_LDR": 1, "GALLUPWORLD_LSHP": 1,
        "IPSOS": 1, "MORGAN": 1, "MorningConsult": 1, "NEWSPOLL": 1,
        "NEWSPOLL/YOUGOV": 1, "NEWSPOLL/PYXIS": 1, "NIELSEN": 1, "Resolve Strategic": 1,
        "YouGov": 1,
    }
    result = pc.compare_series(master, ead)

    assert len(result["exact_matches"]) == 14
    assert {m["series"] for m in result["exact_matches"]} == {
        "ACNIELSEN", "CSES", "ESSENTIALRESEARCH", "FOX&HEDGEHOG", "FreshwaterStrategy",
        "GALLUPWORLD_LDR", "GALLUPWORLD_LSHP", "IPSOS", "MORGAN", "MorningConsult",
        "NEWSPOLL", "NIELSEN", "Resolve Strategic", "YouGov",
    }

    assert result["normalized_case_matches"] == [
        {"master": "NEWSPOLL/YouGov", "ead": "NEWSPOLL/YOUGOV", "master_rows": 10, "ead_rows": 1}
    ]

    assert result["alias_candidates"] == [
        {"master": "Freshwater Strategy", "ead": "FreshwaterStrategy", "master_rows": 4, "ead_rows": 1}
    ]

    assert result["unmatched_master"] == [{"series": "Freshwater Strategy", "master_rows": 4}]
    assert result["unmatched_ead"] == [{"series": "NEWSPOLL/PYXIS", "ead_rows": 1}]
    assert "never auto-merged" in result["note"]


def test_compare_series_never_mutates_input_dicts():
    master = {"IPSOS": 35}
    ead = {"IPSOS": 1}
    master_copy, ead_copy = dict(master), dict(ead)
    pc.compare_series(master, ead)
    assert master == master_copy
    assert ead == ead_copy


def test_reference_index_contains_country_false_when_index_missing(tmp_path):
    missing = tmp_path / "does_not_exist.duckdb"
    assert pc.reference_index_contains_country(str(missing), "australia") is False


def test_reference_index_contains_country_true_and_false(tmp_path):
    import duckdb

    index_path = tmp_path / "index.duckdb"
    con = duckdb.connect(str(index_path))
    con.execute('CREATE TABLE master AS SELECT \'NEWSPOLL\' AS "Series", \'Australia \' AS "Country"')
    con.execute(
        "CREATE TABLE _index_metadata AS SELECT 'x' AS workbook_path, 'x' AS built_at, "
        "0.0 AS workbook_mtime, 'csv' AS source_kind"
    )
    con.close()

    # Matches via normalization even though the stored value has a
    # trailing space, exactly like the real EAD 'Australia ' bug.
    assert pc.reference_index_contains_country(str(index_path), pc.normalize_identifier("Australia")) is True
    assert pc.reference_index_contains_country(str(index_path), pc.normalize_identifier("Canada")) is False


def test_reference_index_contains_country_corrupt_file_fails_closed(tmp_path):
    bad_path = tmp_path / "corrupt.duckdb"
    bad_path.write_bytes(b"not a real duckdb file")
    # Must never raise, and must never be treated as covering the country.
    assert pc.reference_index_contains_country(str(bad_path), "australia") is False
