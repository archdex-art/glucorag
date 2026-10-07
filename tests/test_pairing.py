from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

from conftest import KEY
from test_accounts import PASSWORD, _register
from test_device_tokens import _bearer, _signed_in_token

from glucorag.api import me as me_api
from glucorag.core.accounts import PAIRING_ALPHABET, hash_password, normalize_pairing_code
from glucorag.core.storage import Storage

EMAIL = "a@example.com"
BAD = "This pairing code is not valid. Make a new one on the website."
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def _make_code(c, **kw):
    r = c.post("/me/pairing", **kw)
    assert r.status_code == 201, r.text
    return r.json()


def _pair(c, code, device="Pixel 8"):
    return c.post("/auth/pair", json={"code": code, "device": device})


def test_pairing_code_signs_a_phone_in(make_client):
    with make_client() as c:
        _register(c)
        body = _make_code(c)
        code = body["code"]
        assert len(code) == 9 and code[4] == "-"
        assert all(ch in PAIRING_ALPHABET for ch in code.replace("-", ""))
        expires = datetime.fromisoformat(body["expires_at"])
        now = datetime.now(UTC)
        assert now + timedelta(minutes=9) < expires <= now + timedelta(minutes=10)
        assert body["qr_svg"].startswith("<svg") and "<script" not in body["qr_svg"]
        uri = urlsplit(body["uri"])
        assert (uri.scheme, uri.netloc) == ("glucorag", "pair")
        query = parse_qs(uri.query)
        assert query == {"server": [body["server_url"]], "code": [code.replace("-", "")]}

        c.cookies.clear()
        r = _pair(c, code)
        assert r.status_code == 200, r.text
        token = r.json()
        assert set(token) == {"token", "expires_at", "account"}
        assert token["account"]["email"] == EMAIL
        assert "set-cookie" not in {k.lower() for k in r.headers}
        me = c.get("/me", headers=_bearer(token["token"]))
        assert me.status_code == 200 and me.json()["email"] == EMAIL
        [device] = c.get("/me/devices", headers=_bearer(token["token"])).json()
        assert device["device"] == "Pixel 8"


def test_pairing_code_is_single_use(make_client):
    with make_client() as c:
        _register(c)
        code = _make_code(c)["code"]
        assert _pair(c, code).status_code == 200
        again = _pair(c, code)
        assert again.status_code == 401 and again.json()["detail"] == BAD


def test_expired_code_is_refused(make_client):
    with make_client() as c:
        _register(c)
        code = _make_code(c)["code"]
        storage = c.app.state.service.storage
        past = (datetime.now(UTC) - timedelta(seconds=1)).isoformat(timespec="microseconds")
        storage._exec("UPDATE pairing_codes SET expires_at=?", (past,))
        r = _pair(c, code)
        assert r.status_code == 401 and r.json()["detail"] == BAD


def test_new_code_replaces_the_previous_one(make_client):
    with make_client() as c:
        _register(c)
        old = _make_code(c)["code"]
        new = _make_code(c)["code"]
        assert _pair(c, old).status_code == 401
        assert _pair(c, new).status_code == 200


def test_code_is_case_and_dash_insensitive(make_client):
    with make_client() as c:
        _register(c)
        code = _make_code(c)["code"]
        sloppy = f" {code[:2].lower()} {code[2:].replace('-', ' - ').lower()} "
        assert _pair(c, sloppy).status_code == 200


def test_malformed_code_and_device_name(make_client):
    with make_client() as c:
        _register(c)
        code = _make_code(c)["code"]
        assert _pair(c, "0000-1111").status_code == 401
        assert _pair(c, code, device="").status_code == 422
        assert _pair(c, code, device="x" * 65).status_code == 422
        assert _pair(c, code).status_code == 200


def test_failed_pairing_is_throttled_per_client(make_client):
    with make_client() as c:
        _register(c)
        code = _make_code(c)["code"]
        for _ in range(5):
            assert _pair(c, "ZZZZ-ZZZZ").status_code == 401
        locked = _pair(c, code)
        assert locked.status_code == 429 and "Retry-After" in locked.headers


def test_only_a_person_browser_session_can_make_codes(make_client):
    with make_client() as c:
        assert c.post("/me/pairing").status_code == 401
        assert c.post("/me/pairing", headers={"X-API-Key": KEY}).status_code == 403

        token = _signed_in_token(c)
        r = c.post("/me/pairing", headers=_bearer(token))
        assert r.status_code == 403

        c.cookies.clear()
        storage = c.app.state.service.storage
        storage.create_user("doc@example.com", hash_password(PASSWORD), "clinician", "p-doc")
        c.post("/auth/login", json={"email": "doc@example.com", "password": PASSWORD})
        r = c.post("/me/pairing")
        assert r.status_code == 403
        assert r.json()["detail"] == "Device sign-in is for personal accounts."


def test_cross_origin_cookie_request_is_refused(make_client):
    with make_client() as c:
        _register(c)
        r = c.post("/me/pairing", headers={"Origin": "https://evil.example"})
        assert r.status_code == 403


def test_server_url_prefers_public_url(make_client):
    with make_client(public_url="https://gluco.example.org/") as c:
        _register(c)
        body = _make_code(c, headers={"Host": "localhost:8851"})
        assert body["server_url"] == "https://gluco.example.org"
        assert body["server_url_guessed"] is False
        assert "server=https%3A%2F%2Fgluco.example.org&" in body["uri"]


def test_server_url_is_the_request_host_when_not_loopback(make_client):
    with make_client() as c:
        _register(c)
        body = _make_code(c, headers={"Host": "glucorag.lan:8851"})
        assert body["server_url"] == "http://glucorag.lan:8851"
        assert body["server_url_guessed"] is False


def test_server_url_guesses_the_lan_address_for_localhost(make_client, monkeypatch):
    monkeypatch.setattr(me_api, "_lan_ipv4", lambda: "192.168.1.20")
    with make_client() as c:
        _register(c)
        for host in ("localhost:8851", "127.0.0.1:8851", "[::1]:8851"):
            body = _make_code(c, headers={"Host": host})
            assert body["server_url"] == "http://192.168.1.20:8851"
            assert body["server_url_guessed"] is True
            assert "server=http%3A%2F%2F192.168.1.20%3A8851&" in body["uri"]


def test_account_deletion_removes_codes(make_client):
    with make_client() as c:
        _register(c)
        code = _make_code(c)["code"]
        assert c.request("DELETE", "/me", json={"password": PASSWORD}).status_code == 204
        storage = c.app.state.service.storage
        assert storage._rows("SELECT COUNT(*) FROM pairing_codes")[0][0] == 0
        assert _pair(c, code).status_code == 401


def test_storage_redeem_is_single_use_and_purges_expired():
    s = Storage(":memory:")
    a = s.create_user("a@example.com", "h", "person", "p-a")
    b = s.create_user("b@example.com", "h", "person", "p-b")
    s.create_pairing_code("old-b", b.id, NOW, NOW + timedelta(minutes=10))
    s.create_pairing_code("code-a", a.id, NOW, NOW + timedelta(minutes=10))

    user = s.redeem_pairing_code("code-a", NOW + timedelta(minutes=1))
    assert user is not None and user.id == a.id
    assert s.redeem_pairing_code("code-a", NOW + timedelta(minutes=2)) is None
    assert s.redeem_pairing_code("old-b", NOW + timedelta(minutes=10)) is None  # expired

    later = NOW + timedelta(minutes=11)
    s.create_pairing_code("new-a", a.id, later, later + timedelta(minutes=10))
    rows = s._rows("SELECT code_hash FROM pairing_codes")
    assert [r[0] for r in rows] == ["new-a"]


def test_normalize_pairing_code():
    assert normalize_pairing_code("abcd-efgh") == "ABCDEFGH"
    assert normalize_pairing_code(" ab cd\tef-gh ") == "ABCDEFGH"
    assert normalize_pairing_code("ABCD-EFG") is None
    assert normalize_pairing_code("ABCD-EFG0") is None  # 0 is not in the alphabet
