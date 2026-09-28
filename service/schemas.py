"""Pydantic request/response/result models for the Pollitik Manager API.

Structured results, not free-form Claude text - see StructuredJobResult.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    # Set on startup for any job found RUNNING in the store, since a
    # process restart means we genuinely do not know whether it finished.
    # See job_store.py.
    INTERRUPTED = "interrupted"


class JobCreateRequest(BaseModel):
    task: str = Field(..., min_length=1, description="High-level Pollitik task description.")
    allow_production_write: bool = Field(
        default=False,
        description=(
            "Job-level intent to eventually write approved observations to "
            "production. This is Gate 2 of the two-gate write model and "
            "defaults to false. Setting it true here does NOT itself write "
            "anything - it only records intent; the actual write still "
            "requires a separate POST /jobs/{job_id}/approve-write call, "
            "which re-validates every record from scratch regardless of "
            "this flag (Gate 1: validation_status == APPROVED, re-derived "
            "at write time, every time)."
        ),
    )


class StructuredJobResult(BaseModel):
    """Adapted from the Pollitik Skill's final-report fields (section 41)
    and the deterministic staging/validation vocabulary the pipeline
    already uses (APPROVED/REVIEW/REJECTED/NOT_FOUND)."""

    status: str = Field(description='"completed", "failed", or "partial"')
    task_type: str | None = None

    countries_researched: list[str] = Field(default_factory=list)
    executives_researched: list[str] = Field(default_factory=list)
    pollsters_found: list[str] = Field(default_factory=list)
    languages_encountered: list[str] = Field(default_factory=list)

    sources_fetched: int = 0
    source_failures: int = 0
    observations_found: int = 0

    # These four counts are RECOMPUTED DETERMINISTICALLY by the service from
    # data/staging/candidates.jsonl records tagged with this job's id (see
    # pollitik_common.read_staged_records_for_job) - not trusted from the
    # orchestrating agent's own self-report. See agent.py.
    approved: int = 0
    review: int = 0
    rejected: int = 0
    not_found: int = 0

    duplicates_skipped: int = 0
    staging_record_ids: list[str] = Field(default_factory=list)
    figures: list[str] = Field(default_factory=list)

    production_write_requested: bool = False
    production_write_performed: bool = False

    unresolved_country_mappings: list[str] = Field(default_factory=list)
    unresolved_series_mappings: list[str] = Field(default_factory=list)

    summary: str = ""


class JobUsage(BaseModel):
    """Token/cost observability (token-efficiency requirement #21).

    model/input_tokens/output_tokens/total_cost_usd/num_model_calls come
    straight from the SDK's own ResultMessage - real API telemetry, not
    an LLM self-report, so it's trusted directly (unlike
    StructuredJobResult's approved/review/rejected/not_found, which are
    deliberately NOT trusted from the agent and are recomputed from
    data/staging/candidates.jsonl instead). num_subagent_calls is a live
    count of Task tool_use events seen in the message stream.
    cache_hits/cache_misses/source_fetch_count are recomputed the same
    deterministic way as the staging counts: by tallying this job's
    entries in logs/research/cache_access.jsonl, not by asking the agent.
    """

    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_cost_usd: float | None = None
    num_model_calls: int = 0
    num_subagent_calls: int = 0
    source_fetch_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0


class WriteAttempt(BaseModel):
    record_id: str
    error: str | None = None
    workbook_path: str | None = None
    backup_path: str | None = None
    row_number: int | None = None
    verified_after_save: bool | None = None
    applied_at: str | None = None


class ApproveWriteResult(BaseModel):
    requested_record_ids: list[str]
    attempts: list[WriteAttempt]
    succeeded: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)


class JobRecord(BaseModel):
    job_id: str
    state: JobState
    task: str
    allow_production_write: bool
    created_at: str
    updated_at: str
    result: StructuredJobResult | None = None
    usage: JobUsage | None = None
    errors: list[str] = Field(default_factory=list)
    write_approvals: list[ApproveWriteResult] = Field(default_factory=list)

    def public_summary(self) -> dict[str, Any]:
        """What GET /jobs/{job_id} returns - explicitly excludes anything
        that isn't already part of this model (no secrets are ever stored
        on a job record in the first place, see job_store.py)."""
        return self.model_dump()
