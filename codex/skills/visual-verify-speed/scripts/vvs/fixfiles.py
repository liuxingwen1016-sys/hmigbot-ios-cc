"""Fix files in the layout and schema the downstream fixer reads (spec/fix/round-N).

File name = id:
  ALIGN_P<page_id>_<diff_kind>_<context_slug>        visual difference (diff_kind from a fixed list)
  ALIGN_P<page_id>_page_missing_hmos                 Android reaches the page, HarmonyOS cannot
  ALIGN_P<page_id>_android_baseline_blocked_<slug>   a dialog / layer only the Android side shows
  CRASH_P<from>_nav_failed_<From>_to_<To>            an edge Android walked, HarmonyOS did not (v4_edge, blocks_subtree)
  CRASH_P<page_id>_app_crash_on_nav                  the app left the foreground after a tap
  BLOCKED_P<page_id>                                 placeholder: not captured this round (not a finding)
  SYSTEMIC_<slug>                                    the same problem on >= 3 pages (ui/_systemic/)
Front matter order, severity mapping, the five body sections (+ 1.5 references and 7 reach path), the round
files _index.md / _summary.md / _delta.md and spec/fix/_state.yaml follow the same schema.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter

from . import layout, source

DIFF_KIND = {"layout": "layout_drift", "layout_bug": "layout_bug", "color": "color_mismatch", "font": "font_mismatch",
             "spacing": "spacing_drift", "component": "component_mismatch", "icon": "icon_mismatch",
             "missing": "missing_element", "extra": "extra_element", "text": "text_mismatch",
             "scroll": "scroll_overflow", "image": "layout_bug", "state": "component_mismatch",
             "render": "missing_element", "other": "component_mismatch"}
KIND_ZH = {"layout_drift": "布局", "layout_bug": "布局", "color_mismatch": "颜色", "font_mismatch": "字体",
           "spacing_drift": "间距", "component_mismatch": "组件", "icon_mismatch": "图标", "missing_element": "缺失",
           "extra_element": "多余", "text_mismatch": "文案", "scroll_overflow": "滚动"}
VISUAL = set(KIND_ZH)
SEV_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,29}$")
ETS_LINE_RE = re.compile(r"([\w./-]*?(\w+\.ets)):(\d+(?:-\d+)?)")
HARD_GATE = ("> 🔴 **修复前必读 / FIXER MUST READ**：本 finding 含视觉差异，修复代码前 **必须** Read 以下 sbs 拼图验证差异"
             "描述、确认改动方向。**禁止**仅凭 §3 文字描述就改代码。")
SEC6 = ["## 6. 尝试过的修复方案（仅由修复方追加，禁删历史条目）",
        "<!-- 首次写 markdown 时本段为空。每轮修复后在此段末尾追加一条新记录，子段标题固定为",
        "     `### round-{N} attempt by visual-fixer`（下游按这一行计数），含 改动文件 / 改动摘要 / 假设根因 / 预期效果 / 未做的事；",
        "     carry-forward 会原样保留本段，所以下一轮能看到所有失败的历史尝试，必须改变思路。 -->"]


# ---------------------------------------------------------------- small helpers

def severity(mm: str, bug: bool = True) -> str:
    if mm == "high":
        return "P0" if bug else "P1"
    return "P1" if mm == "medium" else "P2"


def title(page: str, zh: str, text: str, limit: int = 38) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    if len(text) > limit:
        text = text[:limit - 1] + "…"
    s = f"[{page}] {zh}: {text}"
    return s if len(s) <= 60 else s[:59] + "…"


def ascii_slug(text: str) -> str:
    """Kebab-case slug from ASCII words, '' when the text has no usable ASCII (Chinese -> idx<NN> instead)."""
    if not text or re.search(r"[^\x00-\x7f]", text):
        return ""
    s = "-".join(re.findall(r"[a-z0-9]+", text.lower())[:3])[:30].strip("-")
    return s if SLUG_RE.match(s) else ""


def key_slug(key: str) -> str:
    k = (key or "").lower().replace("_", "-")
    return k if SLUG_RE.match(k) else ""


def yaml_scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("\n", " ")
    return s if re.fullmatch(r"[A-Za-z0-9_./@+-][A-Za-z0-9_./:@+ -]*", s) and not s.endswith(" ") else \
        json.dumps(s, ensure_ascii=False)


def yaml_lines(d: dict, indent: int = 0) -> list:
    out, pad = [], " " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            out.append(f"{pad}{k}:")
            out += yaml_lines(v, indent + 2)
        elif isinstance(v, list):
            out.append(f"{pad}{k}: []" if not v else f"{pad}{k}:")
            out += [f"{pad}  - {yaml_scalar(x)}" for x in v]
        else:
            out.append(f"{pad}{k}: {yaml_scalar(v)}")
    return out


def frontmatter(d: dict) -> str:
    return "\n".join(["---", *yaml_lines(d), "---"])


def gap_lines(files: list, said: str, what: str) -> list:
    """§4: one line per suggested file, with the line number when the judge's evidence names one."""
    lines_of = {}
    for m in ETS_LINE_RE.finditer(said or ""):
        lines_of.setdefault(m.group(2), m.group(3))
    out = []
    for f in files:
        if f == "unknown":
            continue
        out.append(f"- {f}:{lines_of.get(os.path.basename(f), 'unknown')} — {what[:70]}")
    return out or ["- unknown — 未定位到文件，由修复方按页面路径 grep 定位"]


class Ctx:
    """Everything one fix file needs from the round: paths, plan, Android source index."""

    def __init__(self, store, plan, cfg: dict, rnd: int, idx: dict):
        self.store, self.plan, self.cfg, self.rnd, self.idx = store, plan, cfg, rnd, idx
        self.hp = cfg["hmos_project"]
        self.android_project = cfg.get("android_project")

    def r(self, path):
        return layout.rel(self.hp, path)

    def evidence(self, it: dict, k: int = 0) -> list:
        """Canonical deliverables only (side-by-side, HarmonyOS, Android) — the paths the fixer is told to read."""
        canon = it.get("canonical") or {}
        out = []
        for side in ("sbs", "harmony", "android"):
            lst = [p for p in canon.get(side) or [] if p]
            if lst:
                p = lst[min(k, len(lst) - 1)]
                if p and os.path.exists(p):
                    out.append(self.r(p))
        if not out:  # carried without its canonical list: the canonical files of the round that judged it
            rnd, pid = it.get("carried_from", self.rnd), it["android"]
            for p in (layout.sbs(self.store, self.cfg, rnd, pid, k), layout.harmony_jpeg(self.store, self.cfg, rnd, pid, k),
                      layout.android_png(self.store, self.cfg, pid, k)):
                if os.path.exists(p):
                    out.append(self.r(p))
        return out

    def dumps(self, it: dict, k: int = 0) -> list:
        a = layout.android_xml(self.store, self.cfg, it["android"])
        rnd = it.get("carried_from", self.rnd) if it.get("verdict") == "carried" else self.rnd  # judged in that round
        h = layout.harmony_json(self.store, self.cfg, rnd, it["android"], k)
        got = [f"`{self.r(p)}`" for p in (a, h) if os.path.exists(p)]
        return ["、".join(got)] if got else []

    def android_ref(self, it: dict) -> str:
        p = layout.android_png(self.store, self.cfg, it["android"])
        if not os.path.exists(p) and it.get("android_frames"):
            layout._copy(it["android_frames"][0], p)
        return self.r(p) if os.path.exists(p) else (it.get("android_frames") or ["unknown"])[0]

    def source_block(self, refs: list) -> tuple[list, list]:
        """§1 '> 来源:' lines and the §1.5 list of Android files."""
        lines, files = [], []
        base = self.android_project or ""
        for r in refs or []:
            full = os.path.join(base, r["file"]) if base else r["file"]
            lines.append(f"> 来源: {full}:{r['line']}")
            if full not in files:
                files.append(full)
        if refs:
            r0 = refs[0]
            attrs = ", ".join(f"{k}={v}" for k, v in r0["attrs"].items() if k != "text")[:160]
            lines.append(f"> android_anchor: {r0['file']}:{r0['line']} {r0['tag']}({attrs})")
        return lines, files

    def reach(self, pid: str) -> list:
        steps = []
        for s in self.plan.click_steps(pid):
            if s.action == "tap":
                steps.append(f"tap '{s.label}'" if s.label else (f"tap rid={s.rid}" if s.rid else
                             f"tap @{s.center[0]},{s.center[1]}" if s.center else "tap (无文本标签)"))
            elif s.action == "swipe":
                steps.append(f"swipe {s.direction or 'up'}")
            elif s.action == "text":
                steps.append(f"input '{s.text or s.label}'")
            else:
                steps.append(s.action)
        return [f"{i}. {t}" for i, t in enumerate(steps, 1)] or ["1. 冷启动即到（根页面）"]

    def reach_section(self, pid: str) -> list:
        return ["## 7. 实际可达路径（reach_path，由安卓基线自动注入，禁手工编辑）",
                f"> 来源: {self.plan.out}/index.json [{pid}].click_path", "", *self.reach(pid), ""]

    def capture_mode(self, it: dict) -> str:
        xmls = it.get("android_xmls") or []
        try:
            if xmls and "android.webkit.WebView" in open(xmls[0], encoding="utf-8", errors="replace").read():
                return "web"
        except OSError:
            pass
        return "long" if len(it.get("android_frames") or []) > 1 else "single"


def similarity(res: dict | None, it: dict) -> float:
    """The judge's overall similarity; without one: structural match of the first frame (paired / (paired +
    missing + extra + invisible + font)) x (0.5 + 0.5 x share of paired elements within 4dp)."""
    v = (res or {}).get("similarity")
    if isinstance(v, (int, float)) and 0 <= v <= 1:
        return round(float(v), 2)
    fr = (it.get("frames") or [{}])[0].get("oracle") or {}
    try:
        with open(fr.get("file", ""), encoding="utf-8") as f:
            o = json.load(f)
        rows = [r for r in o.get("measure") or [] if not r.get("data")]
        paired = len(rows)
        diff = sum((o.get("summary") or {}).get(k, 0) for k in ("missing", "extra", "invisible", "font"))
        if not paired + diff:
            return 0.5
        ok = sum(1 for r in rows if max(abs(r["dx"]), abs(r.get("dy_residual") if r.get("dy_residual") is not None
                                                              else r["dy"])) <= 4
                 and (not r.get("size_comparable") or max(abs(r["dw"]), abs(r["dh"])) <= 4))
        return round(paired / (paired + diff) * (0.5 + 0.5 * (ok / paired if paired else 0)), 2)
    except (OSError, ValueError):
        return 0.5


def _ticket(tid: str, layer: str, front: dict, body: list, meta: dict) -> dict:
    return {"id": tid, "layer": layer, "front": front, "body": "\n".join(body), "meta": meta}


def _front(tid, ttl, kind, sev, files, cat_pattern, ev, pid_page, cap, sim, mm, bug, layer="ui", extra=None,
           before_evidence=None):
    f = {"id": tid, "title": ttl, "source": "visual-verify", "layer": layer, "kind": kind, "severity": sev}
    f.update(extra or {})
    f.update({"fixer_layer": layer, "category_pattern": cat_pattern, "suggested_files": files or ["unknown"],
              "related": [], "systemic_root": None, "affects": []})
    f.update(before_evidence or {})
    f.update({"evidence": ev or ["unknown"], "page_id": pid_page, "capture_mode": cap, "similarity": sim,
              "multimodal_severity": mm, "is_migration_bug": bug, "disposition": None, "disposition_reason": None,
              "disposition_set_at_round": None})
    return f


# ---------------------------------------------------------------- visual differences

def align(ctx: Ctx, it: dict, f: dict, res: dict | None, refs: list, slug: str, diff_kind: str | None = None,
          files_from_judge: bool = True, result_path: str = "") -> dict:
    """One judge finding (or a confirmed oracle item shaped like one)."""
    pid, page = it["android"], layout.page_id(it["android"])
    k = int(f.get("frame") or 0)
    pattern = f.get("category_pattern")
    dk = diff_kind or DIFF_KIND.get(f.get("category"), "component_mismatch")
    if pattern == "page_missing_hmos":
        tid, zh, sev = f"ALIGN_{page}_page_missing_hmos", "缺失", "P0"
    elif pattern == "dialog_extra_on_android":
        tid, zh, sev = f"ALIGN_{page}_android_baseline_blocked_{slug}", "缺失", "P1"
    else:
        tid, zh, sev = f"ALIGN_{page}_{dk}_{slug}", KIND_ZH.get(dk, "组件"), severity(f["severity"], f.get("is_migration_bug", True))
    text = f.get("title_text") or (f.get("element") if dk in ("missing_element", "extra_element") and f.get("element")
                                   else f["description"])
    ttl = title(page, zh, text)
    files = [p for p in f.get("suggested_files") or [] if p] or []
    if not files:
        host = _page_file(ctx.hp, it.get("harmony_page"))
        files, files_from_judge = ([host] if host else ["unknown"]), False
    ev = ctx.evidence(it, k)
    src_lines, src_files = ctx.source_block(refs)
    sbs_ev = [e for e in ev if "/sbs/" in e][:1]
    visual = (dk in VISUAL) and pattern not in ("page_missing_hmos",)
    body = [f"# {ttl}", ""]
    if visual and sbs_ev:
        body += [HARD_GATE, f"> - `{sbs_ev[0]}`", ""]
    body += ["## 1. Spec 引用", f"来源: {ctx.android_ref(it)}（Android 基线，单元 {pid}「{it.get('label', '')}」）",
             *src_lines, "",
             "## 1.5 必用参考（机械生成，禁编辑）", "",
             "**修复时必须用到下列参考**；用不上的要在 §6「未做的事」里写明为什么用不上。", "",
             *(f"- **Android 实现**：`{p}`" for p in src_files),
             *(f"- **双端对比图**：`{p}`（缺图即本页未做过视觉对比，按缺证处理）" for p in sbs_ev),
             *(f"- **双端 dump**：{d}（先看结构：真没渲染 / 被遮挡 / 滚出屏幕，再改源码）" for d in ctx.dumps(it, k)),
             "- **历史失败假设**：见 §6 —— 已被证伪的方向不得重复", "",
             "## 2. 期望", str(f.get("android", "")).strip(), "",
             "## 3. 实际", f"description: {str(f['description']).strip()}", f"harmony: {str(f.get('harmony', '')).strip()}"]
    if f.get("evidence"):
        body.append(f"证据: {str(f['evidence']).strip()}")
    if f.get("root_cause_hint"):
        body.append(f"root_cause_hint: {str(f['root_cause_hint']).strip()}")
    if f.get("element"):
        body.append(f"element: {f['element']}")
    if f.get("region"):
        body.append(f"region: 鸿蒙原图比例坐标 {f['region']}（第 {k} 帧）")
    if result_path:
        body.append(f"> source: {result_path}")
    said = " ".join(str(f.get(x, "")) for x in ("evidence", "root_cause_hint", "harmony"))
    body += ["", "## 4. 源码缺口", *gap_lines(files, said, str(f["description"]))]
    if refs:
        body.append(f"- 安卓对照：{refs[0]['file']}:{refs[0]['line']} — {source.format_ref(refs[0])[:120]}")
    body += ["", "## 5. 修复建议",
             "1. 以 §1 的安卓源码为准确认目标值（布局 XML / style / drawable / 代码里找，写清出处 file:line）",
             f"2. 按该取值修改鸿蒙实现，使其：{str(f.get('android', '')).strip()[:80]}",
             "3. 改完不编译、不截图复验，由下一轮复验确认", "", *SEC6, "", *ctx.reach_section(pid)]
    front = _front(tid, ttl, "ALIGNMENT_DIFF", sev, files, pattern or dk, ev, page, ctx.capture_mode(it),
                   similarity(res, it), f["severity"], bool(f.get("is_migration_bug", True)))
    meta = {"page": page, "pid": pid, "key": f.get("key"), "diff_kind": dk, "files": files if files_from_judge else [],
            "sev": sev, "mm": f["severity"], "visual": visual, "sbs": sbs_ev[0] if sbs_ev else None}
    return _ticket(tid, "ui", front, body, meta)


def check_ticket(ctx: Ctx, it: dict, c: dict, kind: str, res: dict | None, refs: list, slug: str) -> dict:
    """A failing icon_semantic / siblings_order check of the judge."""
    page = layout.page_id(it["android"])
    if kind == "icon":
        f = {"category": "icon", "severity": "medium", "is_migration_bug": True, "key": "" if slug.startswith("idx") else slug,
             "description": f"{c.get('context', '')} 形状/方向不符",
             "android": json.dumps(c.get("android"), ensure_ascii=False),
             "harmony": json.dumps(c.get("hmos"), ensure_ascii=False)}
        t = align(ctx, it, f, res, refs, slug, "icon_mismatch")
        t["front"]["title"] = title(page, "图标", f"{c.get('context', '')} 形状/方向不符")
    else:
        f = {"category": "layout", "severity": "medium", "is_migration_bug": True, "key": "" if slug.startswith("idx") else slug,
             "description": f"{c.get('container', '')} 与 Android 不一致",
             "android": " / ".join(map(str, c.get("android_order") or [])),
             "harmony": " / ".join(map(str, c.get("hmos_order") or []))}
        t = align(ctx, it, f, res, refs, slug, "layout_drift")
        t["front"]["title"] = title(page, "顺序", f"{c.get('container', '')} 与 Android 不一致")
    t["body"] = t["body"].replace(t["body"].split("\n", 1)[0], f"# {t['front']['title']}", 1)
    return t


# ---------------------------------------------------------------- walk gaps

NAV = {  # walk gap code -> (hmos_failed_reason, nav_mismatch_type, 中文)
    "control_not_found": ("trigger_not_found", "missing_handler", "鸿蒙找不到这一步的控件"),
    "no_response": ("click_failed", "missing_handler", "鸿蒙点了控件，页面没有变化"),
    "danger_refused": ("trigger_not_found", "semantic_diff", "鸿蒙同位置是删除/确认类控件，与安卓不一致，未点击"),
    "wrong_target": ("verify_timeout", "wrong_target", "鸿蒙点击后到达的不是安卓的那一页"),
    "control_covered": ("click_failed", "semantic_diff", "鸿蒙这一步的控件被上层（底栏、浮层）盖住，滚动后仍点不到"),
}


def _short(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "", text or "")[:40] or "Page"


def _page_file(hp: str, page_path: str | None) -> str | None:
    if not page_path:
        return None
    mods = ["entry"] + (sorted(os.listdir(hp)) if os.path.isdir(hp) else [])
    for mod in mods:
        p = os.path.join(mod, "src", "main", "ets", page_path + ".ets")
        if os.path.exists(os.path.join(hp, p)):
            return p
    return None


_ETS: dict = {}


def _ets_texts(hp: str) -> dict:
    """{rel path: text} of every .ets file and {string resource name: value} of every module (cached per project)."""
    if hp not in _ETS:
        files, strings = {}, {}
        for d, dirs, names in os.walk(hp, followlinks=True):
            dirs[:] = [x for x in dirs if x not in ("build", "oh_modules", "node_modules", "spec", "docs")
                       and not x.startswith(".")]
            for n in names:
                full = os.path.join(d, n)
                if n.endswith(".ets"):
                    files[os.path.relpath(full, hp)] = open(full, encoding="utf-8", errors="replace").read()
                elif n == "string.json" and os.sep + "element" in d:
                    try:
                        for x in json.load(open(full, encoding="utf-8")).get("string") or []:
                            strings.setdefault(x.get("name"), x.get("value"))
                    except (OSError, ValueError, AttributeError):
                        pass
        _ETS[hp] = (files, strings)
    return _ETS[hp]


def _shows(files: dict, strings: dict, label: str) -> set:
    want = re.sub(r"\s+", "", label or "")
    names = [k for k, v in strings.items() if k and re.sub(r"\s+", "", str(v or "")) == want]
    pats = [re.compile(r"['\"`]" + re.escape(label.strip()) + r"['\"`]")] + \
        [re.compile(r"app\.string\." + re.escape(n) + r"\b") for n in names]
    return {f for f, text in files.items() if any(p.search(text) for p in pats)}


def label_files(hp: str, label: str, peers=(), limit: int = 3) -> list:
    """HarmonyOS source files that show this label (literal, or through a string resource): where the entry
    control lives. Several -> the ones that also show most of the other texts of the Android screen (the entry
    list, not the target page's own title). More than `limit` files -> too generic to point at."""
    if len(re.sub(r"\s+", "", label or "")) < 2:
        return []
    files, strings = _ets_texts(hp)
    hits = _shows(files, strings, label)
    if len(hits) > 1 and peers:
        score = dict.fromkeys(hits, 0)
        for t in peers:
            if len(t) >= 2:
                for f in _shows({f: files[f] for f in hits}, strings, t):
                    score[f] += 1
        top = max(score.values())
        hits = {f for f in hits if score[f] == top}
    return sorted(hits) if 0 < len(hits) <= limit else []


def _gap_evidence(ctx: Ctx, it: dict) -> list:
    """Walk evidence of a failed step, copied into the canonical HarmonyOS _evidence/ folder."""
    out = []
    g = (it.get("gap") or {}).get("evidence") or {}
    base = os.path.join(layout.shots(ctx.store), "harmony", f"round-{ctx.rnd}", "_evidence")
    page = layout.page_id(it["android"])
    for key, name in (("png", f"{page}__failed.jpeg"), ("dump", f"{page}__failed.hmos.json")):
        src = g.get(key)
        if src:
            src = src if os.path.isabs(src) else ctx.store.p(src)
            dst = (layout._jpeg if key == "png" else layout._copy)(src, os.path.join(base, name))
            if dst:
                out.append(ctx.r(dst))
    return out


HIT_BLOCK_RE = re.compile(r"\?\s*HitTestMode\.Block\s*:\s*HitTestMode\.(?:None|Transparent|Default)")


def hit_block_scan(hp: str, files: list) -> list:
    """`visible ? HitTestMode.Block : None` in the entry page / its components: every child stops taking taps."""
    out = []
    for f in files:
        full = os.path.join(hp, f)
        try:
            for i, line in enumerate(open(full, encoding="utf-8", errors="replace"), 1):
                if HIT_BLOCK_RE.search(line):
                    out.append(f"{f}:{i}")
        except OSError:
            continue
    return out[:5]


def nav_failed(ctx: Ctx, it: dict, code: str, by_pid: dict, res: dict | None = None) -> dict:
    plan, pid = ctx.plan, it["android"]
    u = plan.units[pid]
    parent = u.parent or plan.root.page_id if plan.root else None
    from_page = layout.page_id(parent) if parent else layout.page_id(pid)
    pu = plan.units.get(parent) if parent else None
    reason, mtype, zh = NAV[code]
    tid = f"CRASH_{from_page}_nav_failed_{_short(pu.activity if pu else 'Root')}_to_{_short(u.activity)}_" \
          f"{layout.page_id(pid)}"
    step = u.step
    label = (step.label if step else "") or "(图标)"
    ttl = title(from_page, "导航", f"{(pu.label if pu else '首页')} → {u.label}（{zh}）", 44)
    # the files that show the entry label; the host page only when the label is nowhere (an icon, data)
    files = label_files(ctx.hp, step.label if step else "", step.peers if step else ())
    for page in ([] if files else (((by_pid or {}).get(parent) or {}).get("harmony_page"), it.get("harmony_page"))):
        f = _page_file(ctx.hp, page)
        if f and f not in files:
            files.append(f)
    blocks = [layout.page_id(d) for d in plan.descendants(pid)]
    ev = [ctx.android_ref(it)] + _gap_evidence(ctx, it) + (ctx.evidence(it, 0) if res is not None else [])
    ev = list(dict.fromkeys(e for e in ev if e))
    v4 = {"from_page": pu.label if pu else "Root", "to_page": u.label,
          "trigger": {"label": label, "resource_id": (step.rid if step and step.rid else None),
                      "type": "tap_text" if step and step.label else "tap_icon"},
          "android_verified": True, "hmos_failed_reason": reason, "nav_mismatch_type": mtype}
    front = _front(tid, ttl, "CRASH", "P0", files, "nav_failed", ev, from_page, None, None, "high", True,
                   before_evidence={"v4_edge": v4, "blocks_subtree": blocks, "reason_slug": "nav_failed"})
    gap = it.get("gap") or {}
    body = [f"# {ttl}", "", "## 1. Spec 引用",
            f"来源: {ctx.android_ref(it)}（Android 基线：从「{pu.label if pu else '首页'}」点「{label}」到达「{u.label}」）", "",
            "## 2. 期望", f"从「{pu.label if pu else '首页'}」点「{label}」后到达「{u.label}」，与安卓截图一致。", "",
            "## 3. 实际", f"{zh}。"]
    if gap.get("reason"):
        body.append(f"走查记录: {gap['reason']}")
    if gap.get("matched"):
        body.append(f"鸿蒙点到的控件: 「{gap['matched']}」（方式 {gap.get('method')}）")
    if res is not None and res.get("notes"):
        body.append("判图说明: " + str(res["notes"])[:300])
    for hit in hit_block_scan(ctx.hp, files):
        body.append(f"命中链预检：{hit} —— 显示时 HitTestMode.Block 会挡住整棵子树的点击，先查这里")
    if blocks:
        body.append(f"因此 {len(blocks)} 个下级页面本轮没有采到（见 blocks_subtree，修好后下一轮重采）。")
    body += ["", "## 4. 源码缺口", *(f"- {f}:unknown — 「{label}」的入口控件 / 点击事件 / 路由" for f in files),
             *([] if files else ["- unknown — 按鸿蒙对应页面查找入口控件、点击事件和路由注册"]), "",
             "## 5. 修复建议",
             f"1. 对照安卓源码找到「{label}」的点击处理和目标页面",
             {"missing_handler": "2. 在鸿蒙对应页面补上同样的入口和点击跳转",
              "wrong_target": "2. 改正鸿蒙点击后的路由目标（路由常量 / 跳转参数）",
              "semantic_diff": "2. 让鸿蒙该位置的控件与安卓一致（文案、类型、点击行为）"}[mtype],
             "3. 改完由下一轮复验确认，blocks_subtree 里的页面会一并重采", "", *SEC6, "", *ctx.reach_section(pid)]
    return _ticket(tid, "ui", front, body, {"page": from_page, "pid": pid, "sev": "P0", "kind": "CRASH",
                                             "blocks": blocks})


def app_crash(ctx: Ctx, it: dict) -> dict:
    """The app left the foreground on the step to this unit: a tap (on_nav), or the launch itself (on_launch)."""
    pid, page = it["android"], layout.page_id(it["android"])
    u = ctx.plan.units[pid]
    gap = it.get("gap") or {}
    launch = gap.get("phase") == "launch"
    slug = "app_crash_on_launch" if launch else "app_crash_on_nav"
    tid = f"CRASH_{page}_{slug}"
    ttl = title(page, "崩溃", "启动阶段（冷启动后立刻离开应用）" if launch else f"nav 阶段（进入「{u.label}」时离开应用）")
    ev = [ctx.android_ref(it)] + _gap_evidence(ctx, it)
    blocks = [layout.page_id(d) for d in ctx.plan.descendants(pid)]
    front = _front(tid, ttl, "CRASH", "P0", ["unknown"], "app_crash", ev, page, None, None, "high", True,
                   before_evidence={"blocks_subtree": blocks, "reason_slug": slug})
    logs = gap.get("crash_logs") or []
    body = [f"# {ttl}", "", "## 1. Spec 引用", f"来源: {ctx.android_ref(it)}（Android 基线：到达「{u.label}」）", "",
            "## 2. 期望", "冷启动后停在首页，与安卓根页一致。" if launch else f"点击后正常进入「{u.label}」。", "",
            "## 3. 实际",
            ("冷启动后应用立刻离开前台（疑似启动崩溃），本轮其余页面都没有走到。" if launch else
             "点击后应用离开前台（疑似崩溃或跳到了别的应用）。") + (f" 走查记录: {gap.get('reason')}" if gap.get("reason") else ""),
            *([f"设备故障日志: {', '.join(logs)}（`hdc file recv` 取回，看 Reason / Error message / Stacktrace）"] if logs else []),
            "", "## 4. 源码缺口", "- unknown — 先看设备故障日志 / hilog 里该时刻的异常栈定位", "",
            "## 5. 修复建议", "1. 按异常栈修复（启动期常见：依赖模块没打进包、入口页初始化抛错、资源缺失）",
            "2. 重新编译安装后再走查；改完由下一轮复验确认", "",
            *SEC6, "", *ctx.reach_section(pid)]
    return _ticket(tid, "ui", front, body, {"page": page, "pid": pid, "sev": "P0", "kind": "CRASH", "blocks": blocks})


def blocked(ctx: Ctx, it: dict, why: str, blocked_by: str | None, edge: str, disposition: str) -> dict:
    pid, page = it["android"], layout.page_id(it["android"])
    u = ctx.plan.units[pid]
    tid = f"BLOCKED_{page}"
    ttl = title(page, "未采集", f"{u.label}：{why}", 44)
    a = ctx.android_ref(it)
    front = {"id": tid, "title": ttl, "source": "visual-verify", "layer": "ui", "kind": "BLOCKED", "severity": "P3",
             "status": "blocked", "fixer_layer": "ui", "suggested_fix_owner": "noop", "suggested_files": ["unknown"],
             "related": [], "systemic_root": None, "affects": [], "blocked_by": blocked_by or a,
             "blocked_by_edge": edge, "evidence": [a], "page_id": page, "capture_mode": None, "similarity": None,
             "multimodal_severity": "low", "is_migration_bug": False, "disposition": disposition,
             "disposition_reason": why, "disposition_set_at_round": ctx.rnd}
    body = [f"# {ttl}", "", "## 1. Spec 引用", f"来源: {a}（Android 基线「{u.label}」）", "",
            "## 2. 期望", "本轮采到鸿蒙对应画面并完成对比。", "", "## 3. 实际", why, "",
            "## 4. 源码缺口", "- unknown — 占位单，不是缺陷，不派修复", "",
            "## 5. 修复建议", "1. 上游问题修好（或按报告手驱补采）后下一轮重采，到达后按证据出正式单并删除本占位", "",
            *ctx.reach_section(pid)]
    return _ticket(tid, "ui", front, body, {"page": page, "pid": pid, "sev": "P3", "kind": "BLOCKED"})


# ---------------------------------------------------------------- cross-page problems

def systemic(ctx: Ctx, tickets: list) -> list:
    """The same problem on >= 3 pages: same judge key, or same diff_kind in the same judge-named file(s)."""
    aligns = [t for t in tickets if t["front"]["kind"] == "ALIGNMENT_DIFF" and t["meta"].get("visual")]
    parent = list(range(len(aligns)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    first = {}
    for i, t in enumerate(aligns):
        m = t["meta"]
        keys = [("key", m.get("key"))] if m.get("key") and not str(m["key"]).startswith("idx") else []
        if m.get("files") and len(m["files"]) <= 2:
            keys.append(("files", m["diff_kind"], tuple(sorted(m["files"]))))
        for k in keys:
            if k in first:
                parent[find(i)] = find(first[k])
            else:
                first[k] = i
    groups = {}
    for i, t in enumerate(aligns):
        groups.setdefault(find(i), []).append(t)
    out = []
    for members in groups.values():
        pages = sorted({t["meta"]["page"] for t in members})
        if len(pages) < 3:
            continue
        keys = Counter(t["meta"].get("key") for t in members if t["meta"].get("key") and not str(t["meta"]["key"]).startswith("idx"))
        slug = key_slug(keys.most_common(1)[0][0]) if keys else ""
        slug = slug or f"{members[0]['meta']['diff_kind'].replace('_', '-')}-{len(out) + 1:02d}"
        tid = f"SYSTEMIC_{slug}"
        sev = min((t["front"]["severity"] for t in members), key=lambda s: SEV_ORDER[s])
        rels = [f"round-{ctx.rnd}/ui/{t['id']}.md" for t in members]
        files = list(dict.fromkeys(f for t in members for f in t["front"]["suggested_files"] if f != "unknown")) or ["unknown"]
        head = members[0]["front"]["title"].split("] ", 1)[-1]
        ttl = title(f"跨页·{len(pages)}页", head.split(": ", 1)[0] if ": " in head else "组件",
                    head.split(": ", 1)[-1])
        ev = list(dict.fromkeys(t["meta"]["sbs"] for t in members if t["meta"].get("sbs")))[:3] or ["unknown"]
        front = {"id": tid, "title": ttl, "source": "visual-verify", "layer": "ui", "kind": "SYSTEMIC", "severity": sev,
                 "fixer_layer": "ui", "category_pattern": members[0]["front"].get("category_pattern"),
                 "suggested_files": files, "related": rels, "systemic_root": None, "affects": rels, "evidence": ev,
                 "page_id": "_systemic", "capture_mode": "single",
                 "similarity": min(t["front"]["similarity"] or 1 for t in members),
                 "multimodal_severity": min((t["meta"]["mm"] for t in members), key=lambda s: {"high": 0, "medium": 1, "low": 2}[s]),
                 "is_migration_bug": True, "disposition": None, "disposition_reason": None, "disposition_set_at_round": None}
        body = [f"# {ttl}", "", "## 1. Spec 引用", f"来源: 跨页聚类（{len(pages)} 页同一问题：{', '.join(pages)}）",
                *(f"> 成员: {r}" for r in rels), "",
                "## 2. 期望", members[0]["body"].split("## 2. 期望", 1)[-1].split("## 3.", 1)[0].strip(), "",
                "## 3. 实际", *(f"- {t['front']['title']}" for t in members), "",
                "## 4. 源码缺口", *(f"- {f}:unknown — 共用实现，改一处覆盖 {len(pages)} 页" for f in files if f != "unknown"),
                *([] if files != ["unknown"] else ["- unknown — 由修复方按成员单定位"]), "",
                "## 5. 修复建议", "1. 在共用组件 / 样式里按安卓源码一次修好", "2. 逐个成员单核对是否都被覆盖", "", *SEC6, ""]
        out.append(_ticket(tid, "ui/_systemic", front, "\n".join(body).split("\n"), {"page": "_systemic",
                                                                                     "sev": sev, "kind": "SYSTEMIC",
                                                                                     "members": [t["id"] for t in members]}))
        for t in members:
            t["front"]["systemic_root"] = f"round-{ctx.rnd}/ui/_systemic/{tid}.md"
    return out


# ---------------------------------------------------------------- round files

def write_files(fix_dir: str, tickets: list) -> None:
    for t in tickets:
        d = os.path.join(fix_dir, t["layer"])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, t["id"] + ".md"), "w", encoding="utf-8") as fh:
            fh.write(frontmatter(t["front"]) + "\n\n" + t["body"].rstrip() + "\n")


def _link(t: dict) -> str:
    f = t["front"]
    extra = f" (affects {len(f.get('affects') or [])})" if f["kind"] == "SYSTEMIC" else ""
    return f"- [{f['title']}]({t['layer']}/{t['id']}.md) [{f['kind']}][{f['severity']}]{extra}"


def _sorted(tickets: list) -> list:
    return sorted(tickets, key=lambda t: (t["front"]["kind"] != "SYSTEMIC", SEV_ORDER.get(t["front"]["severity"], 9),
                                          t["front"]["kind"], t["id"]))


def write_index(fix_dir: str, rnd: int, tickets: list, when: str) -> None:
    lines = [f"# Round {rnd} 索引（visual-verify）", "", f"> 生成时间：{when}", ""]
    for layer, name in (("feat", "Feature 层"), ("ui", "UI 层")):
        ts = _sorted([t for t in tickets if t["layer"].split("/")[0] == layer])
        lines += [f"## {name}（{len(ts)} 条）", "", *(_link(t) for t in ts), ""]
    with open(os.path.join(fix_dir, "_index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_summary(fix_dir: str, rnd: int, tickets: list, pages: list, checks: list, when: str,
                  unchanged: int | None, stubborn: list | None = None) -> None:
    kinds = ("ALIGNMENT_DIFF", "CRASH", "IMPL_MISSING", "BLOCKED", "SYSTEMIC")
    lines = [f"# Round {rnd} 统计（visual-verify 部分）", "", f"> 跑测时间：{when}", "",
             "## 总计（按 kind，仅 visual-verify 产出的部分）", "",
             "| layer | " + " | ".join(kinds) + " | 合计 |", "|---|" + "---:|" * (len(kinds) + 1)]
    tot = Counter()
    for layer in ("ui", "feat"):
        c = Counter(t["front"]["kind"] for t in tickets if t["layer"].split("/")[0] == layer)
        tot.update(c)
        lines.append(f"| {layer} | " + " | ".join(str(c.get(k, 0)) for k in kinds) + f" | {sum(c.values())} |")
    lines.append("| **合计** | " + " | ".join(f"**{tot.get(k, 0)}**" for k in kinds) + f" | **{sum(tot.values())}** |")
    lines += ["", "## 页面维度（每页一行）", "",
              "| page_id | 页面名称 | capture_mode | similarity | high | medium | low | rounds | status |",
              "|---|---|---|---:|---:|---:|---:|---:|---|", *pages, "",
              "## Checks performed（证明 verifier 跑过）", "", "| check | 结果 |", "|---|---|", *checks, "",
              "## Top 10（按 severity + affects 排序，systemic 优先）", ""]
    top = [t for t in _sorted(tickets) if t["front"]["kind"] != "BLOCKED"][:10]
    lines += [f"{i}. `{t['id']}` [{t['front']['kind']}][{t['front']['severity']}] {t['front']['title']}"
              for i, t in enumerate(top, 1)] or ["（无）"]
    if stubborn:
        lines += ["", "## 顽固问题（≥3 轮或 ≥3 次修复仍未通过；≥5 次转人工）", ""]
        lines += [f"- `{tid}`：{r} 轮 / 修复 {n} 次 → {what}" for tid, r, n, what in stubborn]
    lines += ["", "## 未变化项", "", "round-0 无上一轮可比" if unchanged is None else
              f"无变化的开放问题：{unchanged}（详见 _delta.md）", ""]
    with open(os.path.join(fix_dir, "_summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def ids_of(fix_dir: str) -> set:
    out = set()
    for d, _, files in os.walk(fix_dir):
        for n in files:
            if n.endswith(".md") and not n.startswith("_"):
                out.add(n[:-3])
    return out


def write_delta(fix_dir: str, prev_dir: str, rnd: int, tickets: list) -> int:
    now = {t["id"] for t in tickets if t["front"]["kind"] != "BLOCKED"}
    before = {i for i in ids_of(prev_dir) if not i.startswith("BLOCKED_")}
    fixed, new, same = sorted(before - now), sorted(now - before), sorted(now & before)
    lines = [f"# Round {rnd} 与 Round {rnd - 1} 差异", "", f"## fixed（{len(fixed)}）", "",
             *(f"- `{i}`" for i in fixed), "", f"## new（{len(new)}）", "", *(f"- `{i}`" for i in new), "",
             "## regressed", "", "无机械可判的 GREEN→RED 回归项（new 中如有上一轮已修页面，人工复核）。", "",
             f"## unchanged（{len(same)}）", "", *(f"- `{i}`" for i in same), ""]
    with open(os.path.join(fix_dir, "_delta.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return len(same)


# ---------------------------------------------------------------- across rounds

def section6(text: str) -> str:
    """The attempt history of a fix file (everything in section 6 after its comment)."""
    if "## 6." not in text:
        return ""
    sec = text.split("## 6.", 1)[1].split("\n## 7.", 1)[0]
    sec = sec.split("\n", 1)[1] if "\n" in sec else ""
    if "-->" in sec:
        sec = sec.split("-->", 1)[1]
    keep = [ln for ln in sec.strip("\n").splitlines() if not ln.startswith("> 顽固问题") and not ln.startswith("> 上轮修复复核")]
    return "\n".join(keep).strip()


def with_history(body: str, notes: list, history: str) -> str:
    """Put carried notes and attempts into section 6 (right after its comment)."""
    if not notes and not history:
        return body
    anchor = SEC6[-1]
    extra = "\n".join([*(f"> {n}" for n in notes), *([history] if history else [])])
    return body.replace(anchor, anchor + "\n" + extra, 1) if anchor in body else body
