#!/usr/bin/env python3
"""precision_ledger.py <mechanical_tree> <verified_tree> [--json out]

开发用精度账（不在运行链路里）：把机械候选（provenance.status=candidate，兼容旧式 candidate=true）的
trigger_label / trigger_view_id 与一棵**已被 LLM 核实或运行时回写**的同项目树逐条对照，得出"机械层答对/答错/
被证伪/无对照"的计数与错单。用途：改了 tree_generic 的解析规则后量精度有没有退化；不是完成判据，也不进
preflight。对照键：先按 (from_page, trigger_view_id) 精确对，再按 (from_page, evidence_line)，最后退到同 from_page
唯一条目；同起点多条且都对不上 → 记 ambiguous。
"""
import json, sys, collections

PL = {"", "unknown", "trigger_label_unknown", "none", "null", "?"}


def recs(t):
    return {r["id"]: r for k in ("pages", "fragments", "dialogs") for r in (t.get(k) or []) if isinstance(r, dict)}


def is_cand(e):
    return (e.get("provenance") or {}).get("status") == "candidate" or e.get("candidate") is True


def short(v):
    return (v or "").split(".")[-1]


def match(e, ver_entries):
    frm = e.get("from_page")
    same = [v for v in ver_entries if v.get("from_page") == frm]
    if not same:
        return None, "none"
    mv = short(e.get("trigger_view_id"))
    if mv:
        hit = [v for v in same if short(v.get("trigger_view_id")) == mv]
        if len(hit) == 1:
            return hit[0], "vid"
    ln = e.get("evidence_line")
    if ln is not None:
        hit = [v for v in same if v.get("evidence_line") == ln]
        if len(hit) == 1:
            return hit[0], "line"
    if len(same) == 1:
        return same[0], "from_page"
    return None, "ambiguous"


def main(argv):
    if len(argv) < 3:
        print(__doc__); return 2
    m, v = recs(json.load(open(argv[1]))), recs(json.load(open(argv[2])))
    out = argv[argv.index("--json") + 1] if "--json" in argv else None
    c = collections.Counter(); wrong = []
    for rid, rm in m.items():
        ver = [x for x in (v.get(rid) or {}).get("inbound_triggers") or [] if isinstance(x, dict)]
        for e in rm.get("inbound_triggers") or []:
            if not isinstance(e, dict) or not is_cand(e):
                continue
            c["candidates"] += 1
            ve, how = match(e, ver)
            if ve is None:
                c["no_counterpart_" + how] += 1; continue
            c["matched_by_" + how] += 1
            if ve.get("disproven"):
                c["disproven_by_llm"] += 1; continue
            ml, vl = (e.get("trigger_label") or "").strip(), (ve.get("trigger_label") or "").strip()
            mv, vv = short(e.get("trigger_view_id")), short(ve.get("trigger_view_id"))
            if ml and ml.lower() not in PL:
                c["mech_labeled"] += 1
                if vl and vl.lower() not in PL:
                    if ml == vl or ml in vl or vl in ml:
                        c["label_agree"] += 1
                    else:
                        c["label_wrong"] += 1; wrong.append((rid, e.get("from_page"), "label", ml, vl))
                else:
                    c["label_mech_only(llm_unknown)"] += 1; wrong.append((rid, e.get("from_page"), "label_llm_unknown", ml, vl))
            if mv:
                c["mech_vid"] += 1
                if vv:
                    if mv == vv:
                        c["vid_agree"] += 1
                    else:
                        c["vid_wrong"] += 1; wrong.append((rid, e.get("from_page"), "vid", mv, vv))
                else:
                    c["vid_mech_only"] += 1
            if (not ml or ml.lower() in PL) and vl and vl.lower() not in PL:
                c["llm_filled_missing_label"] += 1
    print(dict(c))
    for w in wrong:
        print("  ", w)
    if out:
        json.dump({"counts": dict(c), "wrong": wrong}, open(out, "w"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
