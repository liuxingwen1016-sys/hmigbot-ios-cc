"""Round report and round bookkeeping."""
from __future__ import annotations

import os
import re

from .android import Plan
from .fixplan import tickets_of
from .tickets import fix_root
from . import layout
from .store import Store, now_iso, read_json, write_json


def next_round(store: Store, cfg: dict, full: bool = False, log=print) -> int:
    r = store.rounds()
    cur = int(r.get("current", 0))
    scope = None
    if not full:
        ids = set()
        plan = Plan(cfg["android_out"])
        by_page = {layout.page_id(pid): pid for pid in plan.units}
        for t in tickets_of(cfg["hmos_project"], cur):
            for p in [t.get("page_id")] + list(t.get("blocks_subtree") or []):
                if p in by_page:
                    ids.add(by_page[p])
        st = store.state(cur) or {}
        for pid, u in (st.get("units") or {}).items():
            if u.get("status") in ("gap",) or (u.get("status") == "blocked"):
                ids.add(pid)
        changed, shared = changed_scope(store, cfg, cur)
        ids |= changed
        scope = None if shared else sorted(ids)
        if shared:
            log(f"[vvs] fixes changed shared files ({', '.join(shared[:4])}{' …' if len(shared) > 4 else ''}): "
                "the next round re-walks everything (unchanged evidence keeps its verdict)")
    nxt = cur + 1
    r["current"] = nxt
    r.setdefault("history", {})[str(nxt)] = {"created": now_iso(), "scope": scope, "from": cur}
    store.save_rounds(r)
    os.makedirs(store.round_dir(nxt), exist_ok=True)  # callers redirect logs into it right away
    layout.set_current_round(cfg["hmos_project"], nxt)
    log(f"[vvs] round-{nxt}: " + ("full walk" if scope is None else f"{len(scope)} units to re-walk"))
    return nxt


def changed_scope(store: Store, cfg: dict, rnd: int) -> tuple[set, list]:
    """Units whose own HarmonyOS page file the fixers changed, and the changed files no single page owns
    (components, resources, routes) — those can move any page, so they widen the next walk to all units."""
    from . import fixcheck
    from .fixfiles import _page_file
    hp = cfg["hmos_project"]
    fdir = os.path.join(store.round_dir(rnd), "fix")
    data = read_json(os.path.join(fdir, "fixcheck.json"))
    if data:
        ch = data.get("changed") or {}
    else:
        snap = read_json(os.path.join(fdir, "snapshot.json"))
        ch = fixcheck.changed(hp, snap) if snap else {}
    files = (ch.get("modified") or []) + (ch.get("added") or []) + (ch.get("deleted") or [])
    if not files:
        return set(), []
    pairs = read_json(os.path.join(store.round_dir(rnd), "pairs.json"), {}) or {}
    owners: dict = {}
    for it in pairs.get("items") or []:
        f = _page_file(hp, it.get("harmony_page"))
        if f:
            owners.setdefault(f, set()).add(it["android"])
    hosts = {f for f, pids in owners.items() if len(pids) > 1}  # one page file hosting many units is shared too
    units, shared = set(), []
    for f in files:
        if f in owners and f not in hosts:
            units |= owners[f]
        else:
            shared.append(f)
    # A file several units share (a Navigation host, a component) reaches the units whose captured screens show
    # its texts; a file without texts (styles, resources) or whose texts no capture shows stays shared.
    seen = {pid: set((m.get("sig") or {}).get("texts") or []) for pid, m in store.index_by_pair().items()}
    still = []
    for f in shared:
        texts = ui_texts(hp, f) if f.endswith(".ets") and os.path.exists(os.path.join(hp, f)) else set()
        hit = {pid for pid, t in seen.items() if texts & t}
        if hit:
            units |= hit
        else:
            still.append(f)
    return units, still


CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def ui_texts(hp: str, rel: str) -> set:
    """Texts a .ets file puts on screen (normalized like walk signatures): CJK / sentence string literals and the
    values of the string resources it uses."""
    from .fixfiles import _ets_texts
    from . import hui
    text = open(os.path.join(hp, rel), encoding="utf-8", errors="replace").read()
    text = re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)  # comments are not UI
    lits = [a or b for a, b in re.findall(r"'([^'\n]{1,60})'|\"([^\"\n]{1,60})\"", text)]
    out = [t for t in lits if CJK_RE.search(t) or re.fullmatch(r"[A-Za-z][A-Za-z,.!?']*( [A-Za-z,.!?']+)+", t)]
    strings = _ets_texts(hp)[1]
    out += [str(strings[n]) for n in re.findall(r"app\.string\.(\w+)", text) if strings.get(n)]
    return {hui.DIGITS.sub("#", hui.norm_label(t)) for t in out if hui.norm_label(t)}


def write(store: Store, plan: Plan, rnd: int, cfg: dict, log=print) -> str:
    st = store.state(rnd) or {}
    pairs = read_json(os.path.join(store.round_dir(rnd), "pairs.json")) or {}
    items = pairs.get("items") or []
    tickets = tickets_of(cfg["hmos_project"], rnd)
    fdir = os.path.join(fix_root(cfg["hmos_project"], rnd), "ui")
    blocked_n = sum(1 for n in (os.listdir(fdir) if os.path.isdir(fdir) else []) if n.startswith("BLOCKED_"))
    c = pairs.get("counts") or {}
    dc = st.get("device_counters") or {}
    t_by = {}
    for k, v in (dc.get("purpose_time") or {}).items():
        op = k.split(":", 1)[1] if ":" in k else k
        t_by[op] = round(t_by.get(op, 0) + v, 1)
    device_s = round(sum((dc.get("time") or {}).values()), 1)
    paired = sum(1 for it in items if it.get("status") == "paired")
    lines = [f"# visual-verify-speed round-{rnd} 报告", "",
             f"- 安卓基线: `{plan.out}`（{len(plan.units)} 个单元）",
             f"- 鸿蒙走查: 状态 **{st.get('status')}**{('（' + st.get('halt_reason', '') + '）') if st.get('halt_reason') else ''}，"
             f"自动走查墙钟 {round(st.get('elapsed_s', 0) / 60, 1)} 分（设备命令 {round(device_s / 60, 1)} 分）"
             + (f"，手驱补采 {round(st.get('manual_elapsed_s', 0) / 60, 1)} 分" if st.get("manual_elapsed_s") else ""),
             f"- 配对: {paired}/{len(plan.units)}；" + "，".join(f"{k} {v}" for k, v in sorted(c.items())),
             f"- 问题单: {len(tickets)} 条（`{fix_root(cfg['hmos_project'], rnd)}`，索引 `_index.md`、统计 `_summary.md`）"
             + (f"；另有本轮未采到的占位单 {blocked_n} 条" if blocked_n else ""), ""]
    cnt = st.get("counters") or {}
    if cnt:
        lines += ["## 走查计数", "", "| 点击 | 冷启动 | 重放 | 返回 | 找控件滚动 | 采集 | 帧 | 权限框 |", "|---|---|---|---|---|---|---|---|",
                  f"| {cnt.get('taps', 0)} | {cnt.get('restarts', 0)} | {cnt.get('replays', 0)} | {cnt.get('backs', 0)} | "
                  f"{cnt.get('searches', 0)} | {cnt.get('captures', 0)} | {cnt.get('frames', 0)} | {cnt.get('permissions', 0)} |", ""]
    if t_by:
        lines += ["## 设备时间（秒，按用途）", "", ", ".join(f"{k} {v}" for k, v in sorted(t_by.items(), key=lambda kv: -kv[1])[:14]), ""]
    ps = st.get("popup_stats")
    if ps:
        lines += ["## 弹窗请求", "", ", ".join(f"{k} {round(v, 1) if isinstance(v, float) else v}" for k, v in ps.items()), ""]
    gaps = [it for it in items if it.get("verdict") == "not_paired"]
    if gaps:
        lines += ["## 没有配上的单元", "", "| 安卓单元 | 名称 | 状态 | 原因 |", "|---|---|---|---|"]
        for it in gaps:
            g = it.get("gap") or {}
            why = g.get("code") or it.get("reason") or (f"上级 {it.get('blocked_by')}" if it.get("blocked_by") else "")
            lines.append(f"| {it['android']} | {it['label'][:24]} | {it.get('status')} | {why} |")
        lines.append("")
    drive = [it for it in gaps if it.get("status") == "needs_drive"]
    if drive:
        lines += ["## 需要手驱补采（vvs.py drive ... capture pair=<安卓单元>）", ""]
        for it in drive:
            u = plan.units[it["android"]]
            steps = " → ".join(f"{s.action} {s.label or s.direction or ('@%d,%d' % tuple(s.center) if s.center else '')}"
                               for s in u.path) or "(首次启动画面)"
            lines.append(f"- {it['android']}（{it['label']}，{it.get('reason')}）：安卓步骤 {steps}；安卓截图 `{(it.get('android_frames') or [''])[0]}`")
        lines.append("")
    weak = [it for it in items if it.get("status") == "paired" and it.get("confidence") in ("weak", "unconfirmed")]
    if weak:
        lines += ["## 配对把握低（判图时注意可能不是同一屏）", ""]
        lines += [f"- {it['android']} {it['label'][:24]}：{it.get('confidence')}（文字重合 {it.get('text_overlap')}，方式 {it.get('method')}）" for it in weak]
        lines.append("")
    marker = read_json(os.path.join(fix_root(cfg["hmos_project"], rnd), "_source.json"), {}) or {}
    wd = marker.get("withdrawn") or []
    if wd:
        lines += ["## 机械复核撤回/降级的判图结论", "",
                  "判图写的差异与 dump / 度量表对不上时撤回；位移只有几 dp 的降为低级（规则见 SKILL 质量底线）。", ""]
        lines += [f"- {w['android']} `{w.get('key')}`：{(w.get('description') or '')[:40]} → {w['why'][:90]}" for w in wd]
        lines.append("")
    dod = []
    for it in items:
        res = read_json(it.get("result") or "", {}) if it.get("result") else {}
        for d in (res or {}).get("data_only_differences") or []:
            dod.append(f"- {it['android']}：{d.get('what', '')[:60]}（安卓源码 {d.get('android_source_proof', '')[:50]}）")
    if dod:
        lines += ["## 只比了结构的差异（数据/随机内容，附安卓源码依据）", ""] + dod + [""]
    try:
        from . import coverage
        cov = coverage.build(store, plan, rnd, cfg, cfg.get("bundle", ""))
    except Exception as exc:  # the ledger must not stop the report
        cov = None
        lines += [f"（覆盖账生成失败：{exc}）", ""]
    if cov:
        src, aft, hm = cov["android_source"], cov["aft_uncaptured"], cov["android_missing_harmony_present"]
        lines += ["## 覆盖账", "",
                  f"1. **安卓源码清单**：Manifest 里本 App 的 Activity {len(src['activities'])} 个，aft 采到 "
                  f"{len(src['activities_captured_by_aft'])} 个；弹框类 {len(src['dialogs'])} 个"
                  + (f"；fact-tree 页面 {src['fact_tree_pages']} 个" if src.get("fact_tree_pages") else "") + "。",
                  f"   - aft 没采到的 Activity（两端都没验）：{'、'.join(src['activities_not_captured'][:30]) or '无'}",
                  f"2. **aft 没点到的控件**（这些状态两端都没验）：危险词/确认/拦截 "
                  f"{sum(len(v) for v in aft['not_tapped'].values())} 个，抽样跳过 {sum(len(v) for v in aft['sampled'].values())} 个，"
                  f"找不到 {len(aft['not_found'])} 个。"]
        for page, items in list(aft["not_tapped"].items())[:12]:
            lines.append(f"   - {page}：{'；'.join(items)[:160]}")
        lines.append(f"3. **鸿蒙配对**：{cov['harmony']['paired']}/{cov['harmony']['android_units']} 个安卓单元配上。")
        lines += ["4. **安卓缺、鸿蒙有**："]
        for fr in hm["frames"]:
            lines.append(f"   - {fr['android']}：鸿蒙多 {fr['extra']} 帧 → {fr['note']}")
        kinds = {"android_has": "安卓源码里有（安卓基线没采到或条件显示，先用 aft 补采安卓再比）",
                 "harmony_only": "安卓源码里没有（鸿蒙独有，请确认是否应删除或保留）"}
        for k, title in kinds.items():
            es = [e for e in hm["entries"] if e["kind"] == k]
            if es:
                lines.append(f"   - 鸿蒙多出的可点控件，{title}：")
                lines += [f"     - {e['android']}「{e['label']}」" + ("（无障碍描述，屏上不显示，读屏会念出来）" if e.get("a11y") else "")
                          + (f"（{e['source']}）" if e.get("source") else "") for e in es[:20]]
        other = sum(1 for e in hm["entries"] if e["kind"] in ("list_content", "data_judged"))
        if other:
            lines.append(f"   - 另有 {other} 个是列表内容或判图已用安卓源码证明的数据差异，不计")
        if hm["extra_captures"]:
            lines.append("   - 手驱额外截图（无安卓对应）：" + "、".join(f"{x['unit']}（{x['label']}）" for x in hm["extra_captures"]))
        if not (hm["frames"] or hm["entries"] or hm["extra_captures"]):
            lines.append("   - 无")
        lines.append("")
    if tickets:
        lines += ["## 问题单", ""]
        lines += [f"- [{t.get('severity')}] {t.get('id')} {t.get('title', '')}" for t in tickets]
        lines.append("")
    path = store.p("report.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log(f"[vvs] report -> {path}")
    return path
