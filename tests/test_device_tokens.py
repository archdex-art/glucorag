from datetime import UTC, datetime, timedelta

from test_accounts import PASSWORD, PROFILE, _readings, _register

from glucorag.core.accounts import hash_password

EMAIL = "a@example.com"


def _token(c, email=EMAIL, password=PASSWORD, device="Pixel 8"):
    return c.post("/auth/token", json={"email": email, "password": password, "device": device})


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _signed_in_token(c, device="Pixel 8"):
    _register(c)
    c.cookies.clear()
    r = _token(c, device=device)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_token_issue_and_use(make_client):
    with make_client() as c:
        _register(c)
        c.cookies.clear()
        r = _token(c)
        assert r.status_code == 200
        body = r.json()
        assert body["account"]["email"] == EMAIL
        expires = datetime.fromisoformat(body["expires_at"])
        now = datetime.now(UTC)
        assert now + timedelta(days=364) < expires < now + timedelta(days=366)
        assert "set-cookie" not in {k.lower() for k in r.headers}
        assert c.get("/auth/me").status_code == 401
        me = c.get("/auth/me", headers=_bearer(body["token"]))
        assert me.status_code == 200 and me.json()["email"] == EMAIL


def test_token_wrong_password_401_and_throttled_after_5(make_client):
    with make_client() as c:
        _register(c)
        c.cookies.clear()
        for _ in range(5):
            bad = _token(c, password="x" * 12)
            assert bad.status_code == 401
            assert bad.json()["detail"] == "Email or password is incorrect."
        locked = _token(c)
        assert locked.status_code == 429 and "Retry-After" in locked.headers


def test_token_refused_for_clinician(make_client):
    with make_client() as c:
        storage = c.app.state.service.storage
        storage.create_user("doc@example.com", hash_password(PASSWORD), "clinician", "p-doc")
        r = _token(c, email="doc@example.com")
        assert r.status_code == 403
        assert r.json()["detail"] == "Device sign-in is for personal accounts."


def test_token_device_name_is_required(make_client):
    with make_client() as c:
        _register(c)
        assert _token(c, device="").status_code == 422
        assert _token(c, device="x" * 65).status_code == 422


def test_bearer_write_needs_no_origin_and_cross_origin_header_is_ignored(make_client):
    with make_client() as c:
        token = _signed_in_token(c)
        evil = {**_bearer(token), "Origin": "https://evil.example"}
        assert c.put("/me/profile", json=PROFILE, headers=_bearer(token)).status_code == 200
        r = c.post("/me/readings", json=_readings(1)[0], headers=evil)
        assert r.status_code == 200


def test_invalid_bearer_is_401_even_with_a_valid_cookie(make_client):
    with make_client() as c:
        _register(c)  # cookie stays set
        r = c.get("/auth/me", headers=_bearer("not-a-real-token"))
        assert r.status_code == 401 and r.headers["WWW-Authenticate"] == "Bearer"


def test_malformed_bearer_header_is_401(make_client):
    with make_client() as c:
        _register(c)  # a valid cookie must not rescue a broken bearer header
        for header in ("Bearer", "Bearer a b", "bearer "):
            r = c.get("/auth/me", headers={"Authorization": header})
            assert r.status_code == 401, header
            assert r.headers["WWW-Authenticate"] == "Bearer"


def test_other_authorization_schemes_fall_through_to_the_cookie(make_client):
    """A Basic-auth reverse proxy in front of the website must not break cookie sign-in."""
    with make_client() as c:
        _register(c)
        r = c.get("/auth/me", headers={"Authorization": "Basic abc"})
        assert r.status_code == 200 and r.json()["email"] == EMAIL


def test_bearer_scheme_is_case_insensitive(make_client):
    with make_client() as c:
        token = _signed_in_token(c)
        assert c.get("/auth/me", headers={"Authorization": f"bearer {token}"}).status_code == 200


def test_bearer_use_is_recorded(make_client):
    with make_client() as c:
        token = _signed_in_token(c)
        assert c.get("/me/devices", headers=_bearer(token)).json()[0]["last_used_at"] is not None


def test_devices_list_revoke_then_401(make_client):
    with make_client() as c:
        token = _signed_in_token(c, device="Pixel 8")
        devices = c.get("/me/devices", headers=_bearer(token)).json()
        assert [d["device"] for d in devices] == ["Pixel 8"]
        assert set(devices[0]) == {"id", "device", "created_at", "last_used_at"}
        r = c.delete(f"/me/devices/{devices[0]['id']}", headers=_bearer(token))
        assert r.status_code == 204
        assert c.get("/me/status", headers=_bearer(token)).status_code == 401


def test_cookie_sessions_not_listed_as_devices(make_client):
    with make_client() as c:
        _register(c)
        r = c.get("/me/devices")
        assert r.status_code == 200 and r.json() == []


def test_cannot_revoke_someone_elses_device(make_client):
    with make_client() as c:
        mine = _signed_in_token(c)
        _register(c, email="b@example.com")
        c.cookies.clear()
        theirs = _token(c, email="b@example.com").json()["token"]
        their_id = c.get("/me/devices", headers=_bearer(theirs)).json()[0]["id"]
        assert c.delete(f"/me/devices/{their_id}", headers=_bearer(mine)).status_code == 404
        assert c.delete("/me/devices/999999", headers=_bearer(mine)).status_code == 404
        assert c.get("/auth/me", headers=_bearer(theirs)).status_code == 200


def test_logout_with_bearer_ends_that_session(make_client):
    with make_client() as c:
        token = _signed_in_token(c)
        assert c.post("/auth/logout", headers=_bearer(token)).status_code == 204
        assert c.get("/auth/me", headers=_bearer(token)).status_code == 401
        assert c.get("/me/devices", headers=_bearer(token)).status_code == 401
