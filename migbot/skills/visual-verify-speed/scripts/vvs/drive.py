"""Hand-driven HarmonyOS steps, for the states the walk cannot reproduce (first launch, text input, login).

One `drive` call runs a whole chain; it stops at the first failed step (prints STOPPED at step N, exit 1).
Steps (separated by ';'):
  outline                         print the current screen
  tap <text>|desc:<d>|id:<id>|@x,y   tap a control (a danger-word label needs '!' in front: tap !删除); a text off
                                  screen in a horizontally scrolling row is searched by swiping that row
  long <same as tap>
  back
  swipe up|down|left|right
  text <content>                  type into the focused field (else at the last tap); Chinese works
  wait <seconds>
  start                           cold start + start_recipe to the root page
  clear                           clear app data (only when the user asked for it)
  capture pair=<android page_id> [label]   capture the screen as the HarmonyOS side of that Android unit
  capture [label]                 capture an extra screen with no Android counterpart
"""
from __future__ import annotations

import re
import shlex

from . import hcapture, hui
from .android import Step
from .hdevice import DeviceError
from .popup import PopupStop
from .store import read_json, write_json, now_iso


def _target(obs, arg: str):
    if arg.startswith("@"):
        x, y = (int(v) for v in arg[1:].split(","))
        return (x, y), f"@{x},{y}"
    forced = arg.startswith("!")
    if forced:
        arg = arg[1:]
    if arg.startswith("desc:"):
        sel = {"desc": arg[5:]}
    elif arg.startswith("id:"):
        sel = {"id": arg[3:]}
    else:
        sel = {"text": arg}
    hits = hui.select(obs.nodes, sel)
    if not hits:
        hits = hui.select(obs.nodes, {"text_contains": arg}) if "text" in sel else []
        labels = {hui.norm_label(h.text or h.desc) for h in hits}
        if len(labels) != 1:
            return None, f"NOT FOUND {arg}"
    n = hui.tap_target(obs.nodes, hits[0])
    label = hui.label_of(obs.nodes, n)
    if not forced and hui.danger_word(label):
        return None, f"REFUSED {label}: write tap !{label} only when the user allowed it"
    return hui.tap_point(obs.nodes, hits[0], obs.bundle) or n.center, label  # the part a bar/layer does not cover


def run(dev, store, walker, plan, script: str, allow_clear: bool = False, log=print) -> int:
    steps = [s.strip() for s in script.split(";") if s.strip()]
    trail = read_json(f"{store.vvs}/drive_trail.json", [])
    extra_no = len([m for m in store.index() if not m.get("pair", {}).get("android")]) + 1
    obs = walker.settle(walker.observe("drive"), "drive")
    for i, step in enumerate(steps, 1):
        verb, _, arg = step.partition(" ")
        arg = arg.strip()
        try:
            if verb == "outline":
                log(hui.outline(obs.nodes, walker.bundle) if obs else "(no observation)")
                continue
            if verb in ("tap", "long"):
                if obs is None:
                    raise DeviceError("no observation")
                xy, label = _target(obs, arg)
                if xy is None and label.startswith("NOT FOUND") and not arg.startswith(("@", "desc:", "id:")):
                    # off screen in a horizontally scrolling row (category tabs): swipe the rows to find it
                    hit, obs = walker.search_row(Step(action="tap", label=arg.lstrip("!")), obs, "drive", any_row=True)
                    if hit is not None:
                        xy, label = _target(obs, arg)
                if xy is None:
                    log(f"STOPPED at step {i}: {label}")
                    return 1
                (dev.tap if verb == "tap" else dev.long_press)(xy[0], xy[1], "drive")
                trail.append({"action": verb, "label": label, "xy": list(xy)})
            elif verb == "back":
                dev.back("drive")
                trail.append({"action": "back"})
            elif verb == "swipe":
                c = hui.primary_container(obs.nodes, walker.bundle) if obs else None
                box = c.bounds if c else (0, 0, *hui.screen_size(obs.nodes))
                axis = "vertical" if arg in ("up", "down") else "horizontal"
                fwd = arg in ("up", "left")
                (hcapture.swipe_forward if fwd else hcapture.swipe_backward)(dev, box, axis, "drive")
                trail.append({"action": "swipe", "direction": arg})
            elif verb == "text":
                field = [n for n in (obs.nodes if obs else []) if n.type in hui.INPUT_TYPES and not n.covered
                         and n.focused and n.area > 0]
                dev.input_text(arg, "drive", field[0].center if field else None)
                trail.append({"action": "text", "length": len(arg)})
            elif verb == "wait":
                dev.pause(float(arg or 1), "drive")
            elif verb == "start":
                obs = walker.cold_start()
                trail = []
                if obs is None:
                    log(f"STOPPED at step {i}: the root page did not appear")
                    return 1
                continue
            elif verb == "clear":
                if not allow_clear:
                    log(f"STOPPED at step {i}: clear needs --allow-clear (only when the user asked to reset data)")
                    return 1
                dev.clear_data("drive")
                trail = []
            elif verb == "capture":
                m = re.match(r"pair=(\S+)\s*(.*)", arg)
                pid, label = (m.group(1), m.group(2)) if m else (None, arg)
                if pid and pid not in plan.units:
                    log(f"STOPPED at step {i}: unknown Android unit {pid}")
                    return 1
                obs = walker.wait_loaded(walker.settle(walker.observe("drive"), "drive"))
                if obs is None or not obs.in_app:
                    log(f"STOPPED at step {i}: the app is not in front")
                    return 1
                if pid:
                    walker.capture_unit(pid, obs, "manual", label, [t.get("action") for t in trail])
                    walker.us(pid)["manual_trail"] = list(trail)
                else:
                    res = hcapture.capture(dev, walker.bundle, obs, walker.lim["max_swipes"])
                    meta = {"label": label or "extra", "kind": "extra", "pair": {},
                            "harmony": {"bundle": obs.bundle, "page_path": obs.page_path, "overlay": obs.overlay},
                            "density_factor": walker.state.get("density"), "click_path": list(trail),
                            "capture": {"frames": len(res.frames), "stop": res.stop}}
                    saved = store.write_unit(walker.rnd, res.frames, meta, None, obs.page_path, extra_no)
                    extra_no += 1
                    log(f"[vvs] extra -> {saved['unit_dir']}")
                walker.save()
                continue
            else:
                log(f"STOPPED at step {i}: unknown step '{verb}'")
                return 1
        except DeviceError as exc:
            log(f"STOPPED at step {i}: {exc}")
            return 1
        except PopupStop as exc:
            log(f"STOPPED at step {i}: {exc.status}: {exc.reason}")
            return 1
        obs = walker.settle(walker.observe("drive"), "drive")
    write_json(f"{store.vvs}/drive_trail.json", trail)
    store.event("drive", {"steps": len(steps), "at": now_iso()})
    return 0
