"""Run the inference service.

    python -m glucorag.api --model-path models/shanghai-v1 [--db-path ...] [--clock data]

Unset options fall back to ``GLUCORAG_*`` environment variables (see ``ApiSettings``);
API keys come from ``GLUCORAG_API_KEYS`` only, so they never appear in process listings.
"""

import argparse
from pathlib import Path
from typing import Any

import uvicorn

from glucorag.api.app import create_app
from glucorag.api.settings import ApiSettings
from glucorag.core.logging import configure_logging


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--model-path", type=Path)
    p.add_argument("--db-path", type=Path)
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--clock", choices=["wall", "data"])
    p.add_argument("--watchdog-interval-s", type=float)
    p.add_argument("--log-level")
    args = p.parse_args(argv)
    overrides: dict[str, Any] = {k: v for k, v in vars(args).items() if v is not None}
    cfg = ApiSettings(**overrides)
    configure_logging(cfg.log_level)
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, log_config=None)


if __name__ == "__main__":
    main()
