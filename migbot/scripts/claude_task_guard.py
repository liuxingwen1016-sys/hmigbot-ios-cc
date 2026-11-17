#!/usr/bin/env python3
"""Watch a CLI process group and persist conservative, cumulative task accounting.

Costs are CLI estimates, never provider billing. Session cost/modelUsage snapshots
are high-water marks, not additive resume deltas. Unpriced/missing results block a
later attempt rather than pretending that unknown output or cost was zero.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import selectors
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from execution_policy import POLICY, add_execution_arguments, resolve_execution


TOKEN_FIELDS = {
    "input_tokens": "inputTokens", "output_tokens": "outputTokens",
    "cache_read_input_tokens": "cacheReadInputTokens",
    "cache_creation_input_tokens": "cacheCreationInputTokens",
}
EXIT_BUDGET = 78
EXIT_TIMEOUT = 124
EXIT_LOCKED = 75
EXIT_PROTOCOL = 65
MAX_FORWARD_BUFFER = 1024 * 1024


def notice(message):
    """Diagnostics must not stall termination when the stderr consumer is stuck."""
    fd = sys.stderr.fileno()
    blocking = os.get_blocking(fd)
    try:
        os.set_blocking(fd, False)
        os.write(fd, ("execution guard: " + message + "\n").encode("utf-8"))
    except (BlockingIOError, BrokenPipeError):
        pass
    finally:
        os.set_blocking(fd, blocking)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) and value >= 0 else None
    except OverflowError:
        return None


def merge_usage(target, source):
    for key, camel in TOKEN_FIELDS.items():
        value = number(source.get(key, source.get(camel)))
        if value is not None:
            target[key] = max(target.get(key, 0), value)


def atomic_json(path, data):
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def ledger_path(run_dir, task_id):
    digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:24]
    return Path(run_dir) / "execution-ledger" / f"{digest}.json"


class Accounting:
    def __init__(self, data, attempt):
        self.data = data
        self.attempt = attempt
        self.active_messages = {}

    def session(self, event):
        session_id = event.get("session_id") or self.attempt.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            session_id = "attempt:" + self.attempt["id"]
        else:
            self.attempt["session_id"] = session_id
        return self.data["sessions"].setdefault(session_id, {
            "messages": {}, "model_usage": {}, "result_ids": [],
            "priced_message_ids": [], "result_turns": {},
            "result_usage": {},
            "snapshot_message_ids": {},
            "estimated_cost_usd": None, "result_cost_complete": False,
        })

    def message(self, session, message):
        message_id = message.get("id")
        if not isinstance(message_id, str) or not message_id:
            return
        saved = session["messages"].setdefault(message_id, {
            "model": None, "usage": {}, "output_complete": False})
        if isinstance(message.get("model"), str):
            saved["model"] = message["model"]
        if isinstance(message.get("usage"), dict):
            # Assistant/message_start output is commonly a zero placeholder, not
            # final output accounting. Only input/cache is reliable here.
            merge_usage(saved["usage"], {key: value for key, value in message["usage"].items()
                                         if key not in ("output_tokens", "outputTokens")})
        self.active_messages[id(session)] = message_id

    def accept(self, event):
        if not isinstance(event, dict):
            return
        kind = event.get("type")
        if kind not in ("system", "assistant", "stream_event", "result"):
            return
        session = self.session(event)
        if kind == "assistant" and isinstance(event.get("message"), dict):
            self.message(session, event["message"])
        elif kind == "stream_event":
            item = event.get("event", {})
            if not isinstance(item, dict):
                return
            if item.get("type") == "message_start" and isinstance(item.get("message"), dict):
                self.message(session, item["message"])
            elif item.get("type") == "message_delta" and isinstance(item.get("usage"), dict):
                message_id = self.active_messages.get(id(session))
                if message_id:
                    merge_usage(session["messages"][message_id]["usage"], item["usage"])
            elif item.get("type") == "message_stop":
                message_id = self.active_messages.get(id(session))
                if message_id:
                    session["messages"][message_id]["output_complete"] = True
        elif kind == "result":
            self.attempt["terminal_result"] = True
            if event.get("is_error") or str(event.get("subtype", "")).startswith("error"):
                self.attempt["cli_error"] = True
            # UUID is authoritative. A repeated result must not consume budget twice.
            result_id = event.get("uuid")
            if not isinstance(result_id, str) or not result_id:
                result_id = hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()
            if result_id in session["result_ids"]:
                return
            session["result_ids"].append(result_id)
            if isinstance(event.get("usage"), dict):
                saved_result_usage = session["result_usage"].setdefault(result_id, {})
                merge_usage(saved_result_usage, event["usage"])
            turns = number(event.get("num_turns"))
            if turns is not None:
                session["result_turns"][result_id] = turns
            cli_cost = number(event.get("total_cost_usd"))
            models = event.get("modelUsage")
            all_model_costs = bool(models) and isinstance(models, dict)
            if isinstance(models, dict):
                for model, usage in models.items():
                    if not isinstance(usage, dict):
                        all_model_costs = False
                        continue
                    saved = session["model_usage"].setdefault(model, {"usage": {}, "cost_usd": None})
                    merge_usage(saved["usage"], usage)
                    cost = number(usage.get("costUSD"))
                    if cost is None:
                        all_model_costs = False
                    else:
                        saved["cost_usd"] = max(saved["cost_usd"] or 0, cost)
                for key, camel in TOKEN_FIELDS.items():
                    if models and all(isinstance(usage, dict) and
                                      number(usage.get(key, usage.get(camel))) is not None
                                      for usage in models.values()):
                        session["snapshot_message_ids"][key] = list(session["messages"])
            model_costs = [m["cost_usd"] for m in session["model_usage"].values()
                           if m["cost_usd"] is not None]
            known_costs = model_costs + ([] if cli_cost is None else [cli_cost])
            if known_costs:
                session["estimated_cost_usd"] = max(
                    session["estimated_cost_usd"] or 0, cli_cost or 0, sum(model_costs))
            session["result_cost_complete"] = cli_cost is not None or all_model_costs
            if session["result_cost_complete"]:
                session["priced_message_ids"] = list(session["messages"])

    def summarize(self):
        costs = []
        turns = 0
        totals = {key: [] for key in TOKEN_FIELDS}
        complete_fields = {key: True for key in TOKEN_FIELDS}
        complete_cost = True
        for session in self.data["sessions"].values():
            messages = list(session["messages"].values())
            snapshots = list(session["model_usage"].values())
            turns += max(len(messages), sum(session["result_turns"].values()))
            for key in TOKEN_FIELDS:
                message_values = [m["usage"][key] for m in messages if key in m["usage"]]
                snapshot_values = [m["usage"][key] for m in snapshots if key in m["usage"]]
                values = ([sum(message_values)] if message_values else [])
                values += ([sum(snapshot_values)] if snapshot_values else [])
                # result.usage is a per-invocation main-loop lower bound. It is
                # independent of cumulative session modelUsage and can omit subagents.
                result_values = [usage[key] for usage in session.get("result_usage", {}).values()
                                 if key in usage]
                if result_values:
                    values.append(sum(result_values))
                if values:
                    totals[key].append(max(values))
                messages_complete = bool(messages) and len(message_values) == len(messages)
                if key == "output_tokens":
                    messages_complete = False  # Observed output remains a lower bound.
                snapshot_complete = (bool(snapshots) and len(snapshot_values) == len(snapshots)
                    and set(session["messages"]).issubset(
                        session.get("snapshot_message_ids", {}).get(key, [])))
                complete_fields[key] &= messages_complete or snapshot_complete
            cost = session["estimated_cost_usd"]
            if cost is not None:
                costs.append(cost)
            pending = set(session["messages"]) - set(session["priced_message_ids"])
            if pending or not session["result_cost_complete"]:
                complete_cost = False
        # A process without a terminal result may have performed unobserved work.
        if any(a.get("status") != "running" and not a.get("terminal_result")
               for a in self.data["attempts"]):
            complete_cost = False
        self.data.update({
            "num_turns": turns,
            "usage": {key: sum(values) if values else None for key, values in totals.items()},
            "usage_complete": {key: bool(totals[key]) and complete_fields[key] for key in TOKEN_FIELDS},
            "known_estimated_cost_usd": sum(costs),
            "estimated_cost_usd": sum(costs) if costs else None,
            "cost_complete": complete_cost,
            "duration_seconds": sum(a.get("duration_seconds", 0) for a in self.data["attempts"]),
        })


def remaining_command(cmd, turns, budget):
    """Tighten existing CLI caps without changing wrappers or sandbox arguments."""
    result = list(cmd)
    limits = {"--max-turns": turns, "--max-budget-usd": budget}
    for index, item in enumerate(result):
        if item == "--":
            break
        option = item.split("=", 1)[0]
        if option not in limits:
            continue
        if "=" in item:
            try:
                result[index] = f"{option}={min(float(item.split('=', 1)[1]), limits[option]):g}"
            except ValueError:
                raise ValueError("invalid existing CLI execution limit") from None
        elif index + 1 < len(result):
            try:
                result[index + 1] = f"{min(float(result[index + 1]), limits[option]):g}"
            except ValueError:
                raise ValueError("invalid existing CLI execution limit") from None
    return result


def terminate_group(child, force=False):
    try:
        os.killpg(child.pid, signal.SIGKILL if force else signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError:
        # Some hosts report EPERM for a group whose leader has already exited.
        # Still terminate our direct child if it is alive and group signalling failed.
        if child.poll() is None:
            child.kill() if force else child.terminate()


def run_guard(args, route, cmd):
    path = ledger_path(args.run_dir, route.task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            notice("this task already has an active attempt")
            return EXIT_LOCKED
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
            "schema_version": 1, "task_id": route.task_id, "sessions": {}, "attempts": [],
            "max_attempts": POLICY["accounting"]["max_attempts"],
            "cost_source": "CLI estimates; not provider billing; session high-water snapshots",
            "limits": {"max_turns": route.max_turns, "max_budget_usd": route.max_budget_usd,
                       "timeout_seconds": route.timeout_seconds},
        }
        if data.get("task_id") != route.task_id or data.get("schema_version") != 1:
            raise ValueError("execution ledger identity/schema mismatch")
        limits = data["limits"]
        for key in limits:
            limits[key] = min(limits[key], getattr(route, key))
        data["max_attempts"] = min(data.get("max_attempts", POLICY["accounting"]["max_attempts"]),
                                   POLICY["accounting"]["max_attempts"])
        accounting = Accounting(data, {})
        accounting.summarize()
        reason = None
        if any(a.get("status") == "running" for a in data["attempts"]):
            reason = "an earlier attempt has an unknown outcome"
        elif len(data["attempts"]) >= data["max_attempts"]:
            reason = "cumulative attempt budget exhausted"
        elif data["num_turns"] >= limits["max_turns"]:
            reason = "cumulative turn budget exhausted"
        elif data["duration_seconds"] >= limits["timeout_seconds"]:
            reason = "cumulative wallclock budget exhausted"
        elif data["known_estimated_cost_usd"] >= limits["max_budget_usd"]:
            reason = "cumulative CLI estimated cost budget exhausted"
        elif data["attempts"] and not data["cost_complete"]:
            reason = "earlier CLI cost/outcome is unknown; another attempt would bypass accounting"
        if reason:
            data["last_denial"] = {"stage": args.stage, "reason": reason, "time": time.time()}
            atomic_json(path, data)
            notice(reason)
            return EXIT_BUDGET

        attempt = {"id": uuid.uuid4().hex, "stage": args.stage, "model": route.model,
                   "effort": route.effort, "started_at": time.time(), "duration_seconds": 0,
                   "status": "running", "terminal_result": False}
        data["attempts"].append(attempt)
        accounting = Accounting(data, attempt)
        atomic_json(path, data)
        remaining_time = limits["timeout_seconds"] - data["duration_seconds"]
        command = remaining_command(cmd, limits["max_turns"] - data["num_turns"],
                                    limits["max_budget_usd"] - data["known_estimated_cost_usd"])
        started = time.monotonic()
        child = None
        received = []
        old_handlers = {}
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            old_handlers[sig] = signal.signal(sig, lambda signum, frame: received.append(signum))
        status = "completed"
        returncode = EXIT_PROTOCOL
        destinations = {"stdout": sys.stdout.fileno(), "stderr": sys.stderr.fileno()}
        original_blocking = {name: os.get_blocking(fd) for name, fd in destinations.items()}
        try:
            for fd in destinations.values():
                os.set_blocking(fd, False)
            child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     start_new_session=True)
            selector = selectors.DefaultSelector()
            selector.register(child.stdout, selectors.EVENT_READ, "stdout")
            selector.register(child.stderr, selectors.EVENT_READ, "stderr")
            pending = b""
            forwarding = {"stdout": bytearray(), "stderr": bytearray()}
            discarding = False
            stopped_at = None
            while selector.get_map() or child.poll() is None or any(forwarding.values()):
                progressed = False
                for name, queued in forwarding.items():
                    if queued:
                        try:
                            written = os.write(destinations[name], queued)
                            del queued[:written]
                            progressed = True
                        except BlockingIOError:
                            pass
                elapsed = time.monotonic() - started
                if stopped_at is None:
                    if received:
                        status = "interrupted"
                    elif elapsed >= remaining_time:
                        status = "timeout"
                    elif data["num_turns"] > limits["max_turns"]:
                        status = "turn_budget"
                    elif data["known_estimated_cost_usd"] >= limits["max_budget_usd"] and not attempt["terminal_result"]:
                        status = "cost_budget"
                    if status != "completed":
                        terminate_group(child)
                        stopped_at = time.monotonic()
                elif time.monotonic() - stopped_at >= 0.2:
                    terminate_group(child, force=True)
                for key, _ in selector.select(0.05):
                    if len(forwarding[key.data]) >= MAX_FORWARD_BUFFER:
                        continue
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    progressed = True
                    forwarding[key.data].extend(chunk)
                    if key.data != "stdout":
                        continue
                    pending += chunk
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        if not discarding:
                            try:
                                accounting.accept(json.loads(line))
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                pass
                        discarding = False
                    # Never retain whole logs or arbitrarily large JSON lines in memory.
                    if len(pending) > 4 * 1024 * 1024:
                        pending = b""
                        discarding = True
                    accounting.summarize()
                    attempt["duration_seconds"] = time.monotonic() - started
                    atomic_json(path, data)
                if stopped_at is not None and time.monotonic() - stopped_at > 0.5:
                    # A descendant escaped the group but retained pipe FDs: do not hang forever.
                    for key in list(selector.get_map().values()):
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                    if any(forwarding.values()):
                        attempt["output_truncated"] = {name: len(queued)
                                                       for name, queued in forwarding.items()}
                        for queued in forwarding.values():
                            queued.clear()
                if not progressed:
                    time.sleep(0.01)
            selector.close()
            if pending and not discarding:
                try:
                    accounting.accept(json.loads(pending))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
            if stopped_at is not None:
                terminate_group(child, force=True)
            returncode = child.wait(timeout=2)
            if status == "timeout":
                returncode = EXIT_TIMEOUT
            elif status == "interrupted":
                returncode = 128 + received[0]
            elif status in ("turn_budget", "cost_budget"):
                returncode = EXIT_BUDGET
            elif not attempt["terminal_result"]:
                status = "missing_result"
                returncode = returncode or EXIT_PROTOCOL
            elif attempt.get("cli_error"):
                status = "cli_error"
                returncode = returncode or 1
            elif returncode:
                status = "failed"
        except (OSError, subprocess.TimeoutExpired, BrokenPipeError) as exc:
            status = "process_error"
            attempt["process_error_type"] = type(exc).__name__
            if isinstance(exc, OSError):
                attempt["process_error_errno"] = exc.errno
            if child is not None:
                terminate_group(child, force=True)
                child.wait(timeout=2)
            returncode = EXIT_PROTOCOL
        finally:
            for name, fd in destinations.items():
                os.set_blocking(fd, original_blocking[name])
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
            attempt.update(status=status, exit_code=returncode,
                           finished_at=time.time(), duration_seconds=time.monotonic() - started)
            accounting.summarize()
            atomic_json(path, data)
        if status != "completed":
            notice(f"{status}; accounting saved")
        return returncode if returncode >= 0 else 128 - returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--stage", required=True)
    add_execution_arguments(parser)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command after -- is required")
    try:
        return run_guard(args, resolve_execution(args), command)
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError):
        # Never echo command arguments, credentials, endpoint settings, or corrupt ledger data.
        notice("invalid policy or ledger; execution refused")
        return EXIT_PROTOCOL


if __name__ == "__main__":
    raise SystemExit(main())
