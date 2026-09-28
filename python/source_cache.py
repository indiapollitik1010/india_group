#!/usr/bin/env python3
"""Persistent cache of already-verified source retrievals (Skill sections
5-6, 9; token-efficiency requirement #9).

This is NOT a substitute for retrieval or a way to relax source
verification (requirement #22) - it only stores what a real WebFetch
call already produced, so the *same* page does not need to be re-fetched
and re-interpreted by an LLM across jobs/sessions. Every entry keeps the
same provenance fields verify_source.py checks (final_url, http_status,
retrieved_at, evidence_text) - a cache hit is exactly as verifiable as
the original fetch, because it IS the original fetch's recorded output.

Cache entries never expire automatically: a poll result does not change
after publication, so once a page has been verified, its evidence stays
valid indefinitely. If a source page is later corrected/retracted,
delete its entry (by url) and re-fetch rather than trusting the stale
cache - this script does not attempt to detect that on its own.

Every lookup (hit or miss) is logged to logs/research/cache_access.jsonl,
tagged with POLLITIK_JOB_ID when set, so the remote service can tally
cache_hits/cache_misses deterministically per job instead of trusting an
agent's self-report (see service/agent.py).

Usage:
    python3 python/source_cache.py lookup --url <url>
    python3 python/source_cache.py store --record <path-to-json>   # or pipe JSON on stdin
"""

import argparse
import hashlib
import json
import os
import sys

import pollitik_common as pc


def normalize_url(url):
    return (url or "").strip().rstrip("/")


def compute_content_hash(evidence_text):
    return hashlib.sha256((evidence_text or "").encode("utf-8")).hexdigest()


def load_cache():
    return pc.read_jsonl(pc.SOURCE_CACHE_FILE)


def save_cache(entries):
    os.makedirs(os.path.dirname(pc.SOURCE_CACHE_FILE), exist_ok=True)
    tmp = pc.SOURCE_CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    os.replace(tmp, pc.SOURCE_CACHE_FILE)


def log_access(url, hit):
    pc.append_jsonl(pc.CACHE_ACCESS_LOG, {
        "job_id": os.environ.get("POLLITIK_JOB_ID"),
        "url": url,
        "domain": pc.extract_host(url),
        "hit": hit,
        "accessed_at": pc.utc_now_iso(),
    })


def lookup(url):
    key = normalize_url(url)
    for entry in load_cache():
        if normalize_url(entry.get("final_url")) == key:
            log_access(url, True)
            return {"cache_hit": True, "entry": entry}
    log_access(url, False)
    return {"cache_hit": False, "entry": None}


def store(record):
    final_url = record.get("final_url")
    if not final_url:
        raise ValueError("record must include final_url - a cache entry without one is not valid provenance")

    entry = dict(record)
    entry.setdefault("content_hash", compute_content_hash(entry.get("evidence_text")))
    entry.setdefault("domain", pc.extract_host(final_url))
    entry["cached_at"] = pc.utc_now_iso()

    entries = [e for e in load_cache() if normalize_url(e.get("final_url")) != normalize_url(final_url)]
    entries.append(entry)
    save_cache(entries)
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    lookup_parser = sub.add_parser("lookup")
    lookup_parser.add_argument("--url", required=True)

    store_parser = sub.add_parser("store")
    store_parser.add_argument("--record", help="Path to a JSON file. Defaults to reading JSON from stdin.")

    args = parser.parse_args()

    if args.command == "lookup":
        result = lookup(args.url)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result["cache_hit"] else 1)

    if args.command == "store":
        if args.record:
            with open(args.record, "r", encoding="utf-8") as f:
                record = json.load(f)
        else:
            record = json.load(sys.stdin)
        entry = store(record)
        print(json.dumps(entry, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
