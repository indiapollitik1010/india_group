# Pollitik Database

Whenever a task involves collecting, interpreting, validating,
translating, classifying, staging, or writing political-executive
public-support polling data for Pollitik, follow the
pollitik-executive-support Skill
(`.claude/skills/pollitik-executive-support/SKILL.md`, invocable as
`/pollitik-executive-support`).

Permanent rules for this project:

- Production polling data requires verified provenance. A source is
  valid only if it was actually retrieved via WebFetch or another
  explicitly approved deterministic retrieval mechanism.
- Model-generated URLs are never valid provenance, no matter how
  plausible they look.
- Internet evidence must be retrieved and inspected before it is used
  to support any observation.
- Writing to the production Pollitik workbook requires deterministic
  validation and staging first; only APPROVED observations may be
  written.
- Research agents may not directly write production data. This is
  enforced by `.claude/hooks/pollitik_guard.py` (a PreToolUse hook) in
  addition to the Skill's instructions.
