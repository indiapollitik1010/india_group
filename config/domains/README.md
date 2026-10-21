# Modular domain configuration

**Enforcement source of truth is still `config/allowed_domains.txt`.**
`.claude/hooks/pollitik_guard.py` and `python/pollitik_common.py` read
that single flat file, and only that file, to decide whether a WebFetch
call is allowed. Nothing in this directory is wired into enforcement.
This directory does not change that on its own — do not assume adding a
file here approves a domain.

## Why this directory exists

`config/allowed_domains.txt` is deliberately a single global list
because the *matching logic* (host/subdomain matching in
`pollitik_common.host_allowed`) is already country-agnostic and
reusable — there is nothing to refactor there. What that flat file
cannot do cleanly is keep **country-specific domain data** (which
country/pollster/program a given approved domain belongs to, and why it
was approved) separate and legible as the list grows. That is what this
directory is for: structured, per-scope metadata about domains, split
so a reviewer can see "what's approved for Canada" without reading
every other country's entries.

## Layout

```
config/domains/
    README.md       — this file
    global.yaml      — domains not tied to one country (e.g. a
                       multi-country survey program's own site)
    _TEMPLATE.yaml   — the schema for a per-country file, uncommitted
                       as real data (leading underscore: not a real
                       country, never loaded as one)
```

A real per-country file (e.g. `canada.yaml`) should only be added once
the project owner has actually approved domain(s) for that country —
copy `_TEMPLATE.yaml`'s shape, do not invent entries.

## Schema (per domain entry)

```yaml
domains:
  - host: "example-pollster.example"     # exact host, no protocol/path
    country: "Example Country"            # or null for global.yaml entries
    pollster_or_program: "Example Pollster"
    source_type: "polling_firm"           # see config/source_systems.yaml's vocabulary
    approval_status: "approved"           # approved | pending | rejected
    active: true
    notes: "Cite how/when the user approved this, per config/allowed_domains.txt rule 5."
```

## Keeping this in sync with `config/allowed_domains.txt`

When the user approves a new domain (see the pollitik-executive-support
Skill's domain-approval workflow):

1. Add it to `config/allowed_domains.txt` (the actual gate — this step
   is required, not optional).
2. Optionally also record it here, in `global.yaml` or the relevant
   country file, for the structured metadata (why it was approved,
   which country/pollster/program it belongs to). This step is
   recommended once there are enough domains that the flat list's plain
   comments stop being enough — it is not itself a substitute for step 1.

Do not build an automated generator that regenerates
`config/allowed_domains.txt` from these files without deliberately
reviewing `.claude/hooks/pollitik_guard.py` and
`tests/test_pipeline_write_guards.py` first — several existing tests
write directly to `config/allowed_domains.txt` and assume it is the
single, hand-maintained source of truth.
