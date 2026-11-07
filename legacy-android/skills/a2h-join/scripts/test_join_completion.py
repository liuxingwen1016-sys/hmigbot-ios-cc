"""新版多代理机制：完成的子代理很快从 list_agents 消失，完成只在 FINAL_ANSWER 消息里留痕；
followup_task 成功续作后须再次完成，续作调用失败（线程数超限）不算重新开工。
旧版（deepseek）：句柄是 agent_id，完成看 wait_agent / close_agent；close 时仍在跑 = 活没干完；
send_input 是续作；按任务名的契约与原子信封对旧版句柄不适用。"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import join_gate as j  # noqa: E402


def _spawn(name, call, agent_type="worker", ts="2026-10-20T10:00:00Z"):
    return [{"timestamp": ts,
             "payload": {"type": "function_call", "name": "spawn_agent", "call_id": call,
                         "arguments": json.dumps({"task_name": name, "agent_type": agent_type})}},
            {"payload": {"type": "function_call_output", "call_id": call,
                         "output": json.dumps({"task_name": "/root/" + name})}}]


def _message(name, kind, ts):
    text = f"Message Type: {kind}\nTask name: /root\nSender: /root/{name}\nPayload:\n"
    return {"timestamp": ts, "payload": {"type": "agent_message", "author": "/root/" + name,
                                         "recipient": "/root", "content": [{"type": "input_text", "text": text}]}}


def _followup(name, call, ts, output=""):
    return [{"timestamp": ts, "payload": {"type": "function_call", "name": "followup_task", "call_id": call,
                                          "arguments": json.dumps({"target": name, "message": "x"})}},
            {"timestamp": ts, "payload": {"type": "function_call_output", "call_id": call, "output": output}}]


def _gate(tmp_path, lines, *extra):
    roll = tmp_path / "rollout.jsonl"
    roll.write_text("".join(json.dumps(d) + "\n" for d in lines), encoding="utf-8")
    proc = subprocess.run([sys.executable, os.path.join(HERE, "join_gate.py"), "--project", str(tmp_path),
                           "--rollout", str(roll), "--no-ledger", *extra], capture_output=True, text=True)
    return proc.returncode, proc.stdout


def test_final_answer_counts_as_completed(tmp_path):
    rc, out = _gate(tmp_path, _spawn("conv_1", "s1") + [_message("conv_1", "FINAL_ANSWER", "2026-10-20T10:05:00Z")])
    assert rc == 0 and "joined            conv_1" in out


def test_spawned_without_completion_is_not_joined(tmp_path):
    rc, out = _gate(tmp_path, _spawn("conv_1", "s1") + _spawn("conv_2", "s2")
                    + [_message("conv_1", "FINAL_ANSWER", "2026-10-20T10:05:00Z")])
    assert rc == 1 and "UNOBSERVED         conv_2" in out


def test_progress_message_is_not_completion(tmp_path):
    rc, out = _gate(tmp_path, _spawn("conv_1", "s1") + [_message("conv_1", "MESSAGE", "2026-10-20T10:05:00Z")])
    assert rc == 3  # 没有任何完成观测，也没有 list_agents 出参：无法判定


def test_successful_followup_needs_another_final_answer(tmp_path):
    base = _spawn("conv_1", "s1") + [_message("conv_1", "FINAL_ANSWER", "2026-10-20T10:05:00Z")] \
        + _followup("conv_1", "f1", "2026-10-20T10:10:00Z")
    rc, out = _gate(tmp_path, base)
    assert rc == 1 and "OUTSTANDING       conv_1" in out
    rc, out = _gate(tmp_path, base + [_message("conv_1", "FINAL_ANSWER", "2026-10-20T10:20:00Z")])
    assert rc == 0 and "joined            conv_1" in out


def test_failed_followup_does_not_reopen(tmp_path):
    lines = _spawn("conv_1", "s1") + [_message("conv_1", "FINAL_ANSWER", "2026-10-20T10:05:00Z")] \
        + _followup("conv_1", "f1", "2026-10-20T10:10:00Z", "collab tool failed: agent thread limit reached")
    rc, out = _gate(tmp_path, lines)
    assert rc == 0 and "joined            conv_1" in out


# ── 旧版多代理机制（agent_id，无 task_name）─────────────────────────────────

def _call(name, call, args, output, ts="2026-10-20T10:00:00Z"):
    return [{"timestamp": ts, "payload": {"type": "function_call", "name": name, "call_id": call,
                                          "arguments": json.dumps(args)}},
            {"timestamp": ts, "payload": {"type": "function_call_output", "call_id": call, "output": output}}]


def _v1_spawn(aid, call):
    return _call("spawn_agent", call, {"agent_type": "worker", "message": "x"},
                 json.dumps({"agent_id": aid, "nickname": "Pauli"}))


def _v1_wait(aid, call, ts):
    return _call("wait_agent", call, {"targets": [aid]},
                 json.dumps({"status": {aid: {"completed": "OK"}}, "timed_out": False}), ts)


def _v1_close(aid, call, ts, prev):
    return _call("close_agent", call, {"target": aid}, json.dumps({"previous_status": prev}), ts)


def _contract(tmp_path, task_names, ok):
    work = tmp_path / "spec/a2h/_work"
    work.mkdir(parents=True, exist_ok=True)
    (work / "expected_s1.json").write_text(json.dumps({"join_point": "s1", "task_names": task_names,
        "artifacts": [{"path": "out/*.txt", "min_count": 1}]}), encoding="utf-8")
    if ok:
        (tmp_path / "out").mkdir(exist_ok=True)
        (tmp_path / "out/a.txt").write_text("done", encoding="utf-8")


def test_v1_wait_completion_counts(tmp_path):
    rc, out = _gate(tmp_path, _v1_spawn("a-1", "s1") + _v1_wait("a-1", "w1", "2026-10-20T10:05:00Z"))
    assert rc == 0 and "joined            Pauli（worker，a-1）" in out


def test_v1_closed_while_running_is_killed(tmp_path):
    rc, out = _gate(tmp_path, _v1_spawn("a-1", "s1") + _v1_close("a-1", "c1", "2026-10-20T10:05:00Z", "running"))
    assert rc == 1 and "KILLED-WHILE-RUNNING Pauli" in out


def test_v1_killed_but_wildcard_contract_satisfied_passes(tmp_path):
    _contract(tmp_path, ["*"], ok=True)
    rc, out = _gate(tmp_path, _v1_spawn("a-1", "s1") + _v1_close("a-1", "c1", "2026-10-20T10:05:00Z", "running"))
    assert rc == 0 and "产物已由契约背书" in out


def test_v1_send_input_reopens_until_next_completion(tmp_path):
    base = _v1_spawn("a-1", "s1") + _v1_wait("a-1", "w1", "2026-10-20T10:05:00Z") \
        + _call("send_input", "i1", {"target": "a-1", "message": "x"}, json.dumps({"submission_id": "x"}),
                "2026-10-20T10:10:00Z")
    rc, out = _gate(tmp_path, base)
    assert rc == 1 and "OUTSTANDING       Pauli" in out
    rc, out = _gate(tmp_path, base + _v1_close("a-1", "c1", "2026-10-20T10:20:00Z", {"completed": "OK2"}))
    assert rc == 0


def test_v1_named_contract_does_not_apply(tmp_path):
    _contract(tmp_path, ["conv_*"], ok=False)
    rc, out = _gate(tmp_path, _v1_spawn("a-1", "s1") + _v1_wait("a-1", "w1", "2026-10-20T10:05:00Z"))
    assert rc == 0 and "joined            Pauli" in out


def test_v1_completed_without_done_envelope_passes(tmp_path):
    (tmp_path / "spec/a2h/_work/done").mkdir(parents=True)
    rc, out = _gate(tmp_path, _v1_spawn("a-1", "s1") + _v1_wait("a-1", "w1", "2026-10-20T10:05:00Z"))
    assert rc == 0


def _audit(tmp_path, lines):
    roll = tmp_path / "rollout.jsonl"
    roll.write_text("".join(json.dumps(d) + "\n" for d in lines), encoding="utf-8")
    proc = subprocess.run([sys.executable, os.path.join(HERE, "audit_join_coverage.py"), str(roll)],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout


def test_audit_counts_final_answer_and_v1_wait(tmp_path):
    lines = _spawn("conv_1", "s1") + [_message("conv_1", "FINAL_ANSWER", "2026-10-20T10:05:00Z")] \
        + _v1_spawn("a-1", "s2") + _v1_wait("a-1", "w1", "2026-10-20T10:06:00Z")
    rc, out = _audit(tmp_path, lines)
    assert rc == 0 and "2/2 = 100.0%" in out


def test_audit_reports_killed(tmp_path):
    rc, out = _audit(tmp_path, _v1_spawn("a-1", "s1") + _v1_close("a-1", "c1", "2026-10-20T10:05:00Z", "running"))
    assert rc == 1 and "KILLED" in out


# ── 派发方声明：条款②死句柄重派 / 条款③跨 Gate 存活 ─────────────────────────

def _declare(tmp_path, *rows):
    work = tmp_path / "spec/a2h/_work"
    work.mkdir(parents=True, exist_ok=True)
    (work / "join-declarations.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _list(statuses, call="l1", ts="2026-10-20T10:30:00Z"):
    agents = [{"agent_name": "/root/" + n, "agent_status": st} for n, st in statuses.items()]
    return _call("list_agents", call, {}, json.dumps({"agents": agents}), ts)


def _done(name, ts):
    return [_message(name, "FINAL_ANSWER", ts)]


def test_redispatched_dead_handle_passes(tmp_path):
    lines = _spawn("conv_1", "s1") + _spawn("conv_1_redo1", "s2", ts="2026-10-20T10:20:00Z") \
        + _done("conv_1_redo1", "2026-10-20T10:25:00Z")
    assert _gate(tmp_path, lines)[0] == 1        # 原句柄未取回
    _declare(tmp_path, {"kind": "redispatch", "dead": "conv_1", "replacement": "conv_1_redo1"})
    rc, out = _gate(tmp_path, lines)
    assert rc == 0 and "dead-redispatched conv_1 → conv_1_redo1" in out


def test_redispatch_must_be_later_and_same_type(tmp_path):
    early = _spawn("conv_2", "s0", ts="2026-10-20T09:00:00Z") + _done("conv_2", "2026-10-20T09:05:00Z")
    other = _spawn("conv_3", "s3", agent_type="builder", ts="2026-10-20T10:20:00Z") + _done("conv_3", "2026-10-20T10:25:00Z")
    lines = _spawn("conv_1", "s1") + early + other
    _declare(tmp_path, {"kind": "redispatch", "dead": "conv_1", "replacement": "conv_2"},
             {"kind": "redispatch", "dead": "conv_1", "replacement": "conv_3"})
    rc, out = _gate(tmp_path, lines)
    assert rc == 1 and "派发不晚于原句柄" in out and "agent_type 不同" in out


def test_redispatch_limit_is_two(tmp_path):
    names = ["conv_1", "conv_1_r1", "conv_1_r2", "conv_1_r3"]
    lines = []
    for i, n in enumerate(names):
        lines += _spawn(n, f"s{i}", ts=f"2026-10-20T1{i}:00:00Z")
    lines += _done("conv_1_r3", "2026-10-20T14:30:00Z")
    _declare(tmp_path, *[{"kind": "redispatch", "dead": a, "replacement": b} for a, b in zip(names, names[1:])])
    rc, out = _gate(tmp_path, lines)
    assert rc == 1 and "已重派 2 次" in out and "UNOBSERVED         conv_1_r2" in out


def test_v1_killed_handle_redispatched_by_agent_id(tmp_path):
    lines = _v1_spawn("a-1", "s1") + _v1_close("a-1", "c1", "2026-10-20T10:05:00Z", "running") \
        + _call("spawn_agent", "s2", {"agent_type": "worker", "message": "x"},
                json.dumps({"agent_id": "a-2", "nickname": "Bohr"}), "2026-10-20T10:10:00Z") \
        + _v1_wait("a-2", "w2", "2026-10-20T10:20:00Z")
    _declare(tmp_path, {"kind": "redispatch", "dead": "a-1", "replacement": "a-2"})
    rc, out = _gate(tmp_path, lines)
    assert rc == 0 and "dead-redispatched Pauli" in out


def test_defer_only_releases_other_join_points(tmp_path):
    lines = _spawn("conv_1", "s1") + _list({"conv_1": "running"})
    _declare(tmp_path, {"kind": "defer", "handle": "conv_1", "join_point": "stage3_final"})
    rc, out = _gate(tmp_path, lines, "--join-point", "stage1_batch1")
    assert rc == 0 and "alive-across-gate conv_1" in out
    assert _gate(tmp_path, lines, "--join-point", "stage3_final")[0] == 1
    assert _gate(tmp_path, lines)[0] == 1           # 不带 --join-point 的最终收口


def test_defer_cannot_cover_dead_handle(tmp_path):
    lines = _v1_spawn("a-1", "s1") + _v1_close("a-1", "c1", "2026-10-20T10:05:00Z", "running")
    _declare(tmp_path, {"kind": "defer", "handle": "a-1", "join_point": "stage3_final"})
    rc, out = _gate(tmp_path, lines, "--join-point", "stage1_batch1")
    assert rc == 1 and "死句柄应按条款②重派" in out


def test_audit_honors_verified_redispatch(tmp_path):
    lines = _v1_spawn("a-1", "s1") + _v1_close("a-1", "c1", "2026-10-20T10:05:00Z", "running") \
        + _call("spawn_agent", "s2", {"agent_type": "worker", "message": "x"},
                json.dumps({"agent_id": "a-2", "nickname": "Bohr"}), "2026-10-20T10:10:00Z") \
        + _v1_wait("a-2", "w2", "2026-10-20T10:20:00Z")
    roll = tmp_path / "rollout.jsonl"
    roll.write_text("".join(json.dumps(d) + "\n" for d in lines), encoding="utf-8")
    cmd = [sys.executable, os.path.join(HERE, "audit_join_coverage.py"), str(roll)]
    assert subprocess.run(cmd, capture_output=True, text=True).returncode == 1
    _declare(tmp_path, {"kind": "redispatch", "dead": "a-1", "replacement": "a-2"})
    proc = subprocess.run(cmd + ["--project", str(tmp_path)], capture_output=True, text=True)
    assert proc.returncode == 0 and "redispatched" in proc.stdout
