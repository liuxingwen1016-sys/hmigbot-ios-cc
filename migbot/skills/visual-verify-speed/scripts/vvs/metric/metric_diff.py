#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""metric_diff.py — 度量对比判官（零 LLM；compare() 供进程内调用）。

输入: 两端 metric_pack JSON + （可选）结构对比的 struct.json + tolerance.json
输出: 与判图结果同 schema 的 differences[]（category/severity/is_migration_bug/description/
      root_cause_hint + source="metric_oracle"）+ uncovered[]（无视觉真覆盖不了的维度逐条记账，
      绝不静默假 PASS）。

判定维度（图标语义和兄弟顺序不在本脚本，由判图和结构 oracle 负责）：
  color_fg / color_bg  ΔE(CIE76, Lab)         —— 文字/前景色、底色
  size                 vp 绝对差（density 双全）/ ratio 差（退化口径）
  position             质心 ratio 差
  font                 text 节点 ink 高度 vp 差（字号代理）
  （missing/extra/order 来自 struct.json 直并；spacing 由 position+size 间接覆盖）

用法:
  metric_diff.py --android a.metric.json --hmos h.metric.json --page-id HomeFragment \
                 [--struct page.struct.json] [--tolerance tolerance.json] --out page.mdiff.json
"""
import argparse
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# 颜色: hex -> Lab -> ΔE(CIE76)
# ---------------------------------------------------------------------------
def _hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb2lab(rgb):
    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    r, g, b = [v / 255.0 for v in rgb]
    r, g, b = [((v + 0.055) / 1.055) ** 2.4 if v > 0.04045 else v / 12.92 for v in (r, g, b)]
    X = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    Y = (r * 0.2126 + g * 0.7152 + b * 0.0722)
    Z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883
    fx, fy, fz = f(X), f(Y), f(Z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(hex_a, hex_b):
    la, lb = _rgb2lab(_hex2rgb(hex_a)), _rgb2lab(_hex2rgb(hex_b))
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(la, lb)))


# ---------------------------------------------------------------------------
# 节点配对：text 唯一 → id 唯一 → 同类最近邻（ratio 距离 < pair_dist_ratio）
# 跨端类型等价表：Android class 与 ArkUI type 不同名，最近邻按归一化类比对
# ---------------------------------------------------------------------------
_TYPE_EQ = {
    "TextView": "Text", "ImageView": "Image", "ImageButton": "Image",
    "EditText": "TextInput", "Button": "Button", "CheckBox": "Checkbox",
    "Switch": "Toggle", "SeekBar": "Slider", "ProgressBar": "Progress",
    "RecyclerView": "List", "ListView": "List", "ScrollView": "Scroll",
    "WebView": "Web", "VideoView": "Video", "RadioButton": "Radio",
}


def _norm_type(t):
    return _TYPE_EQ.get(t, t)


def pair_nodes(a_nodes, h_nodes, max_dist):
    pairs, used_h = [], set()

    def by_uniq(field):
        from collections import Counter
        av = Counter(n[field] for n in a_nodes if n[field])
        hv = Counter(n[field] for n in h_nodes if n[field])
        for an in a_nodes:
            v = an[field]
            if not v or av[v] != 1 or hv.get(v) != 1 or an.get("_p"):
                continue
            for hn in h_nodes:
                if hn[field] == v and id(hn) not in used_h:
                    an["_p"] = True
                    used_h.add(id(hn))
                    pairs.append((an, hn, field))
                    break

    by_uniq("text")
    by_uniq("id")
    for an in a_nodes:
        if an.get("_p"):
            continue
        best, bd = None, max_dist
        for hn in h_nodes:
            if id(hn) in used_h or _norm_type(hn["type"]) != _norm_type(an["type"]):
                continue
            d = math.hypot(an["ratio"]["cx"] - hn["ratio"]["cx"],
                           an["ratio"]["cy"] - hn["ratio"]["cy"])
            if d < bd:
                best, bd = hn, d
        if best is not None:
            an["_p"] = True
            used_h.add(id(best))
            pairs.append((an, best, "proximity"))
    return pairs


def sev(exceed, tol_cfg):
    if exceed >= tol_cfg["severity_high_x"]:
        return "high"
    if exceed >= tol_cfg["severity_medium_x"]:
        return "medium"
    return "low"


def label(n):
    return n["text"] or n["id"] or n["desc"] or f"{n['type']}@({n['ratio']['cx']},{n['ratio']['cy']})"


def compare(A, H, T, page_id, struct=None):
    """Two metric packs -> metric_diff/1 dict (same rules as the CLI)."""
    diffs, uncovered = [], []

    vp_ok = bool(A.get("density")) and bool(H.get("density"))
    if not vp_ok:
        uncovered.append({"dim": "size_vp", "why": "任一端 density 缺失，尺寸退 ratio 口径（能抓相对失衡，抓不了绝对 vp 偏差）"})
    for side, P in (("android", A), ("hmos", H)):
        for d in P.get("degraded", []):
            uncovered.append({"dim": "pixel", "why": f"{side}: {d}"})

    pairs = pair_nodes(A["nodes"], H["nodes"], T["pair_dist_ratio"])

    for an, hn, how in pairs:
        name = label(an)
        # --- position ---
        dx = abs(an["ratio"]["cx"] - hn["ratio"]["cx"])
        dy = abs(an["ratio"]["cy"] - hn["ratio"]["cy"])
        dpos = max(dx, dy)
        if dpos > T["pos_ratio"]:
            diffs.append({
                "category": "layout", "severity": sev(dpos / T["pos_ratio"], T),
                "is_migration_bug": True, "source": "metric_oracle",
                "description": f"「{name}」位置偏移: Android 质心({an['ratio']['cx']},{an['ratio']['cy']}) "
                               f"vs HMOS({hn['ratio']['cx']},{hn['ratio']['cy']})，Δ={dpos:.3f}（容差 {T['pos_ratio']}）",
                "measured": {"pos_delta_ratio": round(dpos, 4), "pair_by": how},
            })
        # --- size ---
        if vp_ok:
            dw = abs(an["vp"]["w"] - hn["vp"]["w"])
            dh = abs(an["vp"]["h"] - hn["vp"]["h"])
            dsz, unit, tol = max(dw, dh), "vp", T["size_vp"]
        else:
            dw = abs(an["ratio"]["w"] - hn["ratio"]["w"])
            dh = abs(an["ratio"]["h"] - hn["ratio"]["h"])
            dsz, unit, tol = max(dw, dh), "ratio", T["size_ratio"]
        if dsz > tol:
            a_sz = an["vp"] if vp_ok else an["ratio"]
            h_sz = hn["vp"] if vp_ok else hn["ratio"]
            diffs.append({
                "category": "component", "severity": sev(dsz / tol, T),
                "is_migration_bug": True, "source": "metric_oracle",
                "description": f"「{name}」尺寸不一致({unit}): Android {a_sz['w']}x{a_sz['h']} "
                               f"vs HMOS {h_sz['w']}x{h_sz['h']}，Δ={round(dsz, 2)}（容差 {tol}）",
                "measured": {"size_delta": round(dsz, 3), "unit": unit, "pair_by": how},
            })
        # --- pixel 域（两端都有可靠像素测量才比） ---
        pa, ph = an.get("pixel"), hn.get("pixel")
        if pa and ph:
            if pa["unreliable"] or ph["unreliable"]:
                uncovered.append({"dim": "color", "node": name,
                                  "why": f"ink 不可靠(bgSpread A={pa['bgSpread']} H={ph['bgSpread']}，渐变/图片底)，色差与字号本节点未判"})
            else:
                de_fg = delta_e(pa["fg"], ph["fg"])
                if de_fg > T["color_fg_de"]:
                    diffs.append({
                        "category": "color", "severity": sev(de_fg / T["color_fg_de"], T),
                        "is_migration_bug": True, "source": "metric_oracle",
                        "description": f"「{name}」前景色不一致: Android {pa['fg']} vs HMOS {ph['fg']}，"
                                       f"ΔE={de_fg:.1f}（容差 {T['color_fg_de']}）",
                        "measured": {"de": round(de_fg, 1), "a": pa["fg"], "h": ph["fg"]},
                    })
                de_bg = delta_e(pa["bg"], ph["bg"])
                if de_bg > T["color_bg_de"]:
                    diffs.append({
                        "category": "color", "severity": sev(de_bg / T["color_bg_de"], T),
                        "is_migration_bug": True, "source": "metric_oracle",
                        "description": f"「{name}」底色不一致: Android {pa['bg']} vs HMOS {ph['bg']}，"
                                       f"ΔE={de_bg:.1f}（容差 {T['color_bg_de']}）",
                        "measured": {"de": round(de_bg, 1), "a": pa["bg"], "h": ph["bg"]},
                    })
                # --- font（text 节点 ink 高度当字号代理） ---
                if an["text"] and vp_ok and pa.get("ink") and ph.get("ink") \
                        and "h_vp" in (pa["ink"] or {}) and "h_vp" in (ph["ink"] or {}):
                    df = abs(pa["ink"]["h_vp"] - ph["ink"]["h_vp"])
                    if df > T["font_ink_vp"]:
                        diffs.append({
                            "category": "font", "severity": sev(df / T["font_ink_vp"], T),
                            "is_migration_bug": True, "source": "metric_oracle",
                            "description": f"「{name}」字号疑似不一致(ink 高度代理): Android {pa['ink']['h_vp']}vp "
                                           f"vs HMOS {ph['ink']['h_vp']}vp，Δ={df:.1f}（容差 {T['font_ink_vp']}）",
                            "root_cause_hint": "ink 高度含 emoji/图标混排干扰的可能，fixer 需以 fontSize 源码值核实",
                            "measured": {"font_delta_vp": round(df, 1)},
                        })
        elif pa or ph:
            uncovered.append({"dim": "pixel", "node": name, "why": "仅单端有像素域，颜色/字号本节点未判"})

    # --- struct 合并（missing/extra/order 由结构对比产出，直并去重） ---
    struct_n = 0
    if struct:
        S = struct
        seen = {(d["category"], d["description"]) for d in diffs}
        for d in S.get("differences", []):
            k = (d["category"], d["description"])
            if k not in seen:
                diffs.append(d)
                struct_n += 1
    else:
        uncovered.append({"dim": "structure", "why": "未传 --struct，missing/extra/order 三类未判（结构差异由结构 oracle 另行给出）"})

    # 固有不可判维度（每页固定记账，诚实边界）
    uncovered.append({"dim": "font_family", "why": "字体族/字重观感无度量代理，未判"})
    uncovered.append({"dim": "visual_gestalt", "why": "整体排版观感（不落到具体属性的'看着别扭'）未判"})

    order = {"high": 0, "medium": 1, "low": 2}
    diffs.sort(key=lambda d: (order.get(d.get("severity", "low"), 3), d.get("category", "")))
    out = {
        "schema": "metric_diff/1",
        "page_id": page_id,
        "tolerance_used": T,
        "stats": {"pairs": len(pairs), "android_nodes": A["node_count"],
                  "hmos_nodes": H["node_count"], "metric_diffs": len(diffs) - struct_n,
                  "struct_diffs_merged": struct_n, "uncovered": len(uncovered)},
        "differences": diffs,
        "uncovered": uncovered,
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--android", required=True)
    ap.add_argument("--hmos", required=True)
    ap.add_argument("--page-id", required=True)
    ap.add_argument("--struct")
    ap.add_argument("--tolerance", default=os.path.join(_HERE, "tolerance.json"))
    ap.add_argument("--out")
    args = ap.parse_args()
    A = json.load(open(args.android))
    H = json.load(open(args.hmos))
    T = {k: v for k, v in json.load(open(args.tolerance)).items() if not k.startswith("_")}
    S = json.load(open(args.struct)) if args.struct and os.path.exists(args.struct) else None
    out = compare(A, H, T, args.page_id, S)
    if args.out:
        json.dump(out, open(args.out, "w"), ensure_ascii=False, indent=1)
    else:
        json.dump(out, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
