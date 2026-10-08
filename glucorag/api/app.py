"""FastAPI application: loads the model artifact once at startup and serves the runtime.

    GLUCORAG_MODEL_PATH=models/shanghai-v1 python -m glucorag.api

``GLUCORAG_MODEL_PATH`` may also be the registry root (``models``); the version named in
``models/CURRENT`` (written by ``glucorag.release`` on promotion) is then served.

Browsers sign in with accounts (``/auth``); people use ``/me``, clinicians the staff
routes. ``GLUCORAG_API_KEYS`` (optional) grants devices and scripts staff access.
``app`` (module level) reads its settings from the environment at startup, so
``uvicorn glucorag.api.app:app`` works as well.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from glucorag.api import auth, dashboard, downloads, me
from glucorag.api.routes import public, router
from glucorag.api.settings import ApiSettings
from glucorag.api.web import SecurityHeaders, mount_dashboard
from glucorag.core.accounts import LoginThrottle
from glucorag.core.logging import log_event
from glucorag.core.registry import resolve_artifact
from glucorag.core.storage import Storage
from glucorag.inference.engine import ForecastEngine
from glucorag.service import DataClock, GlucoseService, WallClock

log = logging.getLogger("glucorag.api")


def build_service(cfg: ApiSettings) -> GlucoseService:
    if cfg.model_path is None:
        raise RuntimeError("GLUCORAG_MODEL_PATH is not set")
    engine = ForecastEngine.from_artifact(
        resolve_artifact(cfg.model_path), cfg.data_gap_min, cfg.device
    )
    clock = DataClock() if cfg.clock == "data" else WallClock()
    return GlucoseService(engine, Storage(cfg.db_path), cfg.service_config(), clock)


async def _watchdog_loop(service: GlucoseService, interval_s: float) -> None:
    while True:
        await asyncio.sleep(interval_s)
        try:
            await asyncio.to_thread(service.watchdog)
        except Exception:
            log.exception("watchdog failed")


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    static_cfg = settings or ApiSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg = settings or ApiSettings()
        service = build_service(cfg)
        app.state.service = service
        # Keys are for devices and scripts; browsers use account sessions. No keys simply
        # means no key-based access, never unauthenticated access.
        app.state.api_keys = cfg.api_keys
        app.state.max_batch = cfg.max_batch
        app.state.login_throttle = LoginThrottle()
        app.state.allow_signup = cfg.allow_signup
        app.state.cookie_secure = cfg.cookie_secure
        app.state.session_days = cfg.session_days
        app.state.import_max_days = cfg.import_max_days
        app.state.public_url = cfg.public_url
        app.state.phone_apk_path = cfg.phone_apk_path
        app.state.watch_apk_path = cfg.watch_apk_path
        app.state.model_path = resolve_artifact(cfg.model_path or "")
        app.state.sim_report = cfg.sim_report
        app.state.clock = cfg.clock
        app.state.started_at = datetime.now(UTC)
        log_event(log, "service_started", model_version=service.model_version,
                  model_path=str(cfg.model_path), db_path=str(cfg.db_path), clock=cfg.clock,
                  patients=len(service.storage.profiles()))
        task = (
            asyncio.create_task(_watchdog_loop(service, cfg.watchdog_interval_s))
            if cfg.watchdog_interval_s > 0 else None
        )
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            service.storage.close()

    app = FastAPI(title="GlucoRAG EPS-TFT inference service", lifespan=lifespan)
    app.add_middleware(SecurityHeaders)
    app.include_router(public)
    app.include_router(router)
    app.include_router(dashboard.router)
    app.include_router(auth.router)
    app.include_router(me.router)
    app.include_router(downloads.router)
    mount_dashboard(app, static_cfg.web_dir)
    return app


app = create_app()
