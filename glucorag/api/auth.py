"""Account routes: register, sign in (browser cookie, device token or pairing code), sign
out, current account, change password."""

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from glucorag.api.deps import (
    SESSION_COOKIE,
    CurrentPrincipal,
    CurrentUser,
    OptionalPrincipal,
    Service,
)
from glucorag.core.accounts import (
    DUMMY_HASH,
    LoginThrottle,
    WeakPasswordError,
    check_password_policy,
    hash_password,
    new_patient_id,
    new_session_token,
    normalize_pairing_code,
    token_hash,
    verify_password,
)
from glucorag.core.storage import StoredUser, UserGoneError
from glucorag.service import GlucoseService

router = APIRouter(prefix="/auth")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DEVICE_TOKEN_DAYS = 365


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)

    @field_validator("email")
    @classmethod
    def _normalise(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("Enter a valid email address.")
        return v


class AccountOut(BaseModel):
    email: str
    role: Literal["person", "clinician"]
    unit: Literal["mg/dL", "mmol/L"]
    has_profile: bool


class TokenIn(Credentials):
    device: str = Field(min_length=1, max_length=64)


class PairIn(BaseModel):
    code: str = Field(max_length=32)
    device: str = Field(min_length=1, max_length=64)


class TokenOut(BaseModel):
    token: str
    expires_at: datetime
    account: AccountOut


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


def account_out(user: StoredUser, has_profile: bool) -> AccountOut:
    return AccountOut(email=user.email, role=user.role, unit=user.unit, has_profile=has_profile)


def _throttle(request: Request) -> LoginThrottle:
    return request.app.state.login_throttle


def _start_session(request: Request, response: Response, service_user: StoredUser) -> None:
    days: int = request.app.state.session_days
    token, hashed = new_session_token()
    expires = datetime.now(UTC) + timedelta(days=days)
    request.app.state.service.storage.create_session(hashed, service_user.id, expires)
    secure = request.app.state.cookie_secure
    if secure is None:
        forwarded = request.headers.get("x-forwarded-proto", "")
        secure = request.url.scheme == "https" or forwarded == "https"
    response.set_cookie(
        SESSION_COOKIE, token, max_age=days * 86400, httponly=True, samesite="strict",
        secure=secure, path="/",
    )


@router.post("/register", status_code=201)
def register(
    body: Credentials, request: Request, response: Response, service: Service
) -> AccountOut:
    if not request.app.state.allow_signup:
        raise HTTPException(403, "Sign-up is closed on this server. Ask its administrator.")
    try:
        check_password_policy(body.password)
    except WeakPasswordError as e:
        raise HTTPException(422, str(e)) from e
    try:
        user = service.storage.create_user(
            body.email, hash_password(body.password), "person", new_patient_id()
        )
    except ValueError as e:
        raise HTTPException(409, "An account with this email already exists.") from e
    _start_session(request, response, user)
    return account_out(user, has_profile=False)


def _check_credentials(
    body: Credentials, service: GlucoseService, throttle: LoginThrottle
) -> StoredUser:
    """The account for these credentials, or 429 (throttled) / 401 (wrong email or password)."""
    wait = throttle.retry_after(body.email)
    if wait > 0:
        raise HTTPException(
            429, f"Too many failed attempts. Try again in {int(wait // 60) + 1} min.",
            {"Retry-After": str(int(wait) + 1)},
        )
    found = service.storage.user_credentials(body.email)
    stored_hash = found[1] if found else DUMMY_HASH
    if not verify_password(body.password, stored_hash) or found is None:
        throttle.failure(body.email)
        raise HTTPException(401, "Email or password is incorrect.")
    throttle.success(body.email)
    return found[0]


@router.post("/login")
def login(
    body: Credentials,
    request: Request,
    response: Response,
    service: Service,
    throttle: Annotated[LoginThrottle, Depends(_throttle)],
) -> AccountOut:
    user = _check_credentials(body, service, throttle)
    try:
        _start_session(request, response, user)
    except UserGoneError as e:  # deleted while its password was being checked
        raise HTTPException(401, "Email or password is incorrect.") from e
    return account_out(user, service.is_registered(user.patient_id))


@router.post("/token")
def issue_token(
    body: TokenIn,
    service: Service,
    throttle: Annotated[LoginThrottle, Depends(_throttle)],
) -> TokenOut:
    """Sign a phone in: a long-lived bearer token for ``Authorization: Bearer``."""
    user = _check_credentials(body, service, throttle)
    if user.role != "person":
        raise HTTPException(403, "Device sign-in is for personal accounts.")
    token, hashed = new_session_token()
    expires = datetime.now(UTC) + timedelta(days=DEVICE_TOKEN_DAYS)
    try:
        service.storage.create_session(hashed, user.id, expires, device=body.device)
    except UserGoneError as e:  # deleted while its password was being checked
        raise HTTPException(401, "Email or password is incorrect.") from e
    return TokenOut(
        token=token, expires_at=expires,
        account=account_out(user, service.is_registered(user.patient_id)),
    )


_BAD_PAIRING = "This pairing code is not valid. Make a new one on the website."


@router.post("/pair")
def pair(
    body: PairIn,
    request: Request,
    service: Service,
    throttle: Annotated[LoginThrottle, Depends(_throttle)],
) -> TokenOut:
    """Sign a phone in with a code from ``POST /me/pairing``: the same device token as
    ``/auth/token``, without typing a password. Failures are throttled per client address."""
    key = f"pair:{request.client.host if request.client else 'unknown'}"
    wait = throttle.retry_after(key)
    if wait > 0:
        raise HTTPException(
            429, f"Too many failed attempts. Try again in {int(wait // 60) + 1} min.",
            {"Retry-After": str(int(wait) + 1)},
        )
    code = normalize_pairing_code(body.code)
    now = datetime.now(UTC)
    user = None if code is None else service.storage.redeem_pairing_code(token_hash(code), now)
    if user is None or user.role != "person":
        throttle.failure(key)
        raise HTTPException(401, _BAD_PAIRING)
    throttle.success(key)
    token, hashed = new_session_token()
    expires = now + timedelta(days=DEVICE_TOKEN_DAYS)
    try:
        service.storage.create_session(hashed, user.id, expires, device=body.device)
    except UserGoneError as e:  # account deleted after the code was made
        raise HTTPException(401, _BAD_PAIRING) from e
    return TokenOut(
        token=token, expires_at=expires,
        account=account_out(user, service.is_registered(user.patient_id)),
    )


@router.post("/logout", status_code=204)
def logout(principal: OptionalPrincipal, response: Response, service: Service) -> None:
    if principal is not None and principal.session_hash is not None:
        service.storage.delete_session(principal.session_hash)
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict", httponly=True)


@router.get("/me")
def me(principal: CurrentPrincipal, service: Service) -> AccountOut:
    if principal.user is None:
        raise HTTPException(403, "API keys have no account")
    return account_out(principal.user, service.is_registered(principal.user.patient_id))


@router.post("/password", status_code=204)
def change_password(body: PasswordChange, user: CurrentUser, principal: CurrentPrincipal,
                    service: Service) -> None:
    found = service.storage.user_credentials(user.email)
    if found is None or not verify_password(body.current_password, found[1]):
        raise HTTPException(403, "Current password is incorrect.")
    try:
        check_password_policy(body.new_password)
    except WeakPasswordError as e:
        raise HTTPException(422, str(e)) from e
    service.storage.set_password_hash(user.id, hash_password(body.new_password))
    # Every other session ends; this one stays signed in.
    service.storage.delete_user_sessions(user.id, keep=principal.session_hash)
