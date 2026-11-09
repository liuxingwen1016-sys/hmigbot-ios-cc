"""Where the deliverables go inside the HarmonyOS project, and the round bookkeeping shared with the fixer.

<project>/spec/visual-verify/                         this skill's private space (the work directory)
  screenshots/android/<page_id>.png            Android baseline (frozen, reused by every round)
  screenshots/android/<page_id>.android.xml    its dump
  screenshots/android/<page_id>_seg_NN.png     further frames of a scrolled page
  screenshots/harmony/round-N/<page_id>.jpeg   HarmonyOS capture of this round
  screenshots/harmony/round-N/<page_id>.hmos.json
  screenshots/harmony/round-N/_evidence/       further frames (<page_id>__fK.jpeg / .hmos.json)
  screenshots/sbs/round-N/<page_id>.jpeg       side-by-side image (the image every fix file points at)
  screenshots/sbs/round-N/blocks/<page_id>_block_NN_sbs.png   further frames
Both sides run in the one state the app is in (no logged-out / logged-in split).
<project>/spec/fix/round-N/{ui,feat}/*.md             fix files; _index.md _summary.md _delta.md
<project>/spec/fix/_state.yaml                        current_round and the last verifier results
<project>/docs/autofix-log/round-N/batch.md           the fixer schedule of the round

Fix files and reports reference these paths relative to the project root; the walk workspace (walk/) and the
round workspace (rounds/) are never referenced from a fix file.
"""
from __future__ import annotations

import os
import re
import shutil

WORK = ("spec", "visual-verify")
STATE_KEYS = ("schema_version", "current_round", "last_verifier_run_at", "last_verifier_sources",
              "last_verifier_results")


def page_id(android_unit: str) -> str:
    """page_0024_SearchActivity / manual_0024_X -> P0024 (the Android baseline number: stable across rounds)."""
    m = re.search(r"_(\d{4})_", android_unit + "_")
    return "P" + (m.group(1) if m else "0000")


def fix_root(hmos_project: str, rnd: int) -> str:
    return os.path.join(hmos_project, "spec", "fix", f"round-{rnd}")


def rel(hmos_project: str, path: str | None) -> str | None:
    """Project-relative path for fix files (absolute when the file lives outside the project)."""
    if not path:
        return path
    a, root = os.path.abspath(path), os.path.abspath(hmos_project)
    return os.path.relpath(a, root) if a.startswith(root + os.sep) else a


# ---------------------------------------------------------------- canonical paths

def shots(store) -> str:
    return store.p("screenshots")


def android_png(store, cfg: dict, pid: str, k: int = 0) -> str:
    name = f"{page_id(pid)}.png" if k == 0 else f"{page_id(pid)}_seg_{k:02d}.png"
    return os.path.join(shots(store), "android", name)


def android_xml(store, cfg: dict, pid: str) -> str:
    return os.path.join(shots(store), "android", f"{page_id(pid)}.android.xml")


def harmony_jpeg(store, cfg: dict, rnd: int, pid: str, k: int = 0) -> str:
    d = os.path.join(shots(store), "harmony", f"round-{rnd}")
    return os.path.join(d, f"{page_id(pid)}.jpeg") if k == 0 else os.path.join(d, "_evidence", f"{page_id(pid)}__f{k}.jpeg")


def harmony_json(store, cfg: dict, rnd: int, pid: str, k: int = 0) -> str:
    return harmony_jpeg(store, cfg, rnd, pid, k)[: -len(".jpeg")] + ".hmos.json"


def sbs(store, cfg: dict, rnd: int, pid: str, k: int = 0) -> str:
    d = os.path.join(shots(store), "sbs", f"round-{rnd}")
    return os.path.join(d, f"{page_id(pid)}.jpeg") if k == 0 else \
        os.path.join(d, "blocks", f"{page_id(pid)}_block_{k:02d}_sbs.png")


def _copy(src: str | None, dst: str) -> str | None:
    if not src or not os.path.exists(src):
        return None
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src) or os.path.getsize(dst) == 0:
        shutil.copyfile(src, dst)
    return dst


def _jpeg(src: str | None, dst: str) -> str | None:
    if not src or not os.path.exists(src):
        return None
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        from PIL import Image
        Image.open(src).convert("RGB").save(dst, format="JPEG", quality=90)
    except Exception:
        shutil.copyfile(src, dst)
    return dst


def place(store, cfg: dict, rnd: int, it: dict) -> dict:
    """Copy one pair's captures into the canonical layout; returns the canonical paths per frame."""
    pid = it["android"]
    out = {"android": [], "harmony": [], "sbs": []}
    for k, png in enumerate(it.get("android_frames") or []):
        out["android"].append(_copy(png, android_png(store, cfg, pid, k)))
    xmls = it.get("android_xmls") or []
    if xmls:
        _copy(xmls[0], android_xml(store, cfg, pid))
    views = it.get("harmony_views") or []
    for k, png in enumerate(it.get("harmony_frames") or []):
        out["harmony"].append(_jpeg(png, harmony_jpeg(store, cfg, rnd, pid, k)))
        if k < len(views):
            _copy(views[k], harmony_json(store, cfg, rnd, pid, k))
    n = max(len(it.get("android_frames") or []), len(it.get("harmony_frames") or []))
    out["sbs"] = [sbs(store, cfg, rnd, pid, k) for k in range(n)]
    return out


# ---------------------------------------------------------------- spec/fix/_state.yaml

def state_path(hmos_project: str) -> str:
    return os.path.join(hmos_project, "spec", "fix", "_state.yaml")


def _blocks(text: str) -> list:
    """Top-level YAML blocks as (key, lines); enough to keep keys this skill does not own untouched."""
    blocks, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):", line)
        if m:
            cur = [m.group(1), [line]]
            blocks.append(cur)
        elif cur is not None:
            cur[1].append(line)
        else:
            blocks.append([None, [line]])
    return blocks


def current_round(hmos_project: str) -> int | None:
    try:
        text = open(state_path(hmos_project), encoding="utf-8").read()
    except OSError:
        return None
    m = re.search(r"^current_round:\s*(\d+)", text, re.M)
    return int(m.group(1)) if m else None


def first_round(hmos_project: str) -> int:
    """The round a new binding starts at: never on top of a round directory another run already wrote."""
    d = os.path.join(hmos_project, "spec", "fix")
    used = [int(m.group(1)) for n in (os.listdir(d) if os.path.isdir(d) else [])
            for m in [re.fullmatch(r"round-(\d+)", n)] if m]
    cur = current_round(hmos_project)
    if cur is not None and cur not in used:
        return cur
    return max(used) + 1 if used else 0


def write_state(hmos_project: str, rnd: int, results: dict, when: str) -> None:
    path = state_path(hmos_project)
    try:
        old = open(path, encoding="utf-8").read()
    except OSError:
        old = ""
    keep = [lines for key, lines in _blocks(old) if key not in STATE_KEYS]
    ours = ["schema_version: 2", f"current_round: {rnd}", f"last_verifier_run_at: '{when}'",
            "last_verifier_sources:", "- visual-verify", "last_verifier_results:", "  visual-verify:"]
    ours += [f"    {k}: {v}" for k, v in results.items()]
    text = "\n".join(ours + [ln for lines in keep for ln in lines]).rstrip() + "\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def set_current_round(hmos_project: str, rnd: int) -> None:
    path = state_path(hmos_project)
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        text = "schema_version: 2\n"
    if re.search(r"^current_round:", text, re.M):
        text = re.sub(r"^current_round:.*$", f"current_round: {rnd}", text, count=1, flags=re.M)
    else:
        text = text.rstrip() + f"\ncurrent_round: {rnd}\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
