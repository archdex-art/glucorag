import sqlite3
from datetime import UTC, datetime, timedelta

from glucorag.core.storage import SCHEMA, Storage

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=30)


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}


def test_v0_database_upgrades(tmp_path):
    path = tmp_path / "v0.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    assert "device" not in _columns(conn)
    conn.execute(
        "INSERT INTO users (email, password_hash, role, patient_id, created_at) "
        "VALUES ('a@example.com', 'h', 'person', 'p-a', ?)",
        (NOW.isoformat(),),
    )
    conn.execute(
        "INSERT INTO sessions VALUES ('tok', 1, ?, ?)", (NOW.isoformat(), LATER.isoformat())
    )
    conn.commit()
    conn.close()

    storage = Storage(path)
    storage.close()
    Storage(path).close()  # reopening an upgraded file is a no-op

    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == Storage.SCHEMA_VERSION == 1
    assert {"device", "last_used_at"} <= _columns(conn)
    rows = conn.execute("SELECT token_hash, user_id, device, last_used_at FROM sessions")
    assert rows.fetchall() == [("tok", 1, None, None)]
    conn.close()
    storage = Storage(path)
    user = storage.session_user("tok", NOW)
    assert user is not None and user.email == "a@example.com"
    storage.close()


def test_fresh_database_is_current(tmp_path):
    for target in (tmp_path / "fresh.db", ":memory:"):
        storage = Storage(target)
        assert storage._rows("PRAGMA user_version")[0][0] == 1
        storage.close()


def test_device_sessions_list_and_delete_scoped_to_user():
    s = Storage(":memory:")
    a = s.create_user("a@example.com", "h", "person", "p-a")
    b = s.create_user("b@example.com", "h", "person", "p-b")
    s.create_session("web-a", a.id, LATER)  # browser session: not a device
    s.create_session("dev-a", a.id, LATER, device="Pixel Watch")
    s.create_session("dev-b", b.id, LATER, device="Galaxy Watch")

    [da] = s.device_sessions(a.id)
    [db] = s.device_sessions(b.id)
    assert (da.device, db.device) == ("Pixel Watch", "Galaxy Watch")
    assert da.created_at.tzinfo is not None and da.last_used_at is None

    assert s.delete_device_session(a.id, db.id) is False
    assert s.session_user("dev-b", NOW) is not None
    assert s.delete_device_session(a.id, da.id) is True
    assert s.device_sessions(a.id) == []
    assert s.session_user("dev-a", NOW) is None
    assert s.session_user("web-a", NOW) is not None  # cookie session untouched


def test_touch_session_throttled():
    s = Storage(":memory:")
    a = s.create_user("a@example.com", "h", "person", "p-a")
    s.create_session("dev", a.id, LATER, device="Watch")

    s.touch_session("dev", NOW)
    assert s.device_sessions(a.id)[0].last_used_at == NOW
    s.touch_session("dev", NOW + timedelta(minutes=5))
    assert s.device_sessions(a.id)[0].last_used_at == NOW
    s.touch_session("dev", NOW + timedelta(minutes=11))
    assert s.device_sessions(a.id)[0].last_used_at == NOW + timedelta(minutes=11)
