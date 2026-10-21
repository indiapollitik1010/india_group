"""MVP job storage: one JSON file per job under service/config.JOB_STORE_DIR.

Deliberately simple per the project owner's instruction not to
overengineer the first version. Replace with PostgreSQL/Redis for a
multi-worker deployment - see docs/REMOTE_DEPLOYMENT.md for what that
migration needs.

Restart behavior (documented, not just implied): this store persists each
job's last-written state to disk, so job records themselves survive a
restart. What does NOT survive a restart is the in-process asyncio task
actually running a job's SDK query - if the service process dies while a
job is RUNNING, nothing marks it COMPLETED or FAILED on its own. On the
next startup, JobStore.recover_on_startup() finds every job still marked
RUNNING and moves it to INTERRUPTED, with a note in its errors list,
rather than leaving a stale "running" status that will never change.
INTERRUPTED jobs may have partially staged candidates in
data/staging/candidates.jsonl (staging is append-only and safe); they are
never silently retried or resumed.
"""

import asyncio
import datetime
from pathlib import Path

from .schemas import JobRecord, JobState


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class JobStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _path(self, job_id: str) -> Path:
        return self.directory / f"{job_id}.json"

    def _write(self, job: JobRecord) -> None:
        path = self._path(job.job_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)  # atomic rename on POSIX filesystems

    def _read(self, job_id: str) -> JobRecord | None:
        path = self._path(job_id)
        if not path.exists():
            return None
        return JobRecord.model_validate_json(path.read_text(encoding="utf-8"))

    async def create(self, job: JobRecord) -> None:
        async with self._lock:
            self._write(job)

    async def get(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            return self._read(job_id)

    async def save(self, job: JobRecord) -> None:
        job.updated_at = _now_iso()
        async with self._lock:
            self._write(job)

    async def list_ids(self) -> list[str]:
        async with self._lock:
            return sorted(p.stem for p in self.directory.glob("*.json"))

    def recover_on_startup(self) -> list[str]:
        """Synchronous by design - runs once at process startup, before
        the event loop is serving requests. Returns the ids of jobs moved
        to INTERRUPTED."""
        recovered = []
        for path in self.directory.glob("*.json"):
            try:
                job = JobRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if job.state == JobState.RUNNING:
                job.state = JobState.INTERRUPTED
                job.errors.append(
                    "Service restarted while this job was RUNNING; its "
                    "final outcome is unknown. Any records it staged "
                    "before the restart remain in data/staging/candidates.jsonl."
                )
                job.updated_at = _now_iso()
                self._write(job)
                recovered.append(job.job_id)
        return recovered
