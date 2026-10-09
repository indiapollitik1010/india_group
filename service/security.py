"""MVP API authentication: a single shared bearer token.

This is intentionally simple - see docs/REMOTE_DEPLOYMENT.md for why, and
for what should replace it (a real identity provider / per-caller
credentials) before this service is exposed beyond a trusted MVP
deployment. GET /health is exempt; every mutating endpoint depends on
require_api_token.

Fails closed: if POLLITIK_API_TOKEN is not set in the environment, every
mutating request is rejected (503) rather than silently allowed through.
"""

import hmac

from fastapi import Header, HTTPException, status

from . import config


async def require_api_token(authorization: str | None = Header(default=None)) -> None:
    if not config.API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "POLLITIK_API_TOKEN is not configured on this server. "
                "Mutating endpoints are disabled until it is set - this "
                "service never falls back to an open/unauthenticated mode."
            ),
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token. Send 'Authorization: Bearer <POLLITIK_API_TOKEN>'.",
        )

    provided = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(provided, config.API_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token.",
        )
