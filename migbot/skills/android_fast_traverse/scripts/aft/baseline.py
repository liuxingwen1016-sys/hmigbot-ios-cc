"""Validate one output baseline once per invocation, before navigation or capture."""
from __future__ import annotations

FRESH = "; start over in this OUT with `run --fresh` (the old traversal is archived under _aft/previous/)"


def ensure_baseline(dev, state: dict, package: str) -> None:
    previous_package = state.get("package")
    if previous_package and previous_package != package:
        raise ValueError("output belongs to another package; use a separate baseline directory")
    current_app, current_density = dev.app_version(), dev.density()
    previous_app = state.get("app") or {}
    for field in ("versionName", "versionCode", "lastUpdateTime"):
        old = previous_app.get(field)
        if old and current_app.get(field) != old:
            raise ValueError(f"application baseline {field} changed or unavailable (reinstalled or another build)"
                             + FRESH)
    previous_density = state.get("density")
    if previous_density and current_density != previous_density:
        raise ValueError("device density changed or unavailable" + FRESH)
    state["package"] = package
    state["app"] = previous_app or current_app
    state["density"] = previous_density or current_density
