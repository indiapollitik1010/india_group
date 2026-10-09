# Pollitik Manager - Remote Deployment

This document covers the `service/` layer: a FastAPI job API that exposes
the existing local Pollitik research pipeline (Skill, hook, seven
subagents, deterministic `python/` scripts) remotely via the Claude Agent
SDK. Read `README.md` first for the pipeline itself; this document is
about running it as a service.

## 0. Verified Claude Agent SDK facts this design relies on

Everything below was verified against the actually-installed
`claude-agent-sdk` package (version 0.2.137 at the time this was written -
`pip show claude-agent-sdk` for the version you have), by downloading the
real wheel and reading its source directly, not by trusting secondary
sources. `service/agent.py`'s module docstring has the short version;
this is the long version.

- **Package**: `pip install claude-agent-sdk` (PyPI), imported as
  `claude_agent_sdk`. Requires Python >= 3.10. The old `claude-code-sdk`
  name is superseded by this package.
- **It bundles a real, native `claude` CLI binary** inside the wheel
  (`claude_agent_sdk/_bundled/claude`, ~85-95MB depending on platform -
  pip fetches the correct platform-specific wheel automatically, which is
  why the Dockerfile does a plain `pip install` inside the Linux build
  context rather than trying to vendor a binary itself). This means the
  SDK is not a reimplementation - it shells out to the same CLI that
  interactive `claude` sessions use, over a JSON control protocol on
  stdio.
- **`ClaudeAgentOptions.setting_sources`** (`claude_agent_sdk/types.py`):
  its own docstring reads: *"When `None`, all sources are loaded (matches
  CLI defaults). Pass `[]` to disable filesystem settings (SDK isolation
  mode). Must include `"project"` to load CLAUDE.md files."* So the
  default is **not** isolation - omitting this field would load the
  deploying host's `~/.claude/settings.json` too. `service/agent.py`
  explicitly passes `setting_sources=["project"]` so a session only ever
  loads *this repository's* `.claude/settings.json` (and therefore
  `.claude/hooks/pollitik_guard.py`), `CLAUDE.md`, `.claude/agents/*.md`,
  and `.claude/skills/` - never the host's user-level settings, and never
  this repo's own dev-only `.claude/settings.local.json`.
- **Hooks fire unconditionally.** `ClaudeAgentOptions.can_use_tool`'s
  docstring: *"To observe or gate *every* tool call regardless of
  permission rules, use a `PreToolUse` hook ... instead."* Combined with
  the bundled-binary point above, this means
  `.claude/hooks/pollitik_guard.py` runs for every Bash/Write/Edit/
  WebFetch call a remote session makes, exactly as it does interactively,
  regardless of `permission_mode`.
- **`.claude/agents/*.md` become invocable via the `Task` tool** once
  `setting_sources` includes `"project"` - no separate registration is
  needed in `service/agent.py`. (`ClaudeAgentOptions.agents` also exists,
  for *programmatically* defining additional subagents; unused here since
  the seven agents already exist as files.)
- **`permission_mode`** (`claude_agent_sdk/types.py`): one of `"default"`,
  `"acceptEdits"`, `"plan"`, `"bypassPermissions"`, `"dontAsk"`, `"auto"`.
  `"default"` and most others can synchronously prompt for a decision,
  which has nothing to answer it in a headless server (`query()`'s own
  docstring lists "Automated scripts and CI/CD pipelines" as the reason
  to prefer `query()` over the interactive client). `service/agent.py`
  uses `"bypassPermissions"` for the manager session. This is safe
  specifically *because* hooks fire unconditionally (previous bullet) and
  each subagent's own tool list is independently scoped by its
  `.claude/agents/<name>.md` `tools:` frontmatter - `bypassPermissions`
  only removes an *additional*, redundant prompt layer, not the hook or
  the per-agent tool scoping. `"dontAsk"` (deny anything not
  pre-approved) is a stricter alternative if you want defense-in-depth
  beyond the hook, at the cost of maintaining an explicit `allowed_tools`
  list per phase - see "Explicit decisions before real deployment" below.
- **Structured output**: `ClaudeAgentOptions.output_format =
  {"type": "json_schema", "schema": {...}}` makes the final
  `ResultMessage.structured_output` a schema-validated dict instead of
  free text. `service/agent.py` uses this for `StructuredJobResult`
  instead of parsing prose.
- **Authentication env vars**, confirmed by grep of the installed
  package's `_internal/session_resume.py`: `ANTHROPIC_API_KEY` and
  `CLAUDE_CODE_OAUTH_TOKEN`. The SDK reads these directly from the
  process environment; this service never reads or forwards the value
  itself (`service/config.py` only checks *presence*). **Empirically
  confirmed during this project's own local verification**: with neither
  env var set, a job still ran for real and started delegating, because
  the bundled `claude` binary fell back to an already-authenticated
  `claude login` session already present on that machine (credentials
  stored outside the process environment - keychain/`~/.claude/`, the
  same store the interactive CLI and desktop app use). That fallback is
  real but not something to depend on for a deployed service: a fresh
  container has no such ambient login state, so `ANTHROPIC_API_KEY` or
  `CLAUDE_CODE_OAUTH_TOKEN` is effectively mandatory there. Do not assume
  a container is "unauthenticated and therefore safe to test against"
  just because you didn't set either variable - if the *build* environment
  or a mounted volume happens to carry credential files, the same
  fallback could apply. Section 15 (secret rotation) and the container
  image build both assume no such ambient state is present or desired.
- **Unverified / deliberately not relied upon**: whether
  *programmatically* passed `ClaudeAgentOptions.hooks` callbacks
  additively layer with or could ever shadow the filesystem-loaded
  `.claude/settings.json` hooks. The merge logic for that lives inside
  the closed-source CLI binary, not in the Python package. This is *why*
  production writes never go through the LLM at all - see section 10.

## 1. Local development

Requires Python >= 3.10 (this repo was verified against 3.12; the system
default `python3` on the dev machine used to build this was 3.9, which
is too old for `claude-agent-sdk` - use `python3.10`+ explicitly if your
`python3` is older).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in real values - .env is gitignored
```

Run the API:

```bash
uvicorn service.app:app --host 0.0.0.0 --port 8000
```

`GET http://localhost:8000/health` should report `"status": "ok"` (plus
warnings if `ANTHROPIC_API_KEY`/`CLAUDE_CODE_OAUTH_TOKEN` or
`POLLITIK_API_TOKEN` aren't set yet, and if `data/master/` has no
workbook - none of these prevent the service from starting).

## 2. Environment variables

See `.env.example` for the authoritative list (names only). Summary:

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` | One of these, for job execution | Read directly by the SDK - see section 3 |
| `POLLITIK_API_TOKEN` | Yes, for any mutating endpoint | This service's own MVP auth - see section 9 |
| `POLLITIK_JOB_STORE_DIR` | No (defaults to `service_data/jobs/`) | Where job JSON files live |
| `POLLITIK_PYTHON_BIN` | No (defaults to `python3`) | Interpreter used to run `python/*.py` as subprocesses |
| `POLLITIK_MAX_TURNS` | No (defaults to `40`) | Cap on agent turns per job |

## 3. Agent SDK authentication

Pick one:

- **API key** (simplest for a server): set `ANTHROPIC_API_KEY`. Standard
  pay-per-token billing.
- **Claude subscription OAuth token**: set `CLAUDE_CODE_OAUTH_TOKEN`
  instead. Useful if the deployment should draw against a Claude
  subscription rather than API billing - generate this the same way you
  would for any other headless Claude Code usage.

Do not set both unless you know which one you want to take precedence;
just set the one you intend to use. Neither is read or logged by this
service's own code - `service/config.has_anthropic_auth()` only checks
presence for the health endpoint.

## 4. Running tests

```bash
source .venv/bin/activate
pip install -r requirements.txt   # includes pytest/pytest-asyncio/httpx
python3 -m pytest tests/ -v
```

Tests never call the real Anthropic API (`service/agent.query` is
monkeypatched in the SDK-delegation test) and never touch the real
`data/staging/candidates.jsonl` or `config/allowed_domains.txt` - see the
isolation note at the top of `tests/conftest.py`. Nothing in `tests/`
requires `ANTHROPIC_API_KEY` to be set.

## 5. Running via Docker

```bash
docker build -t pollitik-manager:local .
docker run -d --name pollitik-manager -p 8000:8000 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e POLLITIK_API_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))") \
  pollitik-manager:local
```

Or via Compose (reads `POLLITIK_API_TOKEN`/`ANTHROPIC_API_KEY`/
`CLAUDE_CODE_OAUTH_TOKEN` from your shell environment or a local `.env`
file - see `docker-compose.yml`):

```bash
docker compose up --build
```

The image:

- runs as a non-root user (`pollitik`, uid 10001)
- exposes only port 8000
- has a `HEALTHCHECK` against `GET /health`
- installs only `requirements.txt` - no R toolchain (see "R support"
  below), no build tooling beyond what pip needs
- never `--privileged`, never mounts the Docker socket

Verified locally: `docker build` succeeds, the container reports
`healthy` via its own `HEALTHCHECK`, and a full request cycle (health ->
unauthenticated rejection -> create job -> get job -> blocked
approve-write) passes against the running container.

### R support (not yet enabled)

No `R/` scripts exist in this repository yet (see `README.md`). The
Dockerfile deliberately does not install R - add an `apt-get install -y
r-base` layer (plus whatever R packages the eventual `R/*.R` scripts
need) once that code exists, rather than shipping an unused ~1GB R
toolchain today.

## 6. Persistent volume requirements

Mount these as named volumes (see `docker-compose.yml`) or another
persistence mechanism in production - everything else in the image is
either code (redeploy to change it) or safely ephemeral:

- `data/master/` - the production workbook. Never fabricated by this
  service; a production-write job fails clearly if it's absent (see
  `python/apply_changes.py`).
- `data/staging/` - `candidates.jsonl`, the append-only audit trail of
  every candidate observation any job has produced, at every validation
  status.
- `data/archive/` - timestamped workbook backups, made automatically
  before every write.
- `data/cache/` - the persistent source-retrieval cache
  (`python/source_cache.py`). Losing this on redeploy isn't unsafe (the
  next research job just re-fetches and re-verifies), only more
  expensive in tokens - mount it anyway to keep the token-efficiency
  benefit across restarts.
- `data/reference_index.duckdb` - derived from `data/master/`, safe to
  lose (rebuild with `python/build_reference_index.py`), but mounting it
  avoids an unnecessary rebuild on every restart.
- `feedback/` - human corrections, if/when that workflow is wired up.
- `logs/` - validation/write logs, and `logs/research/cache_access.jsonl`
  (the deterministic cache-hit/miss log the usage-observability counts
  in section on token efficiency are computed from - see README.md).
- `outputs/` - R-generated figures/reports, once that exists.
- `service_data/jobs/` - the MVP job store (see section 13 for its
  successor).

`config/`, `.claude/`, and `python/` are part of the application image
(baked in via `COPY . .`), not volumes - the domain allow-list and hook
logic cannot be modified at runtime without rebuilding/redeploying the
image, which is a deliberate security property, not an oversight.

## 7. Filesystem isolation

The container's working directory is the Pollitik repository and
nothing else. `docker-compose.yml` mounts only the named volumes listed
in section 6 - it never bind-mounts a host directory, so there is no
path by which `~/.ssh`, other home-directory contents, `Downloads`,
`Desktop`, cloud credential folders, or unrelated repositories could end
up inside the container, regardless of what exists on the host. If you
write your own run command instead of using the provided
`docker-compose.yml`, do not add `-v $HOME:...` or similar broad mounts -
mount only what section 6 lists.

Inside the SDK session itself, `cwd` is pinned to the repository root
(`service/config.AGENT_CWD`) and `add_dirs` (an `ClaudeAgentOptions`
field for granting access beyond `cwd`) is never set - the manager and
its subagents cannot see any path outside this repository's own
container filesystem.

## 8. Network allowlisting

Unchanged from local usage, and this is the point: `config/allowed_domains.txt`
is still the single source of truth for what WebFetch may reach, and
`.claude/hooks/pollitik_guard.py` still enforces it exactly as described
in section 0 (hooks fire unconditionally for a remote session too).
Running remotely does not broaden this - if anything, review the
allow-list more carefully before a remote deployment, since a remote
service is a more attractive target than a local CLI session.

The container itself needs outbound HTTPS to reach `api.anthropic.com`
(or your chosen auth provider's endpoint) for the SDK to function, plus
whatever hosts are on `config/allowed_domains.txt` for WebFetch. It does
not need any inbound access beyond the port your load balancer/reverse
proxy uses to reach it.

## 9. Pollitik API authentication

`service/security.py` implements a single shared bearer token
(`POLLITIK_API_TOKEN`), checked with `hmac.compare_digest` (constant-time
comparison). Every mutating endpoint depends on it; `GET /health` does
not. If `POLLITIK_API_TOKEN` is unset, every mutating endpoint returns
`503` - the service never falls back to an open/unauthenticated mode.

**This is explicitly MVP-grade.** A single static token has no per-caller
identity, no expiry, no scoping (anyone with the token can create jobs
*and* approve writes), and rotating it requires a redeploy/restart with
a new environment variable. Before exposing this beyond a small trusted
MVP deployment, replace it with a real identity provider (OAuth2/OIDC,
signed JWTs with short expiry, or at minimum per-caller API keys with
independent revocation) sitting in front of or alongside this layer.

## 10. Production write authorization

Two points worth restating precisely, since remote execution raises the
stakes:

**Production writes never go through the LLM.** Even though a
`.claude/agents/excel-writer.md` role definition exists (for interactive,
human-in-the-loop Claude Code sessions), `service/agent.py`'s manager
system prompt explicitly forbids delegating to it, and - more importantly
- the only code path that can invoke `python/apply_changes.py` is
`service.agent.approve_write()`, called directly by
`POST /jobs/{job_id}/approve-write` as a subprocess. No `query()` call
happens anywhere in that function. This was a deliberate choice to avoid
depending on the unverified hook-merge behavior noted in section 0.

**Two gates, both required** (`service/app.py`'s
`approve_write_endpoint`):

1. The job must have been created with `allow_production_write: true`.
   This is immutable after creation in this MVP - create a new job if
   you forgot to set it.
2. `POST /jobs/{job_id}/approve-write` must be called explicitly, with a
   valid `POLLITIK_API_TOKEN`.

The task brief describes gate 2 as "`allow_production_write == true` OR
explicit approved-write API action" - a looser, either/or reading. This
implementation uses the **stricter AND reading** instead (both required).
**This is a decision you should review** - see "Explicit decisions before
real deployment" below for how to loosen it back to OR if you disagree,
and why the stricter reading was chosen as the safer default given the
brief's own framing ("remote execution introduces additional risk...
no remote task should default to production write access").

Even after both gates pass, nothing is trusted from job state:
`python/apply_changes.py` re-validates every record from scratch
(`validate_record.validate()`), independent of whatever
`validation_status` was recorded at staging time. Only a record that
re-validates to `APPROVED` at the moment of writing is ever written.

## 11. Backup/recovery

Unchanged from the local pipeline, because the write path is unchanged:
`python/apply_changes.py` copies the target workbook to
`data/archive/<name>_backup_<UTC-timestamp>.xlsx` before touching it, and
aborts if that copy doesn't verifiably land on disk. After writing, it
re-opens the workbook and confirms the new row matches what was written
before declaring success; `POST /jobs/{job_id}/approve-write`'s response
includes the `backup_path` for every record it touched, and every write
attempt is logged to `logs/writes/writes.jsonl`. To recover from a bad
write, restore the relevant backup file from `data/archive/` - there is
no separate "recovery" tooling because the backup file *is* the recovery
mechanism.

## 12. Deploying to a generic cloud container host

Nothing here is tied to one provider. The image is a standard container;
any host that can run `docker build`/an OCI image with:

- injected environment variables (never baked into the image - see
  section 9/section 15 on secrets),
- a persistent volume/disk mounted at the paths in section 6,
- one exposed HTTP port,
- an HTTP health check against `GET /health`,

works (e.g. a managed container service, a VM running Docker/Compose
directly, or a Kubernetes Deployment + PersistentVolumeClaim). The
`HEALTHCHECK` in the Dockerfile doubles as a readiness/liveness probe
definition if your platform wants one expressed separately (translate it
to that platform's probe format pointing at `GET /health`).

## 13. What PostgreSQL/Redis would add

The current job store (`service/job_store.py`) is one JSON file per job
on local disk, explicitly chosen to avoid overengineering the first
version - see that file's docstring for the documented restart behavior
(a job left `RUNNING` when the process dies is marked `INTERRUPTED` on
next startup, never silently assumed complete).

This does not survive horizontal scaling: two processes/containers each
running their own `JobStore` would not see each other's jobs. To support
multiple instances, replace `JobStore` with a version backed by
PostgreSQL (job records, since they're small structured rows with clear
fields - `schemas.JobRecord` is already a natural table schema) and/or
Redis (if you want pub/sub for live job-status streaming instead of
polling `GET /jobs/{job_id}`, or a lighter-weight store than Postgres for
job state specifically). The `JobStore` class's public methods
(`create`/`get`/`save`/`list_ids`/`recover_on_startup`) are the interface
a new backend needs to implement - nothing else in `service/` should need
to change.

## 14. What multiple workers would add

Right now, `POST /jobs/{job_id}/run` schedules the job with
`asyncio.create_task` inside the single Uvicorn worker process handling
that request. This means:

- Running `uvicorn ... --workers N` with N > 1 today would be actively
  wrong - a job's background task lives only in the worker process that
  received the `/run` call, and other workers polling `GET /jobs/{id}`
  would see the job-store file but not the live task.
- A crashed worker mid-job is exactly the `INTERRUPTED` case
  `job_store.py` documents.

To genuinely support multiple workers/instances: move job execution out
of the request-handling process entirely, into a real task queue (Celery,
RQ, Dramatiq, or similar) backed by Redis/RabbitMQ, with the FastAPI
process only enqueuing jobs and reading status from the shared store
(section 13). At that point `POST /jobs/{job_id}/run` becomes "enqueue",
and a separate worker pool (which still needs the same repo checkout,
`.claude/` contents, and environment variables) executes
`agent.run_job`/`agent.approve_write`.

## 15. Rotating secrets safely

- **`ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN`**: generate the new
  credential first (Anthropic console, or your OAuth flow), deploy it as
  a new environment variable value, confirm `GET /health`'s
  `anthropic_auth_configured` check and a real job succeed against it,
  *then* revoke the old credential. Never delete the old one before the
  new one is confirmed working - a mid-rotation outage is a service that
  can't run any jobs.
- **`POLLITIK_API_TOKEN`**: generate a new token
  (`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`),
  update every caller to use it, deploy the new value, then remove the
  old value. Because this is a single shared token (section 9), there is
  no way to run old and new simultaneously without a brief coordinated
  cutover - another reason to replace this with per-caller credentials
  before multiple real clients depend on this service.
- In all cases: secrets live only in environment variables /
  your platform's secret manager, never in the image (`.gitignore`
  excludes `.env`; `Dockerfile` never `COPY`s it) and never in
  `service_data/jobs/*.json` (`schemas.JobRecord` has no field for
  credentials - `JobRecord.public_summary()` is a plain `model_dump()` of
  a model that was never given one).

## Explicit decisions before real deployment

Things this implementation resolved with a specific, documented choice -
review each before deploying beyond local/MVP use:

1. **`permission_mode="bypassPermissions"`** for the manager session
   (section 0). Safe given the confirmed unconditional-hook behavior and
   per-agent tool scoping, but `"dontAsk"` + an explicit `allowed_tools`
   allow-list is available if you want defense-in-depth beyond the hook.
2. **Two-gate write model resolved as AND, not OR** (section 10). The
   task brief's own wording was ambiguous between the two; this
   implementation chose the stricter reading. One line in
   `service/app.py`'s `approve_write_endpoint` (removing the
   `allow_production_write` check) reverts to the looser OR reading if
   you decide the endpoint-call-as-authorization alone should be
   sufficient.
3. **`POLLITIK_API_TOKEN` is a single shared secret** (section 9). Fine
   for one or a few trusted operators; replace before wider use.
4. **Job store is single-process, file-backed** (sections 13-14). Fine
   for one instance; do not scale to multiple Uvicorn workers or
   containers without the queue/store changes described there first.
5. **`data/archive/fake_workbook_backup_20260813T012436Z.xlsx`** may
   still exist in this repository's `data/archive/` from earlier manual
   hook-testing in this same project (a backup of a synthetic scratchpad
   fixture, not real data) - `pollitik_guard.py` blocks its own deletion
   by design (see that file's docstring on destructive-operation
   handling), so it was left in place rather than routed around. Remove
   it manually if you want a clean `data/archive/` before deployment.
