"""Request dependencies: the service, who is calling, and what they may do.

Three kinds of caller:

* **API key** (``X-API-Key``): devices, scripts and the replay adapter. Full staff access.
* **Clinician session**: staff pages (ward, alerts, model, system) and the staff API.
* **Person session**: only their own data under ``/me``.

Browser sessions are an HttpOnly ``SameSite=Strict`` cookie. Unsafe methods made with a
cookie must also carry a same-origin ``Origin`` header when the browser sends one, so a
cookie alone can never authorise a cross-site write. Phone apps send their device session
as ``Authorization: Bearer <token>`` instead; browsers never attach that header on their
own, so bearer requests skip the origin check.
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, Header, HTTPException, Request

from glucorag.core.accounts import token_hash
from glucorag.core.storage import StoredUser
from glucorag.service import GlucoseService

SESSION_COOKIE = "glucorag_session"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_service(request: Request) -> GlucoseService:
    return request.app.state.service


Service = Annotated[GlucoseService, Depends(get_service)]


@dataclass(frozen=True)
class Principal:
    kind: Literal["api_key", "session"]
    user: StoredUser | None = None
    session_hash: str | None = None

    @property
    def is_staff(self) -> bool:
        return self.kind == "api_key" or (self.user is not None and self.user.role == "clinician")


def _key_ok(request: Request, key: str) -> bool:
    keys: list[str] = request.app.state.api_keys
    return any(secrets.compare_digest(key.encode(), k.encode()) for k in keys)


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if origin is None:  # non-browser clients and same-origin GETs may omit it
        return True
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return urlsplit(origin).netloc == host


def _bearer_token(header: str | None) -> str | None:
    """The token of a ``Bearer`` header; ``None`` for no header or another scheme (e.g. a
    Basic-auth reverse proxy in front of the website), so the cookie still applies."""
    parts = (header or "").split()
    if not parts or parts[0].lower() != "bearer":
        return None
    if len(parts) != 2:
        raise HTTPException(401, "Malformed Bearer header", {"WWW-Authenticate": "Bearer"})
    return parts[1]


def optional_principal(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal | None:
    if x_api_key is not None:
        if not _key_ok(request, x_api_key):
            raise HTTPException(401, "Invalid X-API-Key", {"WWW-Authenticate": "ApiKey"})
        return Principal("api_key")
    storage = get_service(request).storage
    now = datetime.now(UTC)
    bearer = _bearer_token(authorization)
    if bearer is not None:
        hashed = token_hash(bearer)
        user = storage.session_user(hashed, now)
        if user is None:  # never fall back to the cookie: the app must sign in again
            raise HTTPException(401, "Sign in again on this device", {"WWW-Authenticate": "Bearer"})
        storage.touch_session(hashed, now)
        return Principal("session", user, hashed)
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    hashed = token_hash(token)
    user = storage.session_user(hashed, now)
    if user is None:
        return None
    if request.method not in _SAFE_METHODS and not _same_origin(request):
        raise HTTPException(403, "Cross-origin request refused")
    return Principal("session", user, hashed)


OptionalPrincipal = Annotated[Principal | None, Depends(optional_principal)]


def require_principal(principal: OptionalPrincipal) -> Principal:
    if principal is None:
        raise HTTPException(
            401, "Sign in to continue", {"WWW-Authenticate": "ApiKey, Bearer, Cookie"}
        )
    return principal


def require_staff(principal: Annotated[Principal, Depends(require_principal)]) -> Principal:
    if not principal.is_staff:
        raise HTTPException(403, "Clinician access only")
    return principal


def require_user(principal: Annotated[Principal, Depends(require_principal)]) -> StoredUser:
    if principal.user is None:
        raise HTTPException(403, "This endpoint needs a signed-in user, not an API key")
    return principal.user


CurrentUser = Annotated[StoredUser, Depends(require_user)]
CurrentPrincipal = Annotated[Principal, Depends(require_principal)]
