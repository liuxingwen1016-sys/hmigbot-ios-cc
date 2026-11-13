"""Local timing for the stages dispatched by i2h-run."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import time
from uuid import UUID, uuid4


def record(root: Path, preflight: dict, flags: dict, action: str, stage: str, run_id: str | None) -> dict:
    now = time.time()
    clock = time.monotonic()
    stamp = datetime.fromtimestamp(now, timezone.utc).isoformat()
    if run_id is not None and UUID(run_id).hex != run_id:
        raise ValueError("expected timing run ID from the start command")
    if action == "finish" and run_id is None:
        raise ValueError("finishing a stage requires its timing run ID")
    new_run = run_id is None
    run_id = run_id or uuid4().hex
    path = root / "spec/.i2h/timing" / f"{run_id}.json"
    if path.resolve() != path:
        raise ValueError("timing receipt path must stay in the project")
    if path.exists():
        run = json.loads(path.read_bytes())
        if run["project_root"] != str(root) or run["flags"] != flags:
            raise ValueError("timing run project or gate scope changed")
        if run["wall_seconds"] is not None:
            raise ValueError("timing run already ended at Verify")
    elif new_run:
        run = {"schema_version": 1, "run_id": run_id, "project_root": str(root), "flags": flags,
               "started_at": stamp, "ended_at": None, "wall_seconds": None, "attempts": []}
    else:
        raise ValueError("timing run does not exist")

    attempts = run["attempts"]
    previous = attempts[-1] if attempts else None
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
        previous.update(ended_at=stamp, wall_seconds=round(elapsed, 3),
                        status="complete" if stage_result["complete"] else "incomplete")
        if verify_passed:
            span = clock - attempts[0]["start_monotonic"]
            required = {row["stage"] for row in stages}
            observed = {row["stage"] for row in attempts if row["status"] == "complete"}
            full = attempts[0]["stage"] == "i2h-spec" and required <= observed and all(flags.values())
            run.update(ended_at=stamp, wall_seconds=round(span, 3),
                       scope="full" if full else "partial",
                       under_two_hours=(span < 7200) if full else None)

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
            "under_two_hours": run.get("under_two_hours")}
