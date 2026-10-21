"""FastAPI application for the Pollitik Manager remote service.

Run locally with:
    uvicorn service.app:app --host 0.0.0.0 --port 8000

See docs/REMOTE_DEPLOYMENT.md for environment variables, Docker, and the
full write-authorization model this API enforces.
"""

import asyncio
import datetime
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from . import agent, config, health
from .job_store import JobStore
from .schemas import JobCreateRequest, JobRecord, JobState
from .security import require_api_token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pollitik.service")

store = JobStore(config.JOB_STORE_DIR)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@asynccontextmanager
async def lifespan(app: FastAPI):
    recovered = store.recover_on_startup()
    if recovered:
        logger.warning("Recovered %d job(s) left RUNNING by a prior process into INTERRUPTED: %s", len(recovered), recovered)
    checks = health.run_checks()
    logger.info("Startup health: status=%s warnings=%s", checks["status"], checks["warnings"])
    yield


app = FastAPI(
    title="Pollitik Manager Service",
    description=(
        "Remote job API for the Pollitik Database research pipeline. "
        "MVP: single process, file-backed job store. See "
        "docs/REMOTE_DEPLOYMENT.md before deploying beyond local/dev use."
    ),
    lifespan=lifespan,
)


@app.get("/health")
async def get_health() -> dict:
    return health.run_checks()


@app.post("/jobs", dependencies=[Depends(require_api_token)])
async def create_job(payload: JobCreateRequest) -> JobRecord:
    now = _now_iso()
    job = JobRecord(
        job_id=agent.new_job_id(),
        state=JobState.PENDING,
        task=payload.task,
        allow_production_write=payload.allow_production_write,
        created_at=now,
        updated_at=now,
    )
    await store.create(job)
    logger.info("Job created: %s", job.job_id)
    return job


@app.get("/jobs/{job_id}", dependencies=[Depends(require_api_token)])
async def get_job(job_id: str) -> JobRecord:
    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.post("/jobs/{job_id}/run", dependencies=[Depends(require_api_token)])
async def run_job_endpoint(job_id: str) -> JobRecord:
    """Starts execution in the background and returns immediately with
    state=RUNNING. Poll GET /jobs/{job_id} for progress/result - the HTTP
    connection here is not held open for the duration of the job (Pollitik
    research jobs can run long). See docs/REMOTE_DEPLOYMENT.md for the
    single-process caveat this implies."""
    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.state == JobState.RUNNING:
        raise HTTPException(status_code=409, detail="job is already running")

    job.state = JobState.RUNNING
    job.errors = []
    await store.save(job)

    asyncio.create_task(_execute_job(job_id))
    return job


async def _execute_job(job_id: str) -> None:
    job = await store.get(job_id)
    if job is None:
        return
    try:
        result, usage = await agent.run_job(job)
        job.result = result
        job.usage = usage
        job.state = JobState.FAILED if result.status == "failed" else JobState.COMPLETED
    except agent.ManagerRunError as exc:
        logger.error("Job %s failed: %s", job_id, exc)
        job.errors.append(str(exc))
        job.state = JobState.FAILED
    except Exception as exc:  # noqa: BLE001 - a job must always resolve, never hang
        logger.exception("Job %s failed unexpectedly", job_id)
        job.errors.append(f"unexpected error: {exc}")
        job.state = JobState.FAILED
    await store.save(job)


class ApproveWriteRequest(BaseModel):
    record_ids: list[str] | None = None


@app.post("/jobs/{job_id}/approve-write", dependencies=[Depends(require_api_token)])
async def approve_write_endpoint(job_id: str, payload: ApproveWriteRequest | None = None) -> JobRecord:
    """The only endpoint that can cause a production write, and even then
    only through python/apply_changes.py - never through the LLM.

    Two independent gates are enforced here, both required (the stricter
    reading of the project's "two independent gates" requirement - see
    docs/REMOTE_DEPLOYMENT.md for why the looser OR reading was not used):

    1. This job must have been created with allow_production_write=true
       (job-level intent, set once at creation and immutable afterward in
       this MVP).
    2. This exact endpoint must be called (with a valid API token) - that
       call is the "explicit approved-write API action" itself.

    Even with both gates satisfied, every record still goes through
    apply_changes.py's own from-scratch re-validation, backup, and
    post-save verification. Only records that re-validate to APPROVED at
    write time are ever written; nothing here trusts a stale status.
    """
    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    if not job.allow_production_write:
        raise HTTPException(
            status_code=403,
            detail=(
                "This job was created with allow_production_write=false. "
                "Production writes were never authorized for it. Create a "
                "new job with allow_production_write=true if you intend to "
                "write its results to production."
            ),
        )

    if job.state != JobState.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"job must be COMPLETED before approving writes (current state: {job.state.value})",
        )

    record_ids = payload.record_ids if payload else None
    result = await agent.approve_write(job, record_ids)
    job.write_approvals.append(result)
    await store.save(job)
    return job
