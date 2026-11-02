"""find_rollouts 只收主会话 rollout：子代理 rollout（session_id ≠ id）跳过，
派发与 list_agents 记录仍能从主会话取到（1016 客户 546 份子代理日志拖慢收口）。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import join_gate as j  # noqa: E402

ROOT_ID = "root-0001"


def _write(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for d in lines:
            fh.write(json.dumps(d) + "\n")


def _meta(own, sid, cwd):
    return {"type": "session_meta", "payload": {"id": own, "session_id": sid, "cwd": cwd}}


def _root_lines(cwd):
    return [
        _meta(ROOT_ID, ROOT_ID, cwd),
        {"payload": {"type": "function_call", "name": "spawn_agent", "call_id": "c1"}},
        {"payload": {"type": "function_call_output", "call_id": "c1",
                     "output": json.dumps({"task_name": "/root/page_0001"})}},
        {"payload": {"type": "function_call", "name": "list_agents", "call_id": "c2"}},
        {"payload": {"type": "function_call_output", "call_id": "c2",
                     "output": json.dumps({"agents": [{"agent_name": "/root/page_0001",
                                                       "agent_status": {"completed": "ok"}}]})}},
    ]


def test_subagent_rollouts_skipped(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    sess = tmp_path / "sessions"
    monkeypatch.setattr(j, "SESS_ROOT", str(sess))
    root_f = sess / "2026/10/16/rollout-root.jsonl"
    _write(str(root_f), _root_lines(str(proj)))
    for i in range(5):
        _write(str(sess / f"2026/10/16/rollout-sub{i}.jsonl"),
               [_meta(f"sub-{i}", ROOT_ID, str(proj))] + _root_lines(str(proj))[1:])
    files = j.find_rollouts(str(proj), 48)
    assert files == [str(root_f)]
    spawns, ever, _snap, _wc, _ts, _reopened, _killed = j.parse_rollouts(files)
    assert "/root/page_0001" in spawns and "/root/page_0001" in ever


def test_meta_without_session_id_kept(tmp_path, monkeypatch):
    """旧版 Codex 首行没有 session_id → 按主会话处理，保持原行为。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    sess = tmp_path / "sessions"
    monkeypatch.setattr(j, "SESS_ROOT", str(sess))
    f = sess / "2026/10/16/rollout-old.jsonl"
    _write(str(f), [{"type": "session_meta", "payload": {"id": "x", "cwd": str(proj)}}])
    os.utime(f, (time.time(), time.time()))
    assert j.find_rollouts(str(proj), 48) == [str(f)]
