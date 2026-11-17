"""Local timing for the stages dispatched by i2h-run."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import tempfile
import time
from uuid import UUID, uuid4


FULL_FLAGS = ("runtime_plan", "visual_and_ut", "behavior", "bound_visual")
TIMED_STAGES = ("i2h-spec", "i2h-plan", "i2h-execute", "i2h-verify")
CLOCK_TOLERANCE_SECONDS = 2


def runtime_sha256(plan_scripts: Path) -> str:
    """Fingerprint CC scripts and instructions under their real install layout."""
    skill_root = plan_scripts.resolve().parents[1]
    owner = skill_root.parent
    bin_root = owner.parent / ".migbot/bin" if owner.name == ".claude" else owner / "bin"
    runtime = sha256()
    for name, base in (("skill", skill_root), ("command", owner / "commands"),
                       ("agent", owner / "agents"), ("bin", bin_root)):
        pending = [base] if base.is_dir() else []
        while pending:
            path = pending.pop()
            if path != base and (path.name.startswith(".") or path.name in ("tests", "__pycache__")
                                 or path.name.endswith(".dist")):
                continue
            if path.is_dir() and not path.is_symlink():
                pending.extend(sorted(path.iterdir(), reverse=True))
                continue
            if not path.is_file():
                continue
            relative = path.relative_to(base)
            runtime.update(f"{name}/{relative.as_posix()}\n".encode("utf-8"))
            runtime.update(sha256(path.read_bytes()).digest())
    return runtime.hexdigest()


def _fingerprint(path: Path) -> str | None:
    return sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _progress(run: dict, preflight: dict, clock: float, action: str, stage: str) -> None:
    attempts = run["attempts"]
    if preflight["resume_stage"] == "i2h-verify":
        run.setdefault("first_verify_ready_seconds", round(clock - attempts[0]["start_monotonic"], 3))
    if action == "start" and stage == "i2h-verify":
        run.setdefault("first_verify_start_seconds", round(clock - attempts[0]["start_monotonic"], 3))
    plan = next((row for row in preflight["stages"] if row["stage"] == "i2h-plan" and row["complete"]), None)
    if not plan:
        return
    digest = plan.get("checks", {}).get("marker", {}).get("artifact_set_sha256")
    if action == "finish" and stage == "i2h-plan":
        run.setdefault("plan_artifact_set_sha256", digest)
    frozen = run.get("plan_artifact_set_sha256")
    if frozen and digest != frozen:
        run["plan_scope_changed"] = True


def _completion_gaps(run: dict, preflight: dict, flags: dict) -> list[str]:
    attempts = run["attempts"]
    required = {row["stage"] for row in preflight["stages"][:4]}
    observed = {row["stage"] for row in attempts if row["status"] == "complete"}
    gaps = []
    if attempts[0]["stage"] != "i2h-spec" or not required <= observed:
        gaps.append("stages_not_fully_timed")
    if not run.get("target_input_sha256") or not run.get("runtime_sha256"):
        gaps.append("missing_input_or_runtime_identity")
    if not all(flags.get(key) for key in FULL_FLAGS):
        gaps.append("strict_checks_missing")
    if not run.get("plan_artifact_set_sha256"):
        gaps.append("approved_plan_identity_missing")
    if run.get("plan_scope_changed"):
        gaps.append("approved_plan_changed")
    if run.get("clock_discontinuity"):
        gaps.append("clock_discontinuity")
    verification = preflight.get("verification", {})
    visual = verification.get("visual_evidence", {})
    behavior = verification.get("behavior_evidence", {})
    if not (verification.get("report_sha256") and behavior.get("report_sha256")
            and behavior.get("plan_sha256") and visual.get("report_sha256")):
        gaps.append("bound_verify_evidence_missing")
    else:
        run["verify_evidence"] = {"report_sha256": verification["report_sha256"],
                                  "visual": visual, "behavior": behavior}
        before = run.get("initial_verify_evidence", {})
        if any(before.get(name) == proof["report_sha256"]
               for name, proof in (("visual", visual), ("behavior", behavior))):
            gaps.append("preexisting_verify_evidence")
    return gaps

def _receipt_path(root: Path, run_id: str) -> Path:
    if UUID(run_id).hex != run_id:
        raise ValueError("expected timing run ID from the start command")
    path = root / "spec/.i2h/timing" / f"{run_id}.json"
    if path.resolve() != path:
        raise ValueError("timing receipt path must stay in the project")
    return path


def _seconds(value) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("invalid timing duration or monotonic sample")
    return value


def _utc_elapsed(started_at: str, ended_at: str) -> float:
    return (datetime.fromisoformat(ended_at) - datetime.fromisoformat(started_at)).total_seconds()


def report(root: Path, run_id: str) -> dict:
    """Read one recorded run, with its stage work and time between attempts."""
    path = _receipt_path(root, run_id)
    raw = path.read_bytes()
    run = json.loads(raw)
    if run["project_root"] != str(root) or run["run_id"] != run_id:
        raise ValueError("timing receipt does not belong to this project and run")
    attempts = run["attempts"]
    if not attempts:
        raise ValueError("timing receipt has no attempts")
    stage_totals = {stage: {"seconds": 0, "finished_attempts": 0, "incomplete_attempts": 0}
                    for stage in TIMED_STAGES}
    first_start = previous_end = None
    first_verify = None
    gap = work = after_verify_work = 0
    after_verify_ended = 0
    active = None
    legacy = False
    for index, attempt in enumerate(attempts):
        stage = attempt["stage"]
        counts = stage_totals[stage]
        start = _seconds(attempt["start_monotonic"])
        if first_start is None:
            first_start = start
        if previous_end is not None:
            if start < previous_end - 0.001:
                raise ValueError("timing attempts overlap or go backwards")
            if attempt["status"] != "running":
                gap += max(0, start - previous_end)
        if stage == "i2h-verify" and first_verify is None:
            first_verify = start
        if attempt["status"] == "running":
            if index != len(attempts)-1 or attempt.get("ended_at") is not None or attempt["wall_seconds"] is not None:
                raise ValueError("only the final attempt may be running with unknown duration")
            active = {"stage": stage, "started_at": attempt["started_at"], "seconds": None}
            continue
        if attempt["status"] not in ("complete", "incomplete"):
            raise ValueError("unknown timing attempt status")
        duration = _seconds(attempt["wall_seconds"])
        if "end_monotonic" in attempt:
            end = _seconds(attempt["end_monotonic"])
            if end < start or abs(end - start - duration) > 0.001:
                raise ValueError("attempt duration differs from monotonic clock")
            duration = end - start
        else:
            legacy = True
            end = start + duration
        previous_end = end
        counts["seconds"] += duration
        counts["finished_attempts"] += 1
        counts["incomplete_attempts"] += attempt["status"] == "incomplete"
        work += duration
        if first_verify is not None:
            after_verify_work += duration
            after_verify_ended += 1

    observed = previous_end - first_start if previous_end is not None else None
    for key in ("observed_wall_seconds", "wall_seconds"):
        stored = run.get(key)
        if stored is not None and (observed is None or abs(_seconds(stored) - observed) > 0.001):
            raise ValueError("recorded wall span differs from the attempt clock")
    for counts in stage_totals.values():
        counts["seconds"] = round(counts["seconds"], 3)

    after_verify = previous_end - first_verify if after_verify_ended else None
    ended_at = attempts[-2 if active else -1]["ended_at"] if previous_end is not None else None
    clock_validation = {}
    if "clock_discontinuity" in run:
        clock_validation = {
            "clock_validation": "discontinuous" if run["clock_discontinuity"] else "consistent",
            "utc_elapsed_seconds": round(_utc_elapsed(run["started_at"], ended_at), 3) if ended_at else None,
        }
    return {
        "run_id": run_id, "project_root": str(root), "receipt_sha256": sha256(raw).hexdigest(),
        "runtime_sha256": run.get("runtime_sha256"), "scope": run.get("scope"),
        "scope_gaps": run.get("scope_gaps"), "under_two_hours": run.get("under_two_hours"),
        "clock_basis": "monotonic_with_legacy_estimated_ends" if legacy else "monotonic",
        "finished_verify_wall_seconds": run.get("wall_seconds"),
        "first_verify_ready_seconds": run.get("first_verify_ready_seconds"),
        "first_verify_start_seconds": round(first_verify - first_start, 3) if first_verify is not None else None,
        "observed_until": ended_at,
        "observed_wall_seconds": round(observed, 3) if observed is not None else None,
        "finished_attempt_seconds": round(work, 3), "between_finished_attempts_seconds": round(gap, 3),
        "after_first_verify_start": {
            "finished_attempts": after_verify_ended, "attempt_seconds": round(after_verify_work, 3),
            "observed_seconds": round(after_verify, 3) if after_verify is not None else None,
        },
        "stages": stage_totals, "running_attempt": active, **clock_validation,
    }


def record(root: Path, preflight: dict, flags: dict, action: str, stage: str, run_id: str | None) -> dict:
    now = time.time()
    clock = time.monotonic()
    stamp = datetime.fromtimestamp(now, timezone.utc).isoformat()
    if action == "finish" and run_id is None:
        raise ValueError("finishing a stage requires its timing run ID")
    new_run = run_id is None
    run_id = run_id or uuid4().hex
    path = _receipt_path(root, run_id)
    target_input = preflight.get("target_input_sha256")
    tool_input = runtime_sha256(Path(__file__).parent)
    if path.exists():
        run = json.loads(path.read_bytes())
        recorded_flags = {"bound_visual": False, **run["flags"]}
        current_flags = {"bound_visual": False, **flags}
        if run["project_root"] != str(root) or recorded_flags != current_flags:
            raise ValueError("timing run project or gate scope changed")
        frozen_input = run.get("target_input_sha256")
        if frozen_input and frozen_input != target_input:
            raise ValueError("timing run target input changed")
        if run.get("runtime_sha256") not in (None, tool_input):
            raise ValueError("timing run CC runtime changed")
        if run["wall_seconds"] is not None:
            raise ValueError("timing run already ended at Verify")
    elif new_run:
        run = {"schema_version": 1, "run_id": run_id, "project_root": str(root), "flags": flags,
               "started_at": stamp, "ended_at": None, "wall_seconds": None, "attempts": [],
               "target_input_sha256": target_input, "runtime_sha256": tool_input, "clock_discontinuity": False}
        if all(flags.get(key) for key in FULL_FLAGS):
            from acceptance_plan import BEHAVIOR_REPORT

            run["initial_verify_evidence"] = {
                "behavior": _fingerprint(root / BEHAVIOR_REPORT),
                "visual": preflight.get("verification", {}).get("visual_evidence", {}).get("report_sha256"),
            }
    else:
        raise ValueError("timing run does not exist")

    attempts = run["attempts"]
    previous = attempts[-1] if attempts else None
    if previous and clock < previous.get("end_monotonic", previous["start_monotonic"]):
        raise ValueError("monotonic clock changed during timing")
    utc_span = None
    if previous and "clock_discontinuity" in run:
        utc_span = _utc_elapsed(run["started_at"], stamp)
        utc_step = _utc_elapsed(previous["ended_at"] or previous["started_at"], stamp)
        clock_span = clock - attempts[0]["start_monotonic"]
        clock_step = clock - previous.get("end_monotonic", previous["start_monotonic"])
        if max(abs(utc_span - clock_span), abs(utc_step - clock_step)) > CLOCK_TOLERANCE_SECONDS:
            run["clock_discontinuity"] = True
    if action == "start":
        if previous and previous["status"] == "running":
            raise ValueError("finish the active attempt before starting another")
        if preflight["resume_stage"] != stage:
            raise ValueError("timed stage must match the current preflight resume stage")
        attempts.append({"stage": stage, "started_at": stamp, "ended_at": None, "status": "running",
                         "start_monotonic": clock, "wall_seconds": None})
    else:
        if not previous or previous["stage"] != stage or previous["status"] != "running":
            raise ValueError("no matching timed stage is running")
        elapsed = clock - previous["start_monotonic"]
        if elapsed < 0:
            raise ValueError("monotonic clock changed during timing")
        stage_result = next(row for row in preflight["stages"] if row["stage"] == stage)
        stages = preflight["stages"][:4]
        verify_passed = stage == "i2h-verify" and all(row["complete"] for row in stages)
        span = clock - attempts[0]["start_monotonic"]
        previous.update(ended_at=stamp, end_monotonic=clock, wall_seconds=round(elapsed, 3),
                        status="complete" if stage_result["complete"] else "incomplete")
        run.update(observed_until=stamp, observed_wall_seconds=round(span, 3))
        first_verify = next((row for row in attempts if row["stage"] == "i2h-verify"), None)
        if first_verify is not None:
            run["observed_after_first_verify_seconds"] = round(clock - first_verify["start_monotonic"], 3)
        if stage == "i2h-spec" and stage_result["complete"] and not run.get("target_input_sha256"):
            run["target_input_sha256"] = target_input
    _progress(run, preflight, clock, action, stage)
    if action == "finish" and verify_passed:
        gaps = _completion_gaps(run, preflight, flags)
        deadline_span = span if utc_span is None else max(span, utc_span)
        run.update(ended_at=stamp, wall_seconds=round(span, 3), scope="partial" if gaps else "full",
                   scope_gaps=gaps, under_two_hours=None if gaps else deadline_span < 7200)

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write((json.dumps(run, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return {"run_id": run_id, "path": str(path), "attempt_status": attempts[-1]["status"],
            "wall_seconds": run["wall_seconds"], "scope": run.get("scope"),
            "observed_until": run.get("observed_until"), "observed_wall_seconds": run.get("observed_wall_seconds"),
            "first_verify_ready_seconds": run.get("first_verify_ready_seconds"),
            "first_verify_start_seconds": run.get("first_verify_start_seconds"),
            "observed_after_first_verify_seconds": run.get("observed_after_first_verify_seconds"),
            "scope_gaps": run.get("scope_gaps"), "under_two_hours": run.get("under_two_hours")}
