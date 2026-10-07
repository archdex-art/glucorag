from datetime import timedelta

from _runtime import STEP, T0, ManualClock, profile, tiny_artifact

from glucorag.core.storage import Storage
from glucorag.inference.engine import ForecastEngine
from glucorag.service import GlucoseService, ServiceConfig

# Constant forecast: q0.25 = 60 mg/dL at every horizon -> a hypo flag on every forecast.
HYPO = [40, 50, 60, 90, 120, 130, 140]


def _svc(tmp_path, levels=HYPO):
    path = tiny_artifact(tmp_path / "models", levels)
    cfg = ServiceConfig()
    engine = ForecastEngine.from_artifact(path, cfg.data_gap_min)
    svc = GlucoseService(engine, Storage(":memory:"), cfg, ManualClock(T0 + timedelta(days=1)))
    svc.register_profile(profile())
    return svc


def _rows(start, n, value=110.0):
    return [(T0 + (start + i) * STEP, value) for i in range(n)]


def test_backfill_accepts_any_order_and_matches_a_live_stream(tmp_path):
    live = _svc(tmp_path / "live")
    for t, v in _rows(0, 12):
        live.ingest("p1", t, v)
    batch = _svc(tmp_path / "batch")
    shuffled = list(reversed(_rows(0, 12)))
    result = batch.backfill("p1", shuffled)
    assert result.added == 12
    assert result.outcomes == {"warming_up": 7, "predicted": 5}
    assert [p.t0 for p in batch.storage.predictions("p1")] == [
        p.t0 for p in live.storage.predictions("p1")
    ]
    # Same alert timeline: one hypo at the first forecast, then de-duplicated.
    assert [(a.type, a.t_raised) for a in batch.storage.alerts("p1")] == [
        (a.type, a.t_raised) for a in live.storage.alerts("p1")
    ]


def test_backfill_merges_older_history_under_existing_warm_up(tmp_path):
    svc = _svc(tmp_path)
    for t, v in _rows(20, 5):  # 5 recent readings: still warming up, no forecast
        svc.ingest("p1", t, v)
    assert svc.storage.predictions("p1") == []
    result = svc.backfill("p1", _rows(0, 25))  # full history incl. the 5 already stored
    assert result.added == 20 and result.outcomes["already_present"] == 5
    t0s = [p.t0 for p in svc.storage.predictions("p1")]
    # Forecasts replayed over the merged timeline, including after the old warm-up rows.
    assert t0s[0] == T0 + 7 * STEP and t0s[-1] == T0 + 24 * STEP and len(t0s) == 18
    assert svc.buffer.last_timestamp("p1") == T0 + 24 * STEP


def test_backfill_replaces_forecasts_made_before_older_rows_arrived(tmp_path):
    svc = _svc(tmp_path)
    # Live stream with a 75-min hole: forecasts after the hole are suspended (data gap).
    for t, v in _rows(0, 8) + _rows(13, 8):
        svc.ingest("p1", t, v)
    before = {p.t0 for p in svc.storage.predictions("p1")}
    assert T0 + 13 * STEP not in before
    svc.backfill("p1", _rows(8, 5))  # fill the hole
    after = {p.t0 for p in svc.storage.predictions("p1")}
    assert {T0 + i * STEP for i in range(7, 21)} == after
    gaps = [a for a in svc.storage.alerts("p1") if a.type == "data_gap"]
    assert gaps == []  # replayed timeline has no gap any more


def test_backfill_rejects_like_live_ingest_but_not_for_ordering(tmp_path):
    svc = _svc(tmp_path)
    future = T0 + timedelta(days=2)
    result = svc.backfill("p1", [(T0, float("nan")), (T0 + STEP, -1.0), (future, 100.0),
                                 (T0 + 2 * STEP, 100.0), (T0 + 2 * STEP, 101.0)])
    assert result.outcomes == {
        "rejected_non_finite": 1, "rejected_non_positive": 1, "rejected_future": 1,
        "warming_up": 1, "already_present": 1,
    }
    assert result.added == 1
