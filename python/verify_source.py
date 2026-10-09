#!/usr/bin/env python3
"""Deterministic source-provenance verification (Skill sections 5, 6, 31).

IMPORTANT: this script does NOT fetch URLs itself. It only validates
retrieval metadata that a real WebFetch call (or another explicitly
approved deterministic retrieval mechanism) already produced. It
deliberately performs no HTTP requests of its own, so it cannot become a
shell-based bypass around the WebFetch domain gate enforced by
.claude/hooks/pollitik_guard.py.

Input (stdin or --record a JSON file): a JSON object with fields such as
produced by an actual retrieval:

    {
      "requested_url": "...",
      "final_url": "...",
      "http_status": 200,
      "retrieved_at": "2026-08-12T14:03:00Z",
      "evidence_text": "...supporting excerpt from the fetched page..."
    }

Output: a JSON object:

    {
      "source_verified": true | false,
      "status": "OK" | "SOURCE_VALIDATION_FAILED" | "UNVERIFIED_SOURCE_URL",
      "reason": "...",
      "source_domain": "..."
    }

A record can only be treated as source_verified=true once this script
(or validate_record.py, which calls it) says so. Nothing upstream may
set source_verified=true on its own assertion (Skill section 33:
confidence is not evidence).
"""

import argparse
import json
import sys

import pollitik_common as pc


def verify(record):
    final_url = (record or {}).get("final_url") or ""
    requested_url = (record or {}).get("requested_url") or ""
    http_status = (record or {}).get("http_status")
    retrieved_at = (record or {}).get("retrieved_at") or ""
    evidence_text = (record or {}).get("evidence_text") or ""

    if not final_url:
        return {
            "source_verified": False,
            "status": "UNVERIFIED_SOURCE_URL",
            "reason": "No final_url present. A source URL that was never "
                      "actually retrieved (e.g. only written in model "
                      "prose) is not valid provenance.",
            "source_domain": None,
        }

    host = pc.extract_host(final_url)
    if not host:
        return {
            "source_verified": False,
            "status": "SOURCE_VALIDATION_FAILED",
            "reason": "final_url '{}' has no resolvable host.".format(final_url),
            "source_domain": None,
        }

    allowed_domains = pc.read_allowed_domains()
    if not allowed_domains or not pc.host_allowed(host, allowed_domains):
        return {
            "source_verified": False,
            "status": "SOURCE_VALIDATION_FAILED",
            "reason": "Domain '{}' is not in config/allowed_domains.txt.".format(host),
            "source_domain": host,
        }

    if http_status is None or int(http_status) != 200:
        return {
            "source_verified": False,
            "status": "SOURCE_VALIDATION_FAILED",
            "reason": "Retrieval did not report a successful (200) status "
                      "(got {!r}).".format(http_status),
            "source_domain": host,
        }

    if not retrieved_at:
        return {
            "source_verified": False,
            "status": "SOURCE_VALIDATION_FAILED",
            "reason": "No retrieval timestamp recorded.",
            "source_domain": host,
        }

    if not evidence_text.strip():
        return {
            "source_verified": False,
            "status": "SOURCE_VALIDATION_FAILED",
            "reason": "No evidence_text preserved from the retrieved "
                      "content. A URL alone, without the supporting "
                      "excerpt, is not sufficient.",
            "source_domain": host,
        }

    return {
        "source_verified": True,
        "status": "OK",
        "reason": "final_url resolved to an approved domain, retrieval "
                  "reported success, and evidence text is present.",
        "source_domain": host,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--record",
        help="Path to a JSON file with retrieval metadata. Defaults to "
             "reading a single JSON object from stdin.",
    )
    args = parser.parse_args()

    if args.record:
        with open(args.record, "r", encoding="utf-8") as f:
            record = json.load(f)
    else:
        record = json.load(sys.stdin)

    result = verify(record)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["source_verified"] else 1)


if __name__ == "__main__":
    main()
