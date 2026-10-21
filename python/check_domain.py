#!/usr/bin/env python3
"""Deterministic pre-fetch domain classifier (domain-approval workflow,
pollitik-executive-support Skill).

Given a candidate URL, reports whether its host is already present in
config/allowed_domains.txt - WITHOUT fetching anything and without any
network I/O of its own (same non-bypass guarantee as
python/verify_source.py). This lets the researcher agent decide up front
whether it may WebFetch immediately (APPROVED) or must stop and request
the project owner's explicit approval first (DOMAIN_APPROVAL_REQUIRED),
rather than discovering the answer by attempting a fetch and having
.claude/hooks/pollitik_guard.py deny it. Asking first is the intended
workflow; the hook remains the actual enforcement backstop either way.

Usage:
    python3 python/check_domain.py --url <candidate-url>
"""

import argparse
import json
import sys

import pollitik_common as pc


def check(url):
    host = pc.extract_host(url)
    if not host:
        return {
            "url": url,
            "host": None,
            "approved": False,
            "status": "INVALID_URL",
            "reason": "Could not parse a resolvable host from this URL.",
        }

    allowed_domains = pc.read_allowed_domains()
    if allowed_domains and pc.host_allowed(host, allowed_domains):
        return {
            "url": url,
            "host": host,
            "approved": True,
            "status": "APPROVED",
            "reason": "Host is present in config/allowed_domains.txt "
                      "(or a subdomain of an approved entry).",
        }

    return {
        "url": url,
        "host": host,
        "approved": False,
        "status": "DOMAIN_APPROVAL_REQUIRED",
        "reason": "Host is not present in config/allowed_domains.txt. Do "
                  "not WebFetch it (the pollitik_guard hook will also "
                  "deny it). Before proceeding: identify what data this "
                  "domain may contain, why it may be useful, which "
                  "country/pollster/survey program it relates to, and "
                  "request the project owner's explicit approval to add "
                  "it. Do not retry with a mirror, shortener, proxy, or "
                  "cached copy to work around this.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()

    result = check(args.url)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["approved"] else 1)


if __name__ == "__main__":
    main()
