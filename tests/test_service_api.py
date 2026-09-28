"""Tests 1-6 and 13 from the remote-deployment task: the FastAPI service
itself. The real Claude Agent SDK is never called here - service.agent.query
is monkeypatched to a synthetic message stream, so these tests never reach
the live Anthropic API and never touch real Pollitik data (see
tests/conftest.py for the CLAUDE_PROJECT_DIR/job-store isolation this
relies on).
"""

import time

from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, ToolUseBlock
from fastapi.testclient import TestClient

from .conftest import AUTH_HEADERS, SESSION_SANDBOX, run_script
from service.app import app


# --- Test 1: health endpoint -----------------------------------------------

def test_health_endpoint_ok_and_unauthenticated():
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("ok", "degraded")
    assert "checks" in body and "warnings" in body


# --- Test 2: authentication rejection ---------------------------------------

def test_missing_token_rejected():
    with TestClient(app) as client:
        resp = client.post("/jobs", json={"task": "Research something"})
    assert resp.status_code == 401


def test_wrong_token_rejected():
    with TestClient(app) as client:
        resp = client.post(
            "/jobs",
            json={"task": "Research something"},
            headers={"Authorization": "Bearer not-the-real-token"},
        )
    assert resp.status_code == 401


# --- Test 3: create-job ------------------------------------------------------

def test_create_job():
    with TestClient(app) as client:
        resp = client.post("/jobs", json={"task": "Research X for Y"}, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "pending"
    assert body["task"] == "Research X for Y"
    assert "job_id" in body and body["job_id"]


# --- Test 5: production-write defaults to false -----------------------------

def test_allow_production_write_defaults_false():
    with TestClient(app) as client:
        resp = client.post("/jobs", json={"task": "Research X"}, headers=AUTH_HEADERS)
    assert resp.json()["allow_production_write"] is False


# --- Test 6: unauthorized production-write attempt fails --------------------

def test_approve_write_without_token_fails():
    with TestClient(app) as client:
        create = client.post("/jobs", json={"task": "Research X"}, headers=AUTH_HEADERS)
        job_id = create.json()["job_id"]
        resp = client.post(f"/jobs/{job_id}/approve-write")
    assert resp.status_code == 401


def test_approve_write_blocked_when_job_did_not_opt_in():
    with TestClient(app) as client:
        create = client.post(
            "/jobs",
            json={"task": "Research X", "allow_production_write": False},
            headers=AUTH_HEADERS,
        )
        job_id = create.json()["job_id"]
        resp = client.post(f"/jobs/{job_id}/approve-write", headers=AUTH_HEADERS)
    assert resp.status_code == 403


# --- Test 4 & 13: structured job result + mocked delegation through phases -

async def _fake_query(*, prompt, options):
    yield SystemMessage(subtype="init", data={})
    yield AssistantMessage(
        content=[ToolUseBlock(id="t1", name="Task", input={"subagent_type": "researcher", "prompt": prompt})],
        model="claude-test",
    )
    yield AssistantMessage(
        content=[ToolUseBlock(id="t2", name="Task", input={"subagent_type": "validator", "prompt": "stage findings"})],
        model="claude-test",
    )
    yield ResultMessage(
        subtype="success",
        duration_ms=50,
        duration_api_ms=40,
        is_error=False,
        num_turns=3,
        session_id="test-session",
        result="done",
        structured_output={
            "status": "completed",
            "task_type": "research_missing_observations",
            "countries_researched": ["TestCountry"],
            "sources_fetched": 1,
            "source_failures": 0,
            "observations_found": 1,
            # Deliberately wrong self-reported counts - the service must
            # override these from data/staging/candidates.jsonl, not trust them.
            "approved": 999,
            "review": 999,
            "summary": "Researched TestCountry and delegated staging to the validator.",
        },
    )


def _stage_synthetic_record_for_job(job_id: str) -> str:
    record = {
        "country": "TestCountry",
        "series": "Job Approval",
        "pollster": "Test Pollster",
        "question_wording_status": "EXACT_WORDING",
        "positive": 58,
        "negative": 36,
        "response_categories": {"Very poorly": 14, "Poorly": 22, "Well": 40, "Very well": 18},
        "category_classification": {
            "Very poorly": "negative",
            "Poorly": "negative",
            "Well": "positive",
            "Very well": "positive",
        },
        "sample_size": 1204,
        "fieldwork_date_normalized": "1/8/2026",
        "fieldwork_date_status": "OBSERVED",
        "requested_url": "https://approved-pollster.example/report",
        "final_url": "https://approved-pollster.example/report",
        "http_status": 200,
        "retrieved_at": "2026-08-12T14:03:00Z",
        "evidence_text": "Very poorly 14, Poorly 22, Well 40, Very well 18.",
    }
    import json

    proc = run_script(
        "stage_changes.py",
        SESSION_SANDBOX,
        input_json=record,
        extra_env={"POLLITIK_JOB_ID": job_id},
    )
    staged = json.loads(proc.stdout)
    assert staged["validation_status"] == "APPROVED"
    assert staged["job_id"] == job_id
    return staged["record_id"]


def test_manager_delegates_through_phases_and_result_is_structured(monkeypatch):
    import service.agent as agent_module

    monkeypatch.setattr(agent_module, "query", _fake_query)

    with TestClient(app) as client:
        create = client.post(
            "/jobs",
            json={"task": "Research missing approval observations for TestCountry"},
            headers=AUTH_HEADERS,
        )
        job_id = create.json()["job_id"]

        expected_record_id = _stage_synthetic_record_for_job(job_id)

        run_resp = client.post(f"/jobs/{job_id}/run", headers=AUTH_HEADERS)
        assert run_resp.status_code == 200
        assert run_resp.json()["state"] == "running"

        deadline = time.time() + 10
        job = None
        while time.time() < deadline:
            job = client.get(f"/jobs/{job_id}", headers=AUTH_HEADERS).json()
            if job["state"] in ("completed", "failed"):
                break
            time.sleep(0.1)

    assert job is not None, "job did not finish in time"
    assert job["state"] == "completed", job
    result = job["result"]

    # Structured, not free-form text.
    assert isinstance(result, dict)
    assert result["status"] == "completed"
    assert result["countries_researched"] == ["TestCountry"]

    # Deterministic override took effect: the LLM's self-reported
    # approved=999/review=999 must NOT survive.
    assert result["approved"] == 1
    assert result["review"] == 0
    assert result["staging_record_ids"] == [expected_record_id]

    # Usage/cost observability: two AssistantMessages (researcher +
    # validator Task calls) were yielded, both were Task delegations.
    usage = job["usage"]
    assert usage["num_model_calls"] == 2
    assert usage["num_subagent_calls"] == 2
