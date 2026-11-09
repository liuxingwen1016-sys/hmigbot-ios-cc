#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""metric_pack.py — 页面「度量包」生成器（零 LLM、零视觉；模型只读本脚本产出的 JSON）。

前景取最深像素、底色取频次直方图、ink bbox + bgSpread 不可靠标记、--probe 四模式；读两端 dump：
  Android: uiautomator dump XML（*.android.xml）
  HMOS:    uitest dumpLayout JSON（*.hmos.json）

职责边界：**只量测，不判断**。不判差异、不判 bug、
不推断沉浸式/锚定方向——判定归 metric_diff.py（按 tolerance.json）与源码 oracle。
每个像素值都带可靠性信号（bgSpread/unreliable），渐变/图片底上如实说"我不知道"。

用法:
  # 度量包模式（dump 必填；png 可缺——缺则只出几何，不出像素域）
  metric_pack.py --dump HomeFragment.android.xml --png HomeFragment.png \
                 [--density 3.0] [--platform auto|android|hmos] --out HomeFragment.metric.json

  # 探针模式（回答度量包默认输出答不了的追问；输出纯文本，无视觉模型可直接读）
  metric_pack.py --probe page.png --rect x1,y1,x2,y2 --mode colors|runs|ascii|filter \
                 [--color RRGGBB] [--tol 40] [--density 3.0]

density 说明：**必须显式传**。Android = `adb shell wm density`/160；
HMOS = display 密度/160（模拟器常见 3.0）。不传时本脚本**不反解**（反解出错比缺失更危险：
2.75 是真实合法密度，看着完全可信），vp 字段置 null 并在 meta 记 degraded，
下游 metric_diff 自动退到 ratio 口径比对。
"""
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter

try:
    from PIL import Image
except ImportError:
    Image = None

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
# 大区域逐像素太贵：面积超过阈值时按步长采样（对直方图/最深像素无损判定，只降精度不改性质）
_MAX_SAMPLES = 40000
_ASCII_RAMP = "@%#*+=-:. "  # 暗→亮


def parse_bounds(s):
    if not s:
        return None
    m = _BOUNDS_RE.search(s)
    if not m:
        return None
    x1, y1, x2, y2 = (int(g) for g in m.groups())
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


# ---------------------------------------------------------------------------
# dump 解析：两端统一产出节点列表（含 Image/无文本 leaf——这点与结构 oracle
# 只留 text-leaf 不同：图标/图片正是度量包的重点对象）
# ---------------------------------------------------------------------------
def collect_android(path):
    root = ET.parse(path).getroot()
    nodes, screen = [], [1, 1]

    def walk(node, depth):
        a = node.attrib
        b = parse_bounds(a.get("bounds"))
        kids = [c for c in node if c.tag == "node"]
        if b:
            screen[0] = max(screen[0], b[2])
            screen[1] = max(screen[1], b[3])
        keep = b and (not kids or a.get("clickable") == "true"
                      or "Image" in a.get("class", ""))
        if keep:
            nodes.append({
                "text": a.get("text", "").strip(),
                "type": a.get("class", "").split(".")[-1] or "?",
                "id": (a.get("resource-id") or "").split("/")[-1],
                "desc": a.get("content-desc", "").strip(),
                "clickable": a.get("clickable") == "true",
                "bounds": list(b),
            })
        for c in kids:
            walk(c, depth + 1)

    walk(root, 0)
    return nodes, tuple(screen)


def collect_hmos(path):
    root = json.load(open(path))
    nodes, screen = [], [1, 1]

    def walk(node, depth):
        attrs = node.get("attributes", {})
        kids = node.get("children", []) or []
        b = parse_bounds(attrs.get("bounds"))
        if b:
            screen[0] = max(screen[0], b[2])
            screen[1] = max(screen[1], b[3])
        visible = str(attrs.get("visible", "true")).lower() != "false"
        t = attrs.get("type", "?")
        keep = b and visible and (not kids
                                  or str(attrs.get("clickable", "")).lower() == "true"
                                  or t == "Image")
        if keep:
            nodes.append({
                "text": (attrs.get("text") or "").strip(),
                "type": t,
                "id": attrs.get("id") or attrs.get("key") or "",
                "desc": (attrs.get("description") or "").strip(),
                "clickable": str(attrs.get("clickable", "")).lower() == "true",
                "bounds": list(b),
            })
        for c in kids:
            walk(c, depth + 1)

    walk(root, 0)
    return nodes, tuple(screen)


# ---------------------------------------------------------------------------
# 像素量测
#   bg  = 区域内频次最高的颜色（直方图 top1）
#   fg  = 区域内亮度最低的颜色（文字/描边的"主色"永远不在四角，也未必是均值）
#   ink = 与 bg 色距 > tol 的像素外接矩形
#   bgSpread = 边框环上偏离 bg 的比例；> 阈值 → unreliable（渐变/图片底，ink 不可信）
# ---------------------------------------------------------------------------
def _hex(c):
    return "#%02X%02X%02X" % (c[0], c[1], c[2])


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])


def measure_region(im, x1, y1, x2, y2, tol=40, spread_gate=0.35):
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0:
        return None
    step = 1
    while (w // step) * (h // step) > _MAX_SAMPLES:
        step += 1
    hist = Counter()
    darkest, dark_l = (255, 255, 255), 1e9
    px = im.load()
    for y in range(y1, y2, step):
        for x in range(x1, x2, step):
            c = px[x, y][:3]
            hist[c] += 1
            l = _lum(c)
            if l < dark_l:
                dark_l, darkest = l, c
    bg = hist.most_common(1)[0][0]
    # bgSpread：边框环采样
    ring, off_bg = 0, 0
    for x in range(x1, x2, max(1, step)):
        for y in (y1, y2 - 1):
            ring += 1
            if _dist(px[x, y][:3], bg) > tol:
                off_bg += 1
    for y in range(y1, y2, max(1, step)):
        for x in (x1, x2 - 1):
            ring += 1
            if _dist(px[x, y][:3], bg) > tol:
                off_bg += 1
    spread = off_bg / ring if ring else 0.0
    # ink bbox
    ix1, iy1, ix2, iy2, n_ink = x2, y2, x1, y1, 0
    for y in range(y1, y2, step):
        for x in range(x1, x2, step):
            if _dist(px[x, y][:3], bg) > tol:
                n_ink += 1
                ix1, iy1 = min(ix1, x), min(iy1, y)
                ix2, iy2 = max(ix2, x + step), max(iy2, y + step)
    ink = None
    if n_ink:
        ink = {"bounds": [ix1, iy1, ix2, iy2], "w": ix2 - ix1, "h": iy2 - iy1}
    return {
        "bg": _hex(bg),
        "fg": _hex(darkest),
        "ink": ink,
        "bgSpread": round(spread, 3),
        "unreliable": spread > spread_gate,
        "sampled_step": step,
    }


# ---------------------------------------------------------------------------
# 度量包主流程
# ---------------------------------------------------------------------------
def build_pack(args):
    platform = args.platform
    if platform == "auto":
        platform = "hmos" if args.dump.endswith(".json") else "android"
    nodes, screen = (collect_hmos if platform == "hmos" else collect_android)(args.dump)

    density = args.density
    degraded = []
    if not density:
        degraded.append("density_missing: vp 字段全 null，下游只能按 ratio 口径比对")

    im = None
    sx = sy = 1.0
    if args.png and os.path.exists(args.png):
        if Image is None:
            degraded.append("pillow_missing: 无像素域（pip3 install Pillow）")
        else:
            im = Image.open(args.png).convert("RGB")
            sx = im.width / screen[0]
            sy = sx  # vvs: dump bounds are screen pixels; a PNG taller than the dump only adds system bars below
            if abs(im.height / screen[1] - sx) > 0.05 and im.height < screen[1] * sx - 2:
                degraded.append(f"aspect_mismatch: png/dump 缩放比 x={sx:.3f} y={im.height / screen[1]:.3f} 不一致")
    else:
        degraded.append("png_missing: 无像素域（仅几何）")

    out_nodes = []
    for i, n in enumerate(nodes):
        x1, y1, x2, y2 = n["bounds"]
        w, h = x2 - x1, y2 - y1
        rec = dict(n)
        rec["key"] = f"{i}:{n['type']}:{(n['id'] or n['text'] or n['desc'])[:24]}"
        rec["ratio"] = {
            "cx": round((x1 + x2) / 2 / screen[0], 4),
            "cy": round((y1 + y2) / 2 / screen[1], 4),
            "w": round(w / screen[0], 4),
            "h": round(h / screen[1], 4),
        }
        rec["vp"] = ({"w": round(w / density, 1), "h": round(h / density, 1),
                      "x": round(x1 / density, 1), "y": round(y1 / density, 1)}
                     if density else None)
        if im is not None:
            px1, py1 = int(x1 * sx), int(y1 * sy)
            px2, py2 = min(im.width, int(x2 * sx)), min(im.height, int(y2 * sy))
            m = measure_region(im, max(0, px1), max(0, py1), px2, py2, tol=args.tol)
            if m and m["ink"] and density:
                m["ink"]["h_vp"] = round(m["ink"]["h"] / sy / density, 1)
                m["ink"]["w_vp"] = round(m["ink"]["w"] / sx / density, 1)
            rec["pixel"] = m
        else:
            rec["pixel"] = None
        out_nodes.append(rec)

    pack = {
        "schema": "metric_pack/1",
        "platform": platform,
        "dump": os.path.abspath(args.dump),
        "png": os.path.abspath(args.png) if args.png else None,
        "density": density,
        "screen": {"w": screen[0], "h": screen[1]},
        "png_scale": {"x": round(sx, 4), "y": round(sy, 4)},
        "degraded": degraded,
        "node_count": len(out_nodes),
        "nodes": out_nodes,
    }
    if args.out:
        with open(args.out, "w") as f:
            json.dump(pack, f, ensure_ascii=False, indent=1)
        print(f"[metric_pack] {platform} {len(out_nodes)} nodes -> {args.out}"
              + (f"  ⚠ {'; '.join(degraded)}" if degraded else ""))
    else:
        json.dump(pack, sys.stdout, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------------------
# 探针模式（colors/runs/ascii/filter，纯文本输出）
# ---------------------------------------------------------------------------
def run_probe(args):
    if Image is None:
        sys.exit("需要 Pillow: pip3 install Pillow")
    im = Image.open(args.probe).convert("RGB")
    r = [int(v) for v in (args.rect or f"0,0,{im.width},{im.height}").split(",")]
    x1, y1 = max(0, r[0]), max(0, r[1])
    x2, y2 = min(im.width, r[2]), min(im.height, r[3])
    d = args.density
    vp = (lambda n: f" ({n / d:.1f}vp)") if d else (lambda n: "")
    px = im.load()

    if args.mode == "colors":
        hist = Counter()
        darkest, dl = (255, 255, 255), 1e9
        for y in range(y1, y2):
            for x in range(x1, x2):
                c = px[x, y][:3]
                hist[c] += 1
                if _lum(c) < dl:
                    dl, darkest = _lum(c), c
        top = "  ".join(f"{_hex(c)}×{n}" for c, n in hist.most_common(4))
        print(f"rect [{x1},{y1}][{x2},{y2}]\n  darkest : {_hex(darkest)}\n  top     : {top}")
        print("  注: 文字/描边取 darkest，底色取 top 里占比最大的那个")
    elif args.mode == "runs":
        print(f"rect [{x1},{y1}][{x2},{y2}]  暗像素逐行区间 (lum<170)")
        for y in range(y1, y2):
            runs, s = [], -1
            for x in range(x1, x2 + 1):
                dark = x < x2 and _lum(px[x, y][:3]) < 170
                if dark and s < 0:
                    s = x
                if not dark and s >= 0:
                    runs.append(f"{s}-{x - 1}")
                    s = -1
            if runs:
                print(f"  y={y}: {' '.join(runs)}")
    elif args.mode == "ascii":
        cols = min(64, x2 - x1)
        rows = max(1, int((y2 - y1) * cols / (x2 - x1) * 0.5))
        for ry in range(rows):
            line = ""
            for rx in range(cols):
                sxp = x1 + int(rx * (x2 - x1) / cols)
                syp = y1 + int(ry * (y2 - y1) / rows)
                l = _lum(px[sxp, syp][:3])
                line += _ASCII_RAMP[min(len(_ASCII_RAMP) - 1, int(l / 256 * len(_ASCII_RAMP)))]
            print(line)
    elif args.mode == "filter":
        if not args.color:
            sys.exit("--mode filter 需要 --color RRGGBB")
        tc = tuple(int(args.color[i:i + 2], 16) for i in (0, 2, 4))
        fx1, fy1, fx2, fy2, n = x2, y2, x1, y1, 0
        for y in range(y1, y2):
            for x in range(x1, x2):
                if _dist(px[x, y][:3], tc) <= args.tol:
                    n += 1
                    fx1, fy1 = min(fx1, x), min(fy1, y)
                    fx2, fy2 = max(fx2, x), max(fy2, y)
        if n:
            print(f"color #{args.color} bbox [{fx1},{fy1}][{fx2},{fy2}] "
                  f"w={fx2 - fx1}{vp(fx2 - fx1)} h={fy2 - fy1}{vp(fy2 - fy1)} px={n}")
        else:
            print(f"color #{args.color} 在区域内 0 命中 (tol={args.tol})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump")
    ap.add_argument("--png")
    ap.add_argument("--out")
    ap.add_argument("--platform", default="auto", choices=["auto", "android", "hmos"])
    ap.add_argument("--density", type=float, default=0)
    ap.add_argument("--tol", type=int, default=40)
    ap.add_argument("--probe")
    ap.add_argument("--rect")
    ap.add_argument("--mode", default="colors", choices=["colors", "runs", "ascii", "filter"])
    ap.add_argument("--color")
    args = ap.parse_args()
    if args.probe:
        run_probe(args)
    elif args.dump:
        build_pack(args)
    else:
        ap.error("需要 --dump（度量包）或 --probe（探针）之一")


if __name__ == "__main__":
    main()
