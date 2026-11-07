"""Traversal profile: the model's only up-front input (small, app-specific)."""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_LIMITS = {
    "max_pages": 150,             # captured pages + view states + dialogs
    "max_depth": 8,
    "max_scrolls": 8,             # swipes per container
    "max_hscrolls": 12,           # swipes per read-only horizontal strip found without a profile entry (0 = off)
    "max_list_items": 3,          # list items explored per list container per page
    "max_candidates_per_page": 80,
    "max_views_per_page": 15,
    "max_instances_per_page": 2,  # first-screen shots of a known template showing different content (another detail)
    "max_minutes": 0,             # 0 = no wall-clock budget (pause with checkpoint when exceeded)
    "stall_minutes": 5,           # end the run when no new unit appeared for this long, model waits excluded (0 = off)
    "breaker": 3,                 # consecutive unrecovered failures before halting
    "settle_s": 0.35,             # pause after a swipe before dumping
    "match_threshold": 0.8,       # structure containment for "same page"
    "volatility_check_s": 2.5,    # wait before re-reading a 1-2 item text change (rotating banners vs real view states)
}

KNOWN_KEYS = {"package", "launch_component", "start_recipe", "root", "deny", "allow", "extra_danger_words",
              "business_readings", "extra_containers", "limits", "names", "notes", "skip_confirm_in_overlay",
              "grant_permissions", "grant_location"}


class ProfileError(ValueError):
    pass


def _selector_ok(sel) -> bool:
    return isinstance(sel, dict) and bool(set(sel) & {"rid", "text", "text_contains", "desc", "class"})


def validate(p: dict) -> dict:
    if not isinstance(p, dict) or not isinstance(p.get("package"), str) or not p["package"]:
        raise ProfileError("profile.package is required")
    unknown = set(p) - KNOWN_KEYS
    if unknown:
        raise ProfileError(f"unknown profile keys: {sorted(unknown)}")
    out = dict(p)
    out.setdefault("start_recipe", [])
    out.setdefault("deny", [])
    out.setdefault("allow", [])
    out.setdefault("extra_danger_words", [])
    out.setdefault("business_readings", [])
    out.setdefault("extra_containers", [])
    out.setdefault("names", {})
    out.setdefault("skip_confirm_in_overlay", True)
    limits = dict(DEFAULT_LIMITS)
    limits.update(p.get("limits") or {})
    bad = set(limits) - set(DEFAULT_LIMITS)
    if bad:
        raise ProfileError(f"unknown limits: {sorted(bad)}")
    out["limits"] = limits
    comp = out.get("launch_component")
    if comp and not comp.startswith(out["package"] + "/"):
        raise ProfileError("launch_component must belong to the target package")
    for i, rule in enumerate(out["start_recipe"]):
        if not isinstance(rule, dict) or "when" not in rule or not _selector_ok(rule["when"]):
            raise ProfileError(f"start_recipe[{i}] needs a 'when' selector")
        if not any(k in rule for k in ("tap", "back", "wait")):
            raise ProfileError(f"start_recipe[{i}] needs tap/back/wait")
        if "tap" in rule and not _selector_ok(rule["tap"]):
            raise ProfileError(f"start_recipe[{i}].tap must be a selector")
    for name in ("deny", "allow"):
        for i, rule in enumerate(out[name]):
            if not isinstance(rule, dict) or not (set(rule) & {"rid", "text", "text_contains", "desc", "class"}):
                raise ProfileError(f"{name}[{i}] needs at least one of rid/text/text_contains/desc/class")
    for i, r in enumerate(out["business_readings"]):
        if not isinstance(r, dict) or not r.get("name") or not _selector_ok(r.get("selector")):
            raise ProfileError(f"business_readings[{i}] needs name and selector")
    for i, c in enumerate(out["extra_containers"]):
        if not isinstance(c, dict) or not _selector_ok(c.get("selector")):
            raise ProfileError(f"extra_containers[{i}] needs a selector")
        if c.get("axis") not in (None, "vertical", "horizontal"):
            raise ProfileError(f"extra_containers[{i}].axis must be vertical or horizontal")
    if out.get("root") is not None and not _selector_ok(out["root"]):
        raise ProfileError("root must be a selector that is visible only on the root page")
    return out


def load(path: str | Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileError(f"profile is not valid JSON: {exc}") from exc
    return validate(data)


def merge_review(profile: dict, review: dict) -> dict:
    """Review decisions append allow/deny rules and labels; nothing is removed."""
    p = dict(profile)
    p["allow"] = list(profile.get("allow", [])) + list(review.get("allow", []))
    p["deny"] = list(profile.get("deny", [])) + list(review.get("deny", []))
    names = dict(profile.get("names", {}))
    names.update(review.get("labels", {}))
    p["names"] = names
    return validate(p)
