import random
from datetime import UTC, datetime, timedelta

from _runtime import STEP, T0
from test_accounts import PROFILE
from test_device_tokens import _bearer, _signed_in_token


def _phone(c):
    """A signed-in phone with a profile: bearer headers for /me routes."""
    auth = _bearer(_signed_in_token(c))
    assert c.put("/me/profile", json=PROFILE, headers=auth).status_code == 200
    return auth


def _aware(t: datetime) -> str:
    return t.astimezone().isoformat()


def _batch(n, start=0, value=110.0):
    return [{"timestamp": _aware(T0 + (start + i) * STEP), "glucose_mg_dl": value}
            for i in range(n)]


def _post(c, auth, readings):
    return c.post("/me/readings/batch", json={"readings": readings}, headers=auth)


def test_batch_out_of_order_and_duplicates(make_client):
    with make_client() as c:
        auth = _phone(c)
        readings = _batch(12)
        random.Random(1).shuffle(readings)
        first = _post(c, auth, readings)
        assert first.status_code == 200, first.text
        assert first.json() == {"accepted": 12, "already_present": 0, "rejected": []}
        again = _post(c, auth, readings).json()
        assert again == {"accepted": 0, "already_present": 12, "rejected": []}
        history = c.get("/me/history", headers=auth).json()["readings"]
        assert len(history) == 12


def test_batch_future_reading_rejected_with_reason(make_client):
    with make_client(clock="wall") as c:
        auth = _phone(c)
        now = datetime.now().replace(microsecond=0)
        soon, later = now + timedelta(seconds=90), now + timedelta(minutes=3)
        body = _post(c, auth, [
            {"timestamp": _aware(soon), "glucose_mg_dl": 110.0},
            {"timestamp": _aware(later), "glucose_mg_dl": 110.0},
            {"timestamp": _aware(now - STEP), "glucose_mg_dl": 19.0},
            {"timestamp": _aware(now - 2 * STEP), "glucose_mg_dl": 601.0},
        ]).json()
        assert body["accepted"] == 1 and body["already_present"] == 0
        rejected = [(datetime.fromisoformat(r["timestamp"]), r["reason"])
                    for r in body["rejected"]]
        assert rejected == [
            (later.astimezone(), "future"),
            ((now - STEP).astimezone(), "out_of_range"),
            ((now - 2 * STEP).astimezone(), "out_of_range"),
        ]


def test_batch_utc_timestamps_stored_as_local_time(make_client):
    with make_client() as c:
        auth = _phone(c)
        instants = [(T0 + i * STEP).astimezone(UTC) for i in range(3)]
        sent = [{"timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "glucose_mg_dl": 120.0}
                for t in instants]
        assert _post(c, auth, sent).json()["accepted"] == 3
        history = c.get("/me/history", headers=auth).json()["readings"]
        stored = [datetime.fromisoformat(r["timestamp"]) for r in history]
        assert all(t.tzinfo is not None for t in stored)
        assert stored == instants


def test_batch_413_over_max_batch(make_client):
    with make_client(max_batch=3) as c:
        auth = _phone(c)
        r = _post(c, auth, _batch(4))
        assert r.status_code == 413 and "3" in r.json()["detail"]
        assert _post(c, auth, _batch(3)).json()["accepted"] == 3


def test_batch_requires_offset_aware_times(make_client):
    with make_client() as c:
        auth = _phone(c)
        readings = _batch(2)
        readings.append({"timestamp": (T0 + 5 * STEP).isoformat(), "glucose_mg_dl": 110.0})
        assert _post(c, auth, readings).status_code == 422
        assert c.get("/me/history", headers=auth).json()["readings"] == []


def test_batch_requires_profile(make_client):
    with make_client() as c:
        auth = _bearer(_signed_in_token(c))
        assert _post(c, auth, _batch(1)).status_code == 409


def test_alerts_after_id_returns_only_newer_oldest_first(make_client):
    with make_client() as c:
        auth = _phone(c)
        # Constant low forecasts raise hypo once history spans the look-back; each jump
        # past the gap limit then raises data_gap (cleared again by the readings after it).
        series = _batch(10) + _batch(10, start=30) + _batch(1, start=60)
        assert _post(c, auth, series).json()["accepted"] == 21

        newest_first = c.get("/me/alerts", headers=auth).json()
        assert [a["type"] for a in newest_first] == ["data_gap", "data_gap", "hypo"]
        ids = [a["id"] for a in reversed(newest_first)]
        assert ids == sorted(ids)

        after_first = c.get("/me/alerts", params={"after_id": ids[0]}, headers=auth).json()
        assert [a["id"] for a in after_first] == ids[1:]
        capped = c.get("/me/alerts", params={"after_id": 0, "limit": 2}, headers=auth).json()
        assert [a["id"] for a in capped] == ids[:2]
        assert c.get("/me/alerts", params={"after_id": ids[-1]}, headers=auth).json() == []
