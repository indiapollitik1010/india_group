"""Tests for the token-efficiency additions: the DuckDB reference index/
lookup and the source-retrieval cache. Real subprocess invocations
against isolated sandbox directories - no real Pollitik data touched."""

import json

import openpyxl

from .conftest import run_script


def make_fixture_workbook(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Observations"
    ws.append(["Country", "Series", "Pollster", "Question Wording English", "Positive", "Negative", "Fieldwork End Date"])
    ws.append(["TestCountry", "Job Approval", "Test Pollster", "Do you approve of X handling their job?", 58, 36, "1/8/2026"])
    ws.append(["TestCountry", "Job Approval", "Test Pollster", "Do you approve of X handling their job?", 55, 40, "2/2/2026"])
    ws.append(["TestCountry", "Favorability", "Other Pollster", "Do you have a favorable opinion of X?", 50, 45, "1/15/2026"])
    ws.append(["OtherCountry", "Job Approval", "Third Pollster", "Do you approve of Y handling their job?", 62, 30, "1/10/2026"])
    wb.save(path)


def make_fixture_workbook_mixed_date_text(path, num_rows=3000, bad_row_index=2500):
    import datetime

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Observations"
    ws.append(["Country", "Series", "Pollster", "Fieldwork End Date"])
    # A stray text value in an otherwise-all-datetime column (e.g. a
    # transcription artifact combining two fieldwork dates) makes pandas
    # parse the column as mixed-type object dtype. DuckDB's vectorized
    # pandas scan infers TIMESTAMP from the first batch of rows, so the
    # column needs enough leading real dates (> one vector's worth) before
    # the stray text row to actually trigger the cast failure that this
    # fix guards against - a handful of rows isn't enough to reproduce it.
    for i in range(num_rows):
        if i == bad_row_index:
            value = "5/19/2023 + 7/9/2023"
        else:
            value = datetime.datetime(2023, 1, 1) + datetime.timedelta(days=i)
        ws.append(["TestCountry", "Job Approval", "Test Pollster", value])
    wb.save(path)


def test_build_reference_index_reports_cleanly_with_no_workbook(sandbox):
    proc = run_script("build_reference_index.py", sandbox)
    result = json.loads(proc.stdout)
    assert result["built"] is False
    assert not (sandbox / "data" / "reference_index.duckdb").exists()


def test_reference_lookup_reports_cleanly_with_no_index(sandbox):
    proc = run_script("reference_lookup.py", sandbox)
    result = json.loads(proc.stdout)
    assert result["found_index"] is False
    assert result["rows"] == []


def test_build_and_query_reference_index(sandbox):
    workbook = sandbox / "data" / "master" / "pollitik_master.xlsx"
    make_fixture_workbook(workbook)

    build_proc = run_script("build_reference_index.py", sandbox, args=["--workbook", str(workbook)])
    built = json.loads(build_proc.stdout)
    assert built["built"] is True
    assert built["tables"][0]["rows"] == 4

    lookup_proc = run_script(
        "reference_lookup.py", sandbox,
        args=["--country", "TestCountry", "--series", "Job Approval"],
    )
    result = json.loads(lookup_proc.stdout)
    assert result["found_index"] is True
    assert result["row_count_returned"] == 2
    assert result["unmapped_filters"] == []

    # Date-range filter, m/d/yyyy convention (Skill section 19) - this is
    # the exact case that initially returned 0 rows due to DuckDB's
    # default TRY_CAST expecting ISO dates.
    date_proc = run_script(
        "reference_lookup.py", sandbox,
        args=["--date-from", "1/1/2026", "--date-to", "1/31/2026"],
    )
    date_result = json.loads(date_proc.stdout)
    assert date_result["row_count_returned"] == 3

    # Unmapped filter is reported, not silently dropped or misapplied.
    unmapped_proc = run_script("reference_lookup.py", sandbox, args=["--executive-type", "president"])
    unmapped_result = json.loads(unmapped_proc.stdout)
    assert "executive_type" in unmapped_result["unmapped_filters"]
    assert unmapped_result["row_count_returned"] == 4  # unmapped filter ignored, not applied wrongly


def test_build_reference_index_handles_mixed_datetime_and_text_column(sandbox):
    # Regression test: a column that's mostly real datetimes but has one
    # stray text value (e.g. "5/19/2023 + 7/9/2023") makes pandas parse
    # it as an object column mixing Timestamp and str values. DuckDB's
    # pandas-to-Arrow ingestion can't infer a single Arrow type for that
    # mix and used to raise, so build() must normalize object columns to
    # strings first (see build_reference_index.build).
    workbook = sandbox / "data" / "master" / "pollitik_master.xlsx"
    make_fixture_workbook_mixed_date_text(workbook)

    build_proc = run_script("build_reference_index.py", sandbox, args=["--workbook", str(workbook)])
    assert build_proc.returncode == 0, build_proc.stderr
    result = json.loads(build_proc.stdout)
    assert result["built"] is True
    assert result["tables"][0]["rows"] == 3000


def make_fixture_csv_snapshot(path):
    """A minimal stand-in for a country reference-snapshot CSV (e.g.
    countries/canada/data/canada_reference_snapshot.csv) - the exact 8
    columns the real snapshot ships, one country only."""
    path.write_text(
        "Series,Date,Total Count,Positive,Neutral,Negative,Source,Country\n"
        "LIAISON,3/21/2026,1000,64,,32,https://example.test/liaison-1,TestCountry\n"
        "LIAISON,5/2/2026,,60,,32,https://example.test/liaison-2,TestCountry\n"
        "LEGER,10/5/2025,1592,47,,41,https://example.test/leger-1,TestCountry\n",
        encoding="utf-8",
    )


def test_build_reference_index_from_csv_snapshot(sandbox):
    """CSV input (the new snapshot-build path) produces a valid DuckDB
    index without ever touching an Excel workbook - regression coverage
    for the country-reference-snapshot architecture."""
    snapshot = sandbox / "countries_canada_reference_snapshot.csv"
    make_fixture_csv_snapshot(snapshot)

    index_path = sandbox / "data" / "reference_index.duckdb"
    build_proc = run_script(
        "build_reference_index.py", sandbox,
        args=["--workbook", str(snapshot), "--index", str(index_path)],
    )
    assert build_proc.returncode == 0, build_proc.stderr
    built = json.loads(build_proc.stdout)
    assert built["built"] is True
    assert built["source_kind"] == "csv"
    assert built["tables"][0]["rows"] == 3
    assert built["tables"][0]["columns"] == [
        "Series", "Date", "Total Count", "Positive", "Neutral", "Negative", "Source", "Country",
    ]
    assert index_path.exists()


def test_reference_lookup_queries_csv_built_index(sandbox):
    """reference_lookup.py must work identically against a CSV-built
    index as against an Excel-built one - same query interface, no
    special-casing needed by callers."""
    snapshot = sandbox / "countries_canada_reference_snapshot.csv"
    make_fixture_csv_snapshot(snapshot)
    index_path = sandbox / "data" / "reference_index.duckdb"
    run_script("build_reference_index.py", sandbox, args=["--workbook", str(snapshot), "--index", str(index_path)])

    lookup_proc = run_script(
        "reference_lookup.py", sandbox,
        args=["--index", str(index_path), "--country", "TestCountry", "--series", "LIAISON"],
    )
    result = json.loads(lookup_proc.stdout)
    assert result["found_index"] is True
    assert result["row_count_returned"] == 2
    assert all(r["Series"] == "LIAISON" for r in result["rows"])

    date_proc = run_script(
        "reference_lookup.py", sandbox,
        args=["--index", str(index_path), "--date-from", "1/1/2025", "--date-to", "12/31/2025"],
    )
    date_result = json.loads(date_proc.stdout)
    assert date_result["row_count_returned"] == 1
    assert date_result["rows"][0]["Series"] == "LEGER"


def test_build_reference_index_rejects_sheet_arg_for_csv(sandbox):
    """--sheet only means something for an Excel workbook - passing it
    with a CSV input must fail clearly, never silently ignore it."""
    snapshot = sandbox / "countries_canada_reference_snapshot.csv"
    make_fixture_csv_snapshot(snapshot)
    index_path = sandbox / "data" / "reference_index.duckdb"

    proc = run_script(
        "build_reference_index.py", sandbox,
        args=["--workbook", str(snapshot), "--index", str(index_path), "--sheet", "Master"],
    )
    result = json.loads(proc.stdout)
    assert result["built"] is False
    assert "csv" in result["message"].lower()
    assert not index_path.exists()


def test_build_reference_index_excel_path_still_works_after_csv_support_added(sandbox):
    """Regression guard: adding CSV support must not change a single
    thing about the pre-existing Excel-workbook build path."""
    workbook = sandbox / "data" / "master" / "pollitik_master.xlsx"
    make_fixture_workbook(workbook)

    build_proc = run_script("build_reference_index.py", sandbox, args=["--workbook", str(workbook)])
    built = json.loads(build_proc.stdout)
    assert built["built"] is True
    assert built["source_kind"] == "workbook"
    assert built["tables"][0]["rows"] == 4

    lookup_proc = run_script(
        "reference_lookup.py", sandbox,
        args=["--country", "TestCountry", "--series", "Job Approval"],
    )
    result = json.loads(lookup_proc.stdout)
    assert result["found_index"] is True
    assert result["row_count_returned"] == 2


def test_source_cache_store_then_hit_then_miss(sandbox):
    record = {
        "requested_url": "https://approved-pollster.example/report-1",
        "final_url": "https://approved-pollster.example/report-1",
        "http_status": 200,
        "retrieved_at": "2026-08-12T14:03:00Z",
        "evidence_text": "56% approve, 38% disapprove.",
        "title": "Report 1",
    }
    store_proc = run_script("source_cache.py", sandbox, args=["store"], input_json=record, extra_env={"POLLITIK_JOB_ID": "cache-test-job"})
    stored = json.loads(store_proc.stdout)
    assert stored["final_url"] == record["final_url"]
    assert len(stored["content_hash"]) == 64  # sha256 hex digest

    hit_proc = run_script(
        "source_cache.py", sandbox,
        args=["lookup", "--url", "https://approved-pollster.example/report-1"],
        extra_env={"POLLITIK_JOB_ID": "cache-test-job"},
    )
    hit = json.loads(hit_proc.stdout)
    assert hit["cache_hit"] is True
    assert hit["entry"]["evidence_text"] == record["evidence_text"]

    miss_proc = run_script(
        "source_cache.py", sandbox,
        args=["lookup", "--url", "https://approved-pollster.example/never-fetched"],
        extra_env={"POLLITIK_JOB_ID": "cache-test-job"},
    )
    miss = json.loads(miss_proc.stdout)
    assert miss["cache_hit"] is False

    access_log = sandbox / "logs" / "research" / "cache_access.jsonl"
    lines = [json.loads(line) for line in access_log.read_text().splitlines() if line.strip()]
    hits = [entry for entry in lines if entry["job_id"] == "cache-test-job" and entry["hit"]]
    misses = [entry for entry in lines if entry["job_id"] == "cache-test-job" and not entry["hit"]]
    assert len(hits) == 1
    assert len(misses) == 1
