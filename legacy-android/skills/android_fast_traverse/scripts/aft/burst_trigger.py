"""One optional, explicitly requested action between burst frames, never a macro."""
from __future__ import annotations

from . import capture, ui
from .device import DeviceError
from .drive import find, parse_steps, swipe_box


def prepare_trigger(dev, script: str):
    """Validate syntax now; resolve selectors freshly when the callback is invoked."""
    steps = parse_steps(script)
    if len(steps) != 1:
        raise ValueError("--trigger requires exactly one tap, long, back or swipe action")
    verb, arg = steps[0]
    if verb not in ("tap", "long", "back", "swipe"):
        raise ValueError("--trigger supports only tap, long, back or swipe")
    if verb == "back" and arg:
        raise ValueError("back takes no arguments")
    if verb in ("tap", "long"):
        spec = arg[1:].strip() if arg.startswith("!") else arg
        if not spec or spec in ("rid:", "desc:"):
            raise ValueError(f"{verb} requires a nonempty selector")
        if spec.startswith("@"):
            coords = [int(v) for v in spec[1:].split(",")]
            if len(coords) != 2 or min(coords) < 0:
                raise ValueError("coordinates must be @x,y with nonnegative integers")
    if verb == "swipe":
        direction, _, target = arg.partition(" ")
        target = target.strip()
        if direction not in ("up", "down", "left", "right"):
            raise ValueError("swipe direction must be up/down/left/right")
        if target.startswith("@"):
            box = [int(v) for v in target[1:].split(",")]
            if len(box) != 4 or min(box) < 0 or box[0] >= box[2] or box[1] >= box[3]:
                raise ValueError("swipe bounds must be @x1,y1,x2,y2 with positive area")
        elif target and (not target.startswith("rid:") or not target[4:]):
            raise ValueError("swipe target must be rid:<id> or @x1,y1,x2,y2")

    def trigger():
        obs = dev.dump("burst_trigger")
        if not obs.in_app:
            raise DeviceError("burst trigger refused: target package is not in the foreground")
        result = {"action": verb, "spec": arg, "from_activity": obs.activity,
                  "from_window": obs.focus.window, "observation_seq": obs.seq}
        if verb == "back":
            dev.back("burst_trigger")
        elif verb == "swipe":
            box = swipe_box(obs.nodes, dev.package, direction, target)
            if box is None:
                raise DeviceError(f"burst trigger target not found: {target}")
            axis = "horizontal" if direction in ("left", "right") else "vertical"
            fn = capture.swipe_forward if direction in ("up", "left") else capture.swipe_backward
            fn(dev, box, axis, "burst_trigger")
            result["bounds"] = list(box)
        else:
            force = arg.startswith("!")
            spec = arg[1:].strip() if force else arg
            node, xy = find(obs.nodes, dev.package, spec)
            if xy is None:
                raise DeviceError(f"burst trigger target not found: {spec}")
            hit = ui.node_at(obs.nodes, *xy) if node is None else node
            if hit is not None:
                node = ui.tap_target(obs.nodes, hit)
                word = ui.danger_word(ui.action_text(ui.label_of(obs.nodes, hit)), hit.desc, hit.short_rid,
                                      ui.action_text(ui.label_of(obs.nodes, node)), node.desc, node.short_rid)
                if word and not force:
                    raise DeviceError(f"burst trigger refused: danger word {word!r}; "
                                      "prefix ! only with explicit user authorization")
            (dev.long_press if verb == "long" else dev.tap)(*xy, "burst_trigger")
            result["xy"] = list(xy)
        return result

    return trigger
