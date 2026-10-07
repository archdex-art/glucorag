import pytest
from _runtime import STEP, T0

from glucorag.core.accounts import LoginThrottle, hash_password, verify_password

PASSWORD = "correct horse battery"
PROFILE = {"age": 34, "gender": "F", "bmi": 22.5, "diabetes_type": "T1D"}


def _register(c, email="a@example.com", password=PASSWORD):
    return c.post("/auth/register", json={"email": email, "password": password})


def _readings(n, start=0):
    return [{"timestamp": (T0 + (start + i) * STEP).isoformat(), "glucose": 110.0}
            for i in range(n)]


def test_password_hash_roundtrip_and_tamper():
    h = hash_password("s3cret-password")
    assert verify_password("s3cret-password", h)
    assert not verify_password("s3cret-passwore", h)
    assert not verify_password("s3cret-password", h.replace("scrypt", "md5"))


def test_throttle_locks_after_limit_and_unlocks_after_window():
    t = LoginThrottle(max_failures=3, window_s=60)
    for i in range(3):
        assert t.retry_after("x", now=float(i)) == 0
        t.failure("x", now=float(i))
    assert t.retry_after("x", now=3.0) == pytest.approx(57.0)
    assert t.retry_after("x", now=61.0) == 0


def test_register_signs_in_with_httponly_strict_cookie_and_rejects_duplicates(make_client):
    with make_client() as c:
        r = _register(c)
        assert r.status_code == 201 and r.json()["has_profile"] is False
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie
        assert c.get("/auth/me").json()["email"] == "a@example.com"
        assert _register(c, email="A@Example.com").status_code == 409
        assert _register(c, email="b@example.com", password="short").status_code == 422


def test_signup_can_be_closed(make_client):
    with make_client(allow_signup=False) as c:
        assert _register(c).status_code == 403


def test_login_is_case_insensitive_and_throttled(make_client):
    with make_client() as c:
        _register(c)
        c.post("/auth/logout")
        assert c.get("/auth/me").status_code == 401
        for _ in range(5):
            bad = c.post("/auth/login", json={"email": "a@example.com", "password": "x" * 12})
            assert bad.status_code == 401
        locked = c.post("/auth/login", json={"email": "A@EXAMPLE.COM", "password": PASSWORD})
        assert locked.status_code == 429 and "Retry-After" in locked.headers


def test_people_cannot_reach_staff_routes_or_other_patients(make_client):
    with make_client() as c:
        _register(c)
        c.put("/me/profile", json=PROFILE)
        assert c.get("/cohort/risk").status_code == 403
        assert c.get("/model").status_code == 403
        assert c.post("/patients", json={"patient_id": "x", **PROFILE}).status_code == 403


def test_clinician_session_reaches_staff_routes(make_client, tmp_path):
    with make_client() as c:
        storage = c.app.state.service.storage
        storage.create_user("doc@example.com", hash_password(PASSWORD), "clinician", "p-doc")
        c.post("/auth/login", json={"email": "doc@example.com", "password": PASSWORD})
        assert c.get("/cohort/risk").status_code == 200


def test_cross_origin_cookie_write_is_refused(make_client):
    with make_client() as c:
        _register(c)
        r = c.put("/me/profile", json=PROFILE, headers={"Origin": "https://evil.example"})
        assert r.status_code == 403
        same = c.put("/me/profile", json=PROFILE, headers={"Origin": "http://testserver"})
        assert same.status_code == 200


def test_personal_flow_profile_readings_forecast_and_offset_aware_times(make_client):
    with make_client() as c:
        _register(c)
        assert c.get("/me/status").status_code == 409  # profile first
        me = c.put("/me/profile", json={**PROFILE, "sensitivity": "cautious"}).json()
        assert me["profile"]["sensitivity"] == "cautious"
        assert (me["profile"]["hypo_quantile"], me["profile"]["hyper_quantile"]) == (0.1, 0.9)
        for body in _readings(9):
            assert c.post("/me/readings", json=body).status_code == 200
        st = c.get("/me/status").json()
        assert st["prediction"]["horizons"] == [15, 30, 45, 60]
        # q0.10 of the constant forecast is 50 mg/dL <= 70: cautious users get a hypo flag.
        assert [f["type"] for f in st["status"]["risk"]] == ["hypo"]
        assert st["prediction"]["t0"][-6] in "+-"  # offset-aware ISO
        hist = c.get("/me/history?hours=6").json()
        assert len(hist["readings"]) == 9 and hist["readings"][0]["timestamp"][-6] in "+-"
        dup = c.post("/me/readings", json=_readings(1, start=8)[0])
        assert dup.status_code == 422 and dup.json()["reason"] == "duplicate"


def test_mmol_entry_is_converted(make_client):
    with make_client() as c:
        _register(c)
        c.put("/me/profile", json=PROFILE)
        body = {"timestamp": T0.isoformat(), "glucose": 5.5, "unit": "mmol/L"}
        c.post("/me/readings", json=body)
        assert c.get("/me/history").json()["readings"][0]["glucose_mg_dl"] == 99.1


def test_import_backfills_history_skips_exact_duplicates_and_old_rows(make_client):
    with make_client(import_max_days=1) as c:
        _register(c)
        c.put("/me/profile", json=PROFILE)
        c.post("/me/readings", json={"timestamp": "2024-01-02T00:00:00+00:00", "glucose": 100})
        csv_text = "timestamp,glucose\n" + "\n".join(
            [
                "2023-12-30T00:00:00,90",  # older than the 1-day window
                "2024-01-01T23:45:00,95",  # earlier than the stored reading: backfilled
                "2024-01-02T00:00:00,100",  # same time as the stored reading: skipped
                "2024-01-02T00:15:00,105",
            ]
        )
        r = c.post("/me/import?tz=UTC", content=csv_text,
                   headers={"Content-Type": "text/csv"}).json()
        assert (r["older_than_window"], r["already_present"], r["accepted"]) == (1, 1, 2)
        hist = c.get("/me/history?hours=24").json()["readings"]
        assert [h["glucose_mg_dl"] for h in hist] == [95, 100, 105]
        bad = c.post("/me/import?tz=Mars/Base", content=csv_text)
        assert bad.status_code == 422


def test_import_reports_and_honours_date_order(make_client):
    with make_client() as c:
        _register(c)
        c.put("/me/profile", json=PROFILE)
        text = "timestamp,glucose\n03-04-2024 10:00,100\n03-04-2024 10:15,101\n"
        auto = c.post("/me/import?tz=UTC", content=text).json()
        assert auto["date_ambiguous"] is True and auto["date_order"] in ("dmy", "mdy")
        c.delete("/me/readings")
        forced = c.post("/me/import?tz=UTC&dates=dmy", content=text).json()
        assert (forced["date_order"], forced["date_ambiguous"]) == ("dmy", False)
        assert forced["first"].startswith("2024-04-03")


def test_sample_loads_once_and_produces_a_fresh_forecast(make_client):
    with make_client(clock="wall") as c:
        _register(c)
        c.put("/me/profile", json=PROFILE)
        r = c.post("/me/sample")
        assert r.status_code == 200 and r.json()["loaded"] == 192
        assert r.json()["outcomes"]["predicted"] > 150
        assert c.get("/me/status").json()["fresh"] is True
        assert c.post("/me/sample").status_code == 409


def test_login_racing_account_deletion_is_a_clean_401(make_client):
    """The password check is slow by design; an account deleted during it must not 500."""
    with make_client() as c:
        _register(c)
        storage = c.app.state.service.storage
        user = storage.users()[0]
        real_lookup = storage.user_credentials

        def lookup_then_delete(email):
            found = real_lookup(email)
            storage.delete_user(user.id)  # deletion commits after the lookup
            return found

        storage.user_credentials = lookup_then_delete
        c.post("/auth/logout")
        r = c.post("/auth/login", json={"email": "a@example.com", "password": PASSWORD})
        assert r.status_code == 401
        assert "set-cookie" not in {k.lower() for k in r.headers}


def test_delete_readings_then_account_removes_everything(make_client):
    with make_client() as c:
        _register(c)
        c.put("/me/profile", json=PROFILE)
        for body in _readings(9):
            c.post("/me/readings", json=body)
        service = c.app.state.service
        pid = service.storage.users()[0].patient_id
        assert c.delete("/me/readings").status_code == 204
        assert service.storage.reading_summary(pid)[0] == 0
        assert service.storage.latest_prediction(pid) is None
        assert service.buffer.history(pid) == []
        assert c.request("DELETE", "/me", json={"password": "wrong-password"}).status_code == 403
        assert c.request("DELETE", "/me", json={"password": PASSWORD}).status_code == 204
        assert service.storage.users() == [] and not service.is_registered(pid)
        assert c.get("/auth/me").status_code == 401


def test_password_change_ends_other_sessions(make_client):
    with make_client() as a, make_client() as b:
        _register(a)
        b.post("/auth/login", json={"email": "a@example.com", "password": PASSWORD})
        new = "an even better passphrase"
        r = a.post("/auth/password", json={"current_password": PASSWORD, "new_password": new})
        assert r.status_code == 204
        assert a.get("/auth/me").status_code == 200
        assert b.get("/auth/me").status_code == 401
