"""Run summary, review list and gallery."""
from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

LIST_WHOLE_MAX = 12  # sampled lists up to this size may get "tap every item" as the recommended review rule; longer
                     # ones (dates, cities, keywords: walker.PARAM_FAMILY_MIN = 13) select data and stay sampled
PAGE_KEY = re.compile(r"^P\d+$")

CAPTURE_PURPOSES = ("capture_first", "capture_scroll", "rewind")
ARTIFACT_STAT_KEYS = ("captures_attempted", "created", "reused", "revised", "retained", "ambiguous")


def _load(out: Path) -> tuple:
    aft = out / "_aft"
    state = json.loads((aft / "state.json").read_text(encoding="utf-8"))
    # The public index is the delivered artifact set, including later manual work.
    # A legacy/manual-only state need not contain automatic traversal counters.
    if (out / "index.json").exists():
        state["index"] = json.loads((out / "index.json").read_text(encoding="utf-8"))
    edges = []
    if (aft / "edges.jsonl").exists():
        edges = [json.loads(l) for l in (aft / "edges.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return state, edges


def device_seconds(dc: dict) -> dict:
    """Device-busy seconds split into navigation vs capture (focus polls live inside ready_wait)."""
    pt = dc.get("purpose_time", {})
    total = sum(v for k, v in pt.items() if not k.startswith("focus:"))
    capture = sum(v for k, v in pt.items() if not k.startswith("focus:") and k.partition(":")[2] in CAPTURE_PURPOSES)
    setup = sum(v for k, v in pt.items() if not k.startswith("focus:") and k.partition(":")[2] in ("setup", "launch"))
    return {"total": round(total, 2), "capture": round(capture, 2), "setup": round(setup, 2),
            "navigation": round(total - capture - setup, 2)}


def report(out: Path) -> dict:
    state, edges = _load(out)
    c = state.get("counters") or {}
    pages = state.get("pages", {})
    gap_records = state.get("gaps", [])
    skipped = state.get("skipped", [])
    gaps = Counter(g["code"] for g in gap_records)
    skipped_by_page = defaultdict(list)
    for s in skipped:
        skipped_by_page[s["page_id"]].append(f"{s['label'] or s['cand']['resource-id']} ({s['reason']})")
    unreachable = [g for g in gap_records if g["code"] == "unreachable"]
    allow_suggestions = [{"activity": pages[s["page_key"]]["activity"],
                          **({"rid": s["cand"]["resource-id"].rsplit("/", 1)[-1]} if s["cand"]["resource-id"] else {}),
                          **({"text": s["cand"]["label"]} if s["cand"]["label"] else {}),
                          "skipped_because": s["reason"], "page_id": s["page_id"]}
                         for s in skipped + state.get("sampled", []) if s.get("page_key") in pages]
    list_allow = sampled_lists(state)
    sampled_by_page = defaultdict(list)
    for s in state.get("sampled", []):
        sampled_by_page[s["page_id"]].append(f"{s['label'] or s['cand']['resource-id'].rsplit('/', 1)[-1]} ({s['reason']})")
    key_of = {p["page_id"]: k for k, p in pages.items()}
    review_template = {"allow": [], "deny": [], "retry": [pages[g["page"]]["page_id"] for g in unreachable
                                                          if g.get("page") in pages], "labels": {}}
    # Delivered counts come from index.json, so drive captures and instances are included.
    by_kind = Counter((r.get("aft") or {}).get("kind", "manual") for r in state.get("index", []))
    delivered = {"units": len(state.get("index", [])), "by_kind": dict(by_kind),
                 "frames": sum(len(r.get("screenshots") or ([r["screenshot"]] if r.get("screenshot") else []))
                               for r in state.get("index", []))}
    # Attempts are operations, not unique pages or delivered screenshots. A reused
    # capture still counts as an attempt; retained/archived evidence is not active.
    artifact_stats = state.get("artifact_stats")
    capture_stats = {"tracked": artifact_stats is not None,
                     **{key: (artifact_stats or {}).get(key, 0) if artifact_stats is not None else None
                        for key in ARTIFACT_STAT_KEYS}}
    suspected_duplicates = [
        {"page_id": rec["page_id"], "candidates": rec["aft"]["registry"]["suspected_duplicate"]}
        for rec in state.get("index", [])
        if (rec.get("aft") or {}).get("registry", {}).get("suspected_duplicate")]
    summary = {
        "status": state.get("status", "manual_only"), "halt_reason": state.get("halt_reason"), "delivered": delivered,
        "capture_stats": capture_stats, "suspected_duplicates": suspected_duplicates,
        "app": state.get("app"), "elapsed_s": state.get("elapsed_s"),
        "popup_stats": state.get("popup_stats"), "model_request": state.get("model_request"),
        "model_wait_s": (state.get("popup_stats") or {}).get("wait_s"),
        "model_inference_s": None,
        "manual_device_seconds": (device_seconds(state["manual_device_counters"])
                                  if state.get("manual_device_counters") is not None else None),
        "manual_elapsed_s": state.get("manual_elapsed_s"),
        "pages": c.get("pages", 0), "view_states": c.get("views", 0), "danger_dialogs": c.get("dialogs", 0),
        "frames": c.get("frames", 0), "explored_candidates": c.get("explored", 0),
        "edges": c.get("edges", {}), "restarts": c.get("restarts", 0),
        "replays": c.get("replays", 0), "transients": c.get("transients", 0), "skipped": c.get("skipped", {}),
        "gaps": dict(gaps), "drift_active": state.get("drift"),
        "drift_suspects": _ranked_suspects(state) if state.get("drift") else [],
        "readings_configured": _readings_configured(out),
        "stray_top_level": sorted(x.name for x in out.iterdir()
                                  if x.name not in ("index.json", "_aft") and not x.name.startswith(("page_", "manual_"))),
        "skipped_for_review": dict(skipped_by_page),
        "sampled_not_tapped": dict(sampled_by_page),
        "page_keys": key_of,
        "not_found": [g for g in gap_records if g["code"] == "not_found"],
        "path_denied": [g for g in gap_records if g["code"] == "path_denied"],
        "unreachable": unreachable,
        "review_template": review_template,
        "allow_suggestions": allow_suggestions,
        "list_allow": list_allow,
        "whole_column_denied": _whole_column_denied(state, out),
    }
    aft = out / "_aft"
    (aft / "report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (aft / "report.md").write_text(_markdown(summary, device_seconds(state.get("device_counters") or {})), encoding="utf-8")
    gallery(out, state)
    return summary


def _ranked_suspects(state: dict) -> list:
    """Same order as the halt reason (walker.ranked_suspects)."""
    sus = list(reversed(state.get("read_suspects") or []))
    return [s for s in sus if s.get("closed_own_page")] + [s for s in sus if not s.get("closed_own_page")]


def _whole_column_denied(state: dict, out: Path) -> list:
    """Lists denied as a whole column: a deny rule with only a resource-id that skipped three or more different items
    on one page. When the levels of a choice list share one id, the intermediate levels (a province, a city that
    opens its districts) are lost with the last one unless they are hand-driven, so the report names each such list
    where the model reads it."""
    try:
        rules = json.loads((out / "_aft" / "profile.json").read_text(encoding="utf-8")).get("deny") or []
    except (OSError, ValueError):
        return []
    pages = state.get("pages", {})
    found = []
    for rule in rules:
        if not rule.get("rid") or any(rule.get(k) for k in ("text", "text_contains", "desc")):
            continue
        by_page = defaultdict(list)
        for sk in state.get("skipped", []):
            page = pages.get(sk.get("page_key")) or {}
            rid = (sk["cand"].get("resource-id") or "").rsplit("/", 1)[-1]
            if (rid == rule["rid"] and sk["reason"] == "denied:" + (rule.get("reason") or "deny")
                    and (not rule.get("activity") or page.get("activity", "").endswith(rule["activity"]))
                    and sk["label"] and sk["label"] not in by_page[sk["page_id"]]):
                by_page[sk["page_id"]].append(sk["label"])
        found += [{"page_id": pid, "activity": rule.get("activity", ""), "rid": rule["rid"], "items": labels}
                  for pid, labels in by_page.items() if len(labels) >= 3]
    return found


def _readings_configured(out: Path) -> bool | None:
    try:
        profile = json.loads((out / "_aft" / "profile.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return bool(profile.get("business_readings"))


def _markdown(s: dict, secs: dict) -> str:
    e = {"device_seconds": secs}
    lines = [
        f"# 遍历报告",
        "",
        f"- 状态：**{s['status']}**" + (f"（{s['halt_reason']}）" if s.get("halt_reason") else ""),
        f"- 当前有效产物（index.json）：{s['delivered']['units']} 单元，{s['delivered']['frames']} 组截图/XML，按类型 {json.dumps(s['delivered']['by_kind'], ensure_ascii=False)}",
        (f"- 采集登记尝试 {s['capture_stats']['captures_attempted']} 次：新建 {s['capture_stats']['created']}，"
         f"复用 {s['capture_stats']['reused']}，修订 {s['capture_stats']['revised']}，保留原有效版本 {s['capture_stats']['retained']}，"
         f"身份歧义 {s['capture_stats']['ambiguous']} 次（不是新增页面数）"
         if s['capture_stats']['tracked'] else "- 采集登记尝试：旧账本未记录，不能由当前有效单元数反推"),
        f"- 自动遍历累计处理：页面 {s['pages']}，视图态 {s['view_states']}，危险弹窗 {s['danger_dialogs']}，截图/XML 组数 {s['frames']}（不等同当前有效交付量）",
        f"- 探索候选 {s['explored_candidates']}，冷启动 {s['restarts']}，路径重放 {s['replays']}，系统瞬态处理 {s['transients']}",
        f"- 自动遍历设备时间 {e['device_seconds']['total']} s（导航 {e['device_seconds']['navigation']} s，采集 {e['device_seconds']['capture']} s）；自动记录墙钟 {s['elapsed_s']} s",
        (f"- 模型等待 {s['model_wait_s']} s（包含在自动墙钟中，独立于设备时间）；模型推理时长未测量，不能视为 0"
         if s["model_wait_s"] is not None else "- 模型等待时间未记录；模型推理时长未测量，不能视为 0"),
        (f"- 手驱设备时间 {s['manual_device_seconds']['total']} s（采集 {s['manual_device_seconds']['capture']} s）；"
         f"手驱记录墙钟 {s['manual_elapsed_s']} s，不计入自动遍历墙钟"
         if s["manual_device_seconds"] is not None else "- 手驱设备时间：未单独记录，不从自动遍历计时推算"),
    ]
    if s["elapsed_s"]:
        dev_s = e["device_seconds"]["total"] or 0
        wait_s = s["model_wait_s"] or 0
        other = max(0.0, s["elapsed_s"] - dev_s - wait_s)
        pct = lambda v: f"{v / s['elapsed_s'] * 100:.0f}%"
        lines.append(f"- 时间分账（自动遍历墙钟 {s['elapsed_s']:.0f} s）：设备导航 {e['device_seconds']['navigation']:.0f} s"
                     f"（{pct(e['device_seconds']['navigation'])}），设备采集 {e['device_seconds']['capture']:.0f} s"
                     f"（{pct(e['device_seconds']['capture'])}），等模型处理弹窗 {wait_s:.0f} s（{pct(wait_s)}），"
                     f"执行器其他 {other:.0f} s（{pct(other)}）")
    if s.get("popup_stats") is not None:
        lines.append("- 弹窗运行统计：" + json.dumps(s["popup_stats"], ensure_ascii=False))
    request = s.get("model_request")
    if request:
        lines.append(f"- 最近模型请求：`{request.get('request_id', '')}`；请求状态 `{request.get('status', '')}`；"
                     f"证据与请求：`{request.get('request_path', '')}`")
    if s["status"] == "waiting_model":
        lines.append("- 当前进程正在等待调用本 skill 的模型提交 respond，遍历尚未完成；保持原进程存活。")
    elif s["status"] == "paused_model":
        lines.append("- 模型等待超时或弹窗决策未完成，断点已保留；这不是恢复熔断，也不表示必须交给用户。")
    elif s["status"] == "blocked_user":
        lines.append("- 模型已明确请求用户操作；按请求中的原因处理后，在原 OUT 续跑。")
    elif s["status"] == "halted_drift":
        lines.append("- 业务数据被改动且冷启动后没有恢复，执行器已停下，后面的页面没有在改过的数据上采集。"
                     "恢复数据（测试机上 `pm clear`，或用 `drive` 改回），把改数据的控件写进 deny，再对同一 OUT 续跑；"
                     "续跑时执行器先复核读数，没恢复会再次停下。不要删掉 business_readings 来绕过。")
    if s.get("stray_top_level"):
        lines.append("- 产物目录顶层只应有 index.json、page_*/、manual_*/ 和 _aft/；多出来的："
                     + "、".join(s["stray_top_level"]) + "（profile、review 请放 `_aft/input/`，其他请移走）")
    if s.get("readings_configured") is False:
        lines.append("- 未配置业务读数（business_readings）：本次没有核对数据是否被改动。")
    lines += [
        "",
        "## 待模型一次性审阅",
        "",
    ]
    if s["skipped_for_review"]:
        lines.append("未自动点击的控件（危险词 / deny / 确认类按钮；确认类按钮不放行，危险入口只在用户授权且只打开确认框时放行）：")
        for page, items in s["skipped_for_review"].items():
            lines.append(f"- {page}: " + "；".join(items))
    else:
        lines.append("- 无未自动点击的控件")
    if s["suspected_duplicates"]:
        lines.append(f"当前疑似重复单元 {len(s['suspected_duplicates'])} 个（身份不唯一，已分别保留；先核对画面与业务上下文，不能只按 Activity 合并）：")
        for item in s["suspected_duplicates"]:
            lines.append(f"- {item['page_id']}：候选 " + "、".join(item["candidates"]))
    if s.get("list_allow"):
        lines.append(f"被抽样的同构列表（“建议整列补点”只是机械初筛：{LIST_WHOLE_MAX} 项以内、每项点进去是一个页面、标签是文字。"
                     "由模型按含义决定：各项是不同的功能入口（指数、设置项、分类入口）才把规则放进 review 的 allow；"
                     "内容数据（关键词、商品、地名、日期、时间）保持抽样，确实需要某一项再写 rid 加 text）：")
        for la in s["list_allow"]:
            names = "、".join(la["not_tapped"][:8]) + (f" …共 {len(la['not_tapped'])} 项" if len(la["not_tapped"]) > 8 else "")
            advice = ("**建议整列补点**" if la["recommend"] == "whole_list" else
                      "点了不进新页面，建议保持抽样" if not la.get("opens_page") else "数据列表，建议保持抽样")
            lines.append(f"- {la['page_id']}（{la['activity']}）共 {la['size']} 项，未点：{names}。{advice}："
                         + "；".join(f"`{json.dumps(r, ensure_ascii=False)}`" for r in la["rules"][:6])
                         + (f" 等 {len(la['rules'])} 条" if len(la["rules"]) > 6 else ""))
    if s.get("whole_column_denied"):
        lines.append("整列拦截的列表（deny 只写了 rid，这一列每一项都没点）：列表里点了只进入下一级、不保存的项（例如省份、"
                     "带下级区县的城市），每个中间层手驱采一张，用一条 drive 串完，最末一级不点；拿不准哪一项只进入下一级时，"
                     "读这个列表点击处理的源码：")
        for w in s["whole_column_denied"]:
            names = "、".join(w["items"][:10]) + (f" …共 {len(w['items'])} 项" if len(w["items"]) > 10 else "")
            lines.append(f"- {w['page_id']}（{w['activity'] or '任意页面'}，rid={w['rid']}）：{names}。"
                         "写法：`drive \"tap <中间层的一项>; capture <名称>; back\"`")
    nav_back = {page: [i for i in items if i.endswith("(nav_back)")] for page, items in s.get("sampled_not_tapped", {}).items()}
    if any(nav_back.values()):
        lines.append("按返回箭头规则未点：")
        for page, items in nav_back.items():
            if items:
                lines.append(f"- {page}: " + "；".join(items[:12]) + (f" …共 {len(items)} 项" if len(items) > 12 else ""))
    for code in ("not_found", "unreachable"):
        if s[code]:
            lines.append(f"- {code}: " + "；".join(str(g.get("control") or g.get("page_id") or g.get("page")) for g in s[code]))
    if s.get("path_denied"):
        lines.append("- 因拦截规则到不了（所有已知路线都要经过现在被拦的控件，不要写进 retry）：" + "；".join(
            f"{g.get('page_id')}（{g.get('reason')}）" for g in s["path_denied"]))
    if s["gaps"]:
        lines.append(f"- 其他缺口计数：{json.dumps(s['gaps'], ensure_ascii=False)}")
    if s.get("drift_active"):
        lines.append(f"- 业务读数漂移未恢复：{json.dumps(s['drift_active'], ensure_ascii=False)}")
        if s.get("drift_suspects"):
            lines.append("- 漂移嫌疑点击（读数上次确认未变之后点过的控件；点完页面自己关闭的排最前，其余由近到远）：" + "；".join(
                f"{x['page_id']}「{x['label'] or x['resource-id']}」" + ("（点完页面自己关闭）" if x.get("closed_own_page") else "")
                for x in s["drift_suspects"]))
    lines += ["", "审阅后写 `_aft/input/review.json`（allow / deny / retry / labels；retry 写 page_id），执行 `run --review android_traverse_screenshots/_aft/input/review.json` 补跑（同一 OUT 自动续跑）。",
              "需要输入、登录或复杂手势的状态，用 `drive` 宏命令手驱补采。", ""]
    return "\n".join(lines)


def sampled_lists(state: dict) -> list[dict]:
    """One ready allow rule per sampled list, so the review re-queues the whole list, not just the item it names.

    A list whose items share a resource-id gets a single rid-only rule (every item matches it); a list of cells
    without ids gets one text rule per untapped item. "Tap every item" is recommended only for short lists whose
    items open a page and whose labels are words, not data (a menu of index cards, not hours, dates or prices);
    quick inputs that only change the screen in place stay sampled.
    """
    families = state.get("families", {})
    groups = defaultdict(list)
    for s in state.get("sampled", []):
        if s.get("reason") != "list_sample":
            continue
        cand = s["cand"]
        fam = s.get("family") or cand.get("family") or cand.get("group") or cand["key"]
        groups[(state["pages"][s["page_key"]]["activity"], fam)].append(s)
    out = []
    for (activity, fam), recs in groups.items():
        rids = {(r["cand"].get("resource-id") or "").rsplit("/", 1)[-1] for r in recs}
        rid = next(iter(rids)) if len(rids) == 1 else ""
        if rid:
            rules = [{"activity": activity, "rid": rid}]
        else:
            rules = [{"activity": activity, "text": r["cand"]["label"]} for r in recs if r["cand"].get("label")]
        size = max([r["cand"].get("family_size", 0) for r in recs] + [len(recs)])
        labels = [r["label"] or r["cand"]["key"] for r in recs]
        opens_page = bool(PAGE_KEY.match(str((families.get(fam) or {}).get("sig") or "")))
        data_like = sum(1 for t in labels if re.search(r"\d", t)) * 2 >= len(labels)
        whole = size <= LIST_WHOLE_MAX and opens_page and not data_like
        out.append({"page_id": recs[0]["page_id"], "activity": activity, "family": fam, "size": size,
                    "not_tapped": labels, "rules": rules, "opens_page": opens_page, "data_like": data_like,
                    "recommend": "whole_list" if whole else "keep_sampled"})
    return out


def gallery(out: Path, state: dict) -> Path:
    cards = []
    for rec in state.get("index", []):
        paths = rec.get("screenshots") or ([rec["screenshot"]] if rec.get("screenshot") else [])
        shots = "".join(f'<a href="../{html.escape(p)}"><img loading="lazy" src="../{html.escape(p)}"></a>'
                        for p in paths)
        aft = rec.get("aft", {})
        flags = []
        if aft.get("capture", {}).get("proof_degraded"):
            flags.append("proof_degraded")
        if aft.get("drift"):
            flags.append("drift")
        cards.append(f'<section><h3>{html.escape(rec["page_id"])} · {html.escape(rec.get("label") or "")}</h3>'
                     f'<p>{html.escape(aft.get("kind", ""))} · {html.escape(aft.get("activity", ""))} · '
                     f'{len(paths)} 帧 {" ".join(flags)}</p><div class="row">{shots}</div></section>')
    doc = ("<!doctype html><meta charset='utf-8'><title>Traversal gallery</title>"
           "<style>body{font-family:sans-serif;margin:16px;background:#fafafa;color:#222}"
           "section{margin:0 0 24px}h3{margin:4px 0;font-size:15px}p{margin:2px 0 6px;color:#666;font-size:13px}"
           ".row{display:flex;gap:8px;overflow-x:auto}.row img{height:360px;border:1px solid #ddd}</style>"
           f"<h1>遍历截图（{len(cards)} 个采集单元）</h1>" + "".join(cards))
    p = out / "_aft" / "gallery.html"
    p.write_text(doc, encoding="utf-8")
    return p
