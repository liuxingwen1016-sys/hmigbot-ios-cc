"""i2h-spec import facade for the shared bounded worker runner."""
from __future__ import annotations

import sys
from pathlib import Path

_shared = Path(__file__).resolve().parents[3] / "bin/scripts/pipeline"
if str(_shared) not in sys.path:
    sys.path.insert(0, str(_shared))

from bounded_workers import batch_items, run_bounded, utc_now  # type: ignore

__all__ = ["batch_items", "run_bounded", "utc_now"]
