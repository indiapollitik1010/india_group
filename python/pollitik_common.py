"""Shared helpers for the Pollitik deterministic pipeline scripts.

These scripts implement the DETERMINISTIC CODE side of the split described
in the pollitik-executive-support Skill: URL/domain checking, arithmetic,
Excel I/O, staging, and logging. Semantic work (translation, series
matching, ambiguous classification) stays with the LLM/agents; this module
and its callers never do that.
"""

import datetime
import json
import os
import re
import unicodedata
import urllib.parse
from collections import Counter, defaultdict

# The repository root - this file lives at <repo>/python/pollitik_common.py,
# one level below it. Honor an explicitly-set CLAUDE_PROJECT_DIR (tests and
# service/agent.py rely on this override), but never fall back to the
# caller's current working directory: a script invoked from outside the
# repo with CLAUDE_PROJECT_DIR unset must still resolve config/data/log
# paths against the real repo, not silently treat them as missing (e.g.
# an empty allow-list going undetected).
PROJECT_DIR = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

ALLOWED_DOMAINS_PATH = os.path.join(PROJECT_DIR, "config", "allowed_domains.txt")
COUNTRY_RULES_PATH = os.path.join(PROJECT_DIR, "config", "country_rules.yaml")
SCHEMA_MAPPING_PATH = os.path.join(PROJECT_DIR, "config", "schema_mapping.yaml")
SOURCE_SYSTEMS_PATH = os.path.join(PROJECT_DIR, "config", "source_systems.yaml")
SOURCE_VALIDATION_RULES_PATH = os.path.join(PROJECT_DIR, "config", "source_validation_rules.yaml")

# Read-only authoritative EAD Series/Question-Wording reference (NOT the
# production master workbook - see docs/ead/reference/ and Skill section
# on the EAD reference). Never written to by this project.
EAD_REFERENCE_DIR = os.path.join(PROJECT_DIR, "docs", "ead", "reference")
EAD_REFERENCE_WORKBOOK = os.path.join(EAD_REFERENCE_DIR, "EAD Series and Question Wording.xlsx")

STAGING_DIR = os.path.join(PROJECT_DIR, "data", "staging")
STAGING_FILE = os.path.join(STAGING_DIR, "candidates.jsonl")

MASTER_DIR = os.path.join(PROJECT_DIR, "data", "master")
ARCHIVE_DIR = os.path.join(PROJECT_DIR, "data", "archive")
DEFAULT_MASTER_WORKBOOK = os.path.join(MASTER_DIR, "pollitik_master.xlsx")

# Canonical series/question-wording reference (Skill section 48) - the same
# file as EAD_REFERENCE_WORKBOOK above, consulted here specifically to
# confirm an established series' single applicable question. Never treated
# as evidence for a new external observation and never written to. Kept out
# of MASTER_DIR/data/master/ deliberately, so it is never confused with (or
# swept up by) production-master-workbook backup/write logic.
EAD_WORDING_REFERENCE_PATH = EAD_REFERENCE_WORKBOOK

# Tracked, student-safe, ALL-country reference export (every country in one
# file, same 8 canonical columns as a per-country
# countries/<slug>/data/<slug>_reference_snapshot.csv). Built from the
# master workbook by python/build_reference_csv.py and used by
# python/build_country_reference_snapshot.py as a fallback source when the
# master workbook itself isn't present in a checkout (it's git-ignored /
# environment-dependent) - never preferred over the workbook when the
# workbook is available.
REFERENCE_DIR = os.path.join(PROJECT_DIR, "data", "reference")
SHARED_REFERENCE_CSV_PATH = os.path.join(REFERENCE_DIR, "pollitik_reference.csv")

# Tracked, student-safe, ALL-country EAD Series/Question-Wording export -
# the same fallback role as SHARED_REFERENCE_CSV_PATH above, but sourced
# from EAD_WORDING_REFERENCE_PATH instead of the master workbook. Built by
# python/build_ead_reference_csv.py; consumed as a fallback by
# python/build_country_ead_snapshot.py when the EAD workbook itself isn't
# present in a checkout.
SHARED_EAD_REFERENCE_CSV_PATH = os.path.join(REFERENCE_DIR, "ead_series_question_wording.csv")

LOGS_DIR = os.path.join(PROJECT_DIR, "logs")
WRITES_LOG_DIR = os.path.join(LOGS_DIR, "writes")
VALIDATION_LOG_DIR = os.path.join(LOGS_DIR, "validation")
RESEARCH_LOG_DIR = os.path.join(LOGS_DIR, "research")

# Derived, rebuildable reference index (Skill section 13: "the existing
# dataset is reference material only"). Excel remains canonical - this is
# never written back to and never treated as a source of new external
# evidence, only as a fast local index of what the workbook already says.
REFERENCE_INDEX_PATH = os.path.join(PROJECT_DIR, "data", "reference_index.duckdb")

# Source-retrieval cache (Skill sections 5-6): keyed by URL, holds only
# metadata/evidence that already passed real retrieval - never a
# substitute for retrieval, only a way to avoid re-fetching/re-interpreting
# an already-verified page.
CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
SOURCE_CACHE_FILE = os.path.join(CACHE_DIR, "sources.jsonl")
CACHE_ACCESS_LOG = os.path.join(RESEARCH_LOG_DIR, "cache_access.jsonl")


def utc_now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_allowed_domains():
    domains = []
    try:
        with open(ALLOWED_DOMAINS_PATH, "r", encoding="utf-8") as f:
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


def extract_host(url):
    try:
        return urllib.parse.urlparse(url).hostname
    except ValueError:
        return None


_QUOTE_DASH_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "«": '"', "»": '"',
    "–": "-", "—": "-", "−": "-",
}
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_question_wording(text):
    """Deterministic, matching-only normalization (EAD reference workbook
    integration): case-folds, collapses/trims whitespace, and unifies
    Unicode quote/dash variants to their ASCII equivalents.

    Used for BOTH question-wording and Series-name matching - the EAD
    reference workbook inspection found real Series-name collisions that
    differ only by case or trailing whitespace (e.g. "IRI" vs "IRI ",
    "Ipsos" vs "IPSOS"), so the same conservative normalization applies
    to both.

    This NEVER removes substantively meaningful words and is used only
    to compute a derived `*_normalized` column/value for comparison. The
    original text must always be preserved unchanged alongside it -
    nothing in this project overwrites original wording with the
    normalized form.

    Returns None for None/NaN/pandas-NA-ish input (so it composes cleanly
    with optional/missing source columns - a pandas column read from
    Excel can carry a bare float NaN for an empty cell even after a
    string-dtype cast, not just None, and normalizing that naively would
    otherwise produce the literal text "nan").
    """
    if text is None:
        return None
    if isinstance(text, float) and text != text:  # NaN != NaN
        return None
    s = str(text)
    if s in ("nan", "<NA>", "NaT", "None"):
        return None
    for src, dst in _QUOTE_DASH_MAP.items():
        s = s.replace(src, dst)
    s = unicodedata.normalize("NFKC", s)
    s = s.strip()
    s = _WHITESPACE_RE.sub(" ", s)
    return s.lower()


def load_schema_field_aliases():
    """Read config/schema_mapping.yaml's per-field `aliases` (e.g.
    Sample_Size's historical "Total Count" name) and return
    {internal_field_name: [alias strings]}.

    Used by apply_changes.py to recognize a historical/alternate workbook
    column name as the same semantic field, without ever creating a new
    column or renaming an existing one (Skill: "never invent workbook
    columns"). Returns {} if the file is missing, empty, or unparseable -
    callers must keep working with plain direct-name matching in that
    case, exactly as before this file existed.
    """
    try:
        import yaml
    except ImportError:
        return {}

    try:
        with open(SCHEMA_MAPPING_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except OSError:
        return {}

    if not isinstance(data, dict):
        return {}

    aliases = {}
    for canonical_name, spec in (data.get("fields") or {}).items():
        if not isinstance(spec, dict):
            continue
        internal_field = spec.get("internal_field")
        field_aliases = spec.get("aliases")
        if internal_field and field_aliases:
            aliases[internal_field] = list(field_aliases)
    return aliases


def append_jsonl(path, record):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_jsonl_atomic(path, records):
    """Rewrite an entire JSONL file atomically (write to a .tmp sibling,
    then os.replace it into place) - the same pattern source_cache.py
    uses for its cache file. Used for in-place record *replacement*
    (stage_changes.py update mode), never for the normal append path:
    replacing a staged record means the whole file's contents change,
    so a plain append cannot express it, and a non-atomic rewrite could
    leave a torn/partial file if interrupted mid-write."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def read_jsonl(path):
    records = []
    if not os.path.exists(path):
        return records
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def read_staged_records_for_job(job_id):
    """Deterministic lookup, not an LLM self-report: every staged record
    whose job_id (set by stage_changes.py from POLLITIK_JOB_ID) matches."""
    return [r for r in read_jsonl(STAGING_FILE) if r.get("job_id") == job_id]


def read_cache_access_for_job(job_id):
    """Deterministic lookup, not an LLM self-report: every cache lookup
    (hit or miss) source_cache.py logged for this job_id."""
    return [r for r in read_jsonl(CACHE_ACCESS_LOG) if r.get("job_id") == job_id]


def parse_batch_input(text):
    """Parse batch input text as either a JSON array or JSONL (one JSON
    value per non-blank line) of candidate records.

    Used by validate_record.py and stage_changes.py to add a batch mode
    without duplicating parsing logic between them. A single JSON object
    is accepted too (wrapped as a one-element list) so callers don't need
    a separate code path for that case in batch mode.

    Never raises on malformed input: an unparseable JSONL line becomes an
    error-marker dict (`__parse_error__`/`__raw_line__`) in the returned
    list instead of aborting the whole batch, so one bad line can't cause
    the records around it to be silently dropped.
    """
    stripped = text.strip()
    if not stripped:
        return []

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]

    records = []
    for line_number, line in enumerate(stripped.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            records.append({
                "__parse_error__": "Line {}: {}".format(line_number, exc),
                "__raw_line__": line,
            })
    return records


NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")


def is_number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if isinstance(value, str) and NUMERIC_RE.match(value.strip()):
        return True
    return False


def to_number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return float(str(value).strip())


# --- Shared Country/Series identifier normalization -------------------
#
# One deterministic rule, reused everywhere Country/Series values from
# the master workbook, the EAD workbook, a country reference-snapshot
# CSV, or a local reference index need to be COMPARED. This exists
# because a real bug was found and root-caused during a Canada/Australia
# data-integrity audit: the EAD workbook stores every Australia Country
# cell as 'Australia ' (one trailing ASCII space), and an inspection
# script using plain `==` silently treated that as "no Australia rows
# found" - not because the data was missing, but because the comparison
# was too strict. This helper - and ONLY this helper - is the fix:
# reuse it for matching instead of reimplementing normalization
# ad hoc. It is for COMPARISON only; it never rewrites a stored value,
# and every caller that uses it must keep reporting the original raw
# value alongside the normalized one.
_INVISIBLE_CHARS = (" ", "​", "‌", "‍", "﻿", "\t", "\r", "\n")


def normalize_identifier(value):
    """normalize(v) = casefold(strip(remove_invisible_chars(NFKC(str(v)))))

    Strips ordinary leading/trailing whitespace plus NBSP/zero-width
    space/zero-width non-joiner/zero-width joiner/BOM/tab/CR/LF, NFKC-
    normalizes, then casefolds. Deterministic and side-effect-free -
    never mutates a source value, only used to decide whether two raw
    values should be treated as the same identifier for matching."""
    if value is None:
        return ""
    s = unicodedata.normalize("NFKC", str(value))
    for ch in _INVISIBLE_CHARS:
        s = s.replace(ch, "")
    return s.strip().casefold()


def normalize_country_slug(country):
    """The single, canonical countries/<slug>/ folder-name derivation -
    every script that needs a country's slug imports this rather than
    reimplementing it, so they can never disagree.

    Lowercases, strips leading/trailing whitespace, and collapses any run
    of internal whitespace to a single '-' so a multi-word country name
    (e.g. "New Zealand") resolves to the same slug as its existing
    hyphenated folder (countries/new-zealand/), the same way a one-word
    name like "Canada" already resolved to countries/canada/. Nothing
    else is invented or guessed - never applied to a Series/pollster/etc.
    identifier, only to a country name being turned into a folder name."""
    return re.sub(r"\s+", "-", str(country).strip().lower())


class AmbiguousCountryError(Exception):
    """Raised by resolve_country_input() for a country input that must
    never be auto-resolved. Currently only plain "France": Master has
    separate France_Pres/France_PM rows and no single-office 'France'
    assignment, so guessing one would silently pick the wrong (or an
    unrelated, uncategorized) dataset."""


# Controlled alias table for THIS COURSE'S assigned countries only (not a
# general-purpose country-name database). Deliberately NOT fuzzy
# matching - every key is one explicitly-approved input spelling, keyed
# by normalize_identifier() (so case/leading-trailing-whitespace variants
# of these exact listed spellings are accepted for free, the same way
# normalize_identifier already does for every other country), mapped to
# the one canonical Master Country value real Master rows actually use.
# Adding an entry here never touches the Master workbook or either
# shared reference CSV - it only changes which Master value a given
# student-typed name resolves to before matching/exporting.
_COUNTRY_ALIASES_RAW = {
    "UK": "United Kingdom",
    "U.K.": "United Kingdom",
    "US": "United States",
    "U.S.": "United States",
    "USA": "United States",
    "South-Korea": "South Korea",
    "México": "Mexico",
    "Perú": "Peru",
    "Brasil": "Brazil",
    "France President": "France_Pres",
    "France Pres": "France_Pres",
    "France Prime Minister": "France_PM",
    "France PM": "France_PM",
}

# Folder slugs that must stay human-readable rather than the raw
# Master-value default: normalize_country_slug("France_Pres") would
# otherwise give "france_pres" (underscore, not the hyphenated
# countries/<slug>/ style every other country uses).
_CANONICAL_SLUG_OVERRIDES_RAW = {
    "France_Pres": "france-president",
    "France_PM": "france-prime-minister",
}

_AMBIGUOUS_COUNTRY_INPUTS = {"france"}


def resolve_country_input(country):
    """Resolve a student-typed country name to the exact Master Country
    value to match rows against, via the controlled alias table above -
    never fuzzy, never guessed. Plain "France" is deliberately never
    auto-resolved - raises AmbiguousCountryError so the caller can ask
    the student to specify France_Pres/France President or
    France_PM/France Prime Minister instead of silently matching the
    wrong (or an unrelated bare-'France') bucket. Any input with no
    alias entry - including a country not on the alias list at all, or
    an already-canonical Master value like "France_Pres" itself - is
    returned unchanged, so this never affects a country that isn't in
    the alias table."""
    key = normalize_identifier(country)
    if key in _AMBIGUOUS_COUNTRY_INPUTS:
        raise AmbiguousCountryError(
            "'{}' is ambiguous - Master has separate France_Pres and "
            "France_PM rows, not one 'France' assignment. Specify which "
            "office: use 'France_Pres' or 'France President' for the "
            "President, or 'France_PM' or 'France Prime Minister' for "
            "the Prime Minister.".format(country)
        )
    aliases = {normalize_identifier(k): v for k, v in _COUNTRY_ALIASES_RAW.items()}
    return aliases.get(key, country)


def canonical_country_slug(country):
    """Human-readable countries/<slug>/ folder name for a country,
    resolving aliases first (see resolve_country_input()) so e.g. both
    "France President" and "France_Pres" land in the same
    countries/france-president/ folder. Overrides
    normalize_country_slug()'s default only for the Master values whose
    own raw text isn't itself human-readable (see
    _CANONICAL_SLUG_OVERRIDES_RAW). Propagates AmbiguousCountryError
    unchanged for a country (e.g. plain "France") that must not be
    auto-resolved at all."""
    resolved = resolve_country_input(country)
    if resolved in _CANONICAL_SLUG_OVERRIDES_RAW:
        return _CANONICAL_SLUG_OVERRIDES_RAW[resolved]
    return normalize_country_slug(resolved)


def series_skeleton(value):
    """Alphanumeric-only normalized form of `value` - strips punctuation
    and spacing on top of normalize_identifier(). Used ONLY to SURFACE
    likely alias/formatting-variant candidates (e.g. 'Freshwater
    Strategy' vs 'FreshwaterStrategy') for human review - never to
    auto-merge or rewrite anything."""
    return "".join(ch for ch in normalize_identifier(value) if ch.isalnum())


def group_raw_variants(raw_values):
    """Given an iterable of raw values (e.g. every raw Country string
    seen while matching one target country), returns
    {normalized_value: {raw_value: count}} so a caller can explicitly
    flag when more than one raw spelling collapses to the same
    normalized identifier, instead of silently treating them as
    identical or rewriting one into the other."""
    groups = defaultdict(Counter)
    for v in raw_values:
        groups[normalize_identifier(v)][v] += 1
    return {k: dict(v) for k, v in groups.items()}


def compare_series(master_counts, ead_counts):
    """Read-only 4-group comparison of two {raw_series: row_count} maps
    (e.g. a country's Master Series counts vs. its EAD Series counts),
    using normalize_identifier() for case/whitespace-insensitive
    matching and series_skeleton() only to SURFACE likely alias/
    formatting-variant candidates for human review. Never merges,
    rewrites, or drops a raw spelling - purely a reporting helper.

    Returns:
      exact_matches            - identical raw string on both sides
      normalized_case_matches  - equal only after normalize_identifier()
                                  (e.g. casing/whitespace differences)
      alias_candidates         - equal only after series_skeleton()
                                  (e.g. 'Freshwater Strategy' vs
                                  'FreshwaterStrategy') - flagged for
                                  human review, NEVER auto-merged
      unmatched_master         - in master_counts, no match found in EAD
      unmatched_ead            - in ead_counts, no match found in master
    """
    master_set = set(master_counts)
    ead_set = set(ead_counts)

    exact = sorted(master_set & ead_set)
    exact_matches = [
        {"series": s, "master_rows": master_counts[s], "ead_rows": ead_counts[s]}
        for s in exact
    ]

    master_only = master_set - set(exact)
    ead_only = ead_set - set(exact)

    normalized_case_matches = []
    matched_master, matched_ead = set(), set()
    for m in sorted(master_only):
        for e in sorted(ead_only):
            if e in matched_ead:
                continue
            if normalize_identifier(m) == normalize_identifier(e):
                normalized_case_matches.append({
                    "master": m, "ead": e,
                    "master_rows": master_counts[m], "ead_rows": ead_counts[e],
                })
                matched_master.add(m)
                matched_ead.add(e)
                break

    remaining_master = master_only - matched_master
    remaining_ead = ead_only - matched_ead

    # Alias/formatting-variant candidates: for each remaining master-only
    # (or ead-only) series, check whether its alnum skeleton coincides
    # with ANY series on the other side - including one already claimed
    # by an exact or normalized-case match elsewhere. This matters
    # because a Master-only spelling variant (e.g. 'Freshwater Strategy')
    # can coexist with an EAD entry (e.g. 'FreshwaterStrategy') that
    # already exact-matched a DIFFERENT Master row spelled the same way
    # as the EAD entry - the alias signal is still real and worth
    # surfacing even though that EAD series isn't "free" anymore. This
    # is purely an additional, non-exclusive cross-reference for human
    # review: it never removes a series from unmatched_master/
    # unmatched_ead below, and never merges/rewrites anything.
    alias_candidates = []
    for m in sorted(remaining_master):
        skm = series_skeleton(m)
        if not skm:
            continue
        for e in sorted(ead_set):
            if series_skeleton(e) == skm:
                alias_candidates.append({
                    "master": m, "ead": e,
                    "master_rows": master_counts[m], "ead_rows": ead_counts[e],
                })
                break
    already_ead_in_alias = {a["ead"] for a in alias_candidates}
    for e in sorted(remaining_ead):
        if e in already_ead_in_alias:
            continue
        ske = series_skeleton(e)
        if not ske:
            continue
        for m in sorted(master_set):
            if series_skeleton(m) == ske:
                alias_candidates.append({
                    "master": m, "ead": e,
                    "master_rows": master_counts[m], "ead_rows": ead_counts[e],
                })
                break

    unmatched_master = sorted(remaining_master, key=str)
    unmatched_ead = sorted(remaining_ead, key=str)

    return {
        "exact_matches": exact_matches,
        "normalized_case_matches": normalized_case_matches,
        "alias_candidates": alias_candidates,
        "unmatched_master": [{"series": s, "master_rows": master_counts[s]} for s in unmatched_master],
        "unmatched_ead": [{"series": s, "ead_rows": ead_counts[s]} for s in unmatched_ead],
        "note": "Alias/formatting-variant candidates are reported for human review only - never auto-merged.",
    }


def reference_index_contains_country(index_path, country_norm):
    """Read-only check: does ANY table in the duckdb index at index_path
    have a 'Country' column with at least one value that normalizes
    (via normalize_identifier) to country_norm?

    Used by check_assignment_preflight.py so a reference index that
    merely EXISTS but was built for a different country (or an
    unrelated workspace) is never silently treated as safe reference
    data for THIS country - the exact "stale index" gap a fresh
    student/instructor workspace could otherwise hit. Never raises: a
    missing, corrupt, or unreadable index is treated as NOT covering the
    country (fail closed), never as implicitly safe."""
    if not index_path or not os.path.isfile(index_path):
        return False
    try:
        import duckdb
    except ImportError:
        return False
    try:
        con = duckdb.connect(index_path, read_only=True)
    except Exception:
        return False
    try:
        try:
            tables = [
                r[0] for r in con.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name != '_index_metadata'"
                ).fetchall()
            ]
        except Exception:
            return False
        for table in tables:
            try:
                columns = [r[0] for r in con.execute(f'DESCRIBE "{table}"').fetchall()]
            except Exception:
                continue
            if "Country" not in columns:
                continue
            try:
                values = con.execute(f'SELECT DISTINCT "Country" FROM "{table}"').fetchall()
            except Exception:
                continue
            for (v,) in values:
                if normalize_identifier(v) == country_norm:
                    return True
        return False
    finally:
        con.close()
