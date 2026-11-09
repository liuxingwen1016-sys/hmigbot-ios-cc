# i2h 阶段完成标记契约（schema-2）

`$i2h-run` 只把带内容哈希的 schema-2 marker 当作阶段完成证据。阶段
skill 可以继续使用 `.txt` 扩展名，但文件内容必须是由共享
`marker_contract.write_marker()` 写入的 JSON；不要手写旧的
`i2h-*-completed at ...` 文本。旧路径只用于读取历史工程，新运行必须写入
canonical 路径。

共享实现位于 `migbot/bin/scripts/pipeline/marker_contract.py`。安装后它会被
复制到 `<工程>/.migbot/bin/scripts/pipeline/`。下面的调用方式同时兼容源码
检出和已安装工程：

```python
import json
import sys
from pathlib import Path

root = Path.cwd().resolve()
for candidate in (
    root / ".migbot/bin/scripts/pipeline",
    root / "migbot/bin/scripts/pipeline",  # source checkout
):
    if candidate.is_dir():
        sys.path.insert(0, str(candidate))
        break
from marker_contract import write_marker

target_hash = None
for relative in ("spec/.i2h/target-input.json", "spec/.i2h/resources-inventory.json"):
    path = root / relative
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        target_hash = payload.get("target_input_sha256")
        if target_hash:
            break
if not target_hash:
    raise RuntimeError("missing target_input_sha256; do not create a completion marker")

artifact_candidates = ("spec/.i2h/resources-inventory.json",)
artifacts = [relative for relative in artifact_candidates if (root / relative).is_file()]
write_marker(
    root / "<canonical marker path>",
    "<stage id>",
    artifacts,
    target_hash,
    mode="static-only",       # use the actual mode when runtime checks ran
    root=root,
    producer="<stage id>",
)
```

Each stage must replace `artifact_candidates` with the artifacts it actually
produced. Include the report or receipt that gates the stage, and call
`write_marker` only after those files are final. Never include the marker file
itself as an artifact. The resulting object contains `schema_version: 2`,
`inputs_sha256`, an ordered `artifacts` list with per-file SHA-256 values, and
`content_sha256` over that list. A later edit to a recorded artifact therefore
causes `$i2h-run` to resume at that stage.

Canonical marker paths and useful artifact minimums are:

| stage | marker path | include at least |
|---|---|---|
| `i2h-spec` | `spec/baseline/spec-complete.txt` | `spec/.i2h/resources-inventory.json`, `spec/baseline/ui-manifest.md`, `spec/baseline/feature-index.md` |
| `i2h-plan` | `spec/baseline/plans/complete.txt` | approved schema-2 UI delivery JSON and the final plan |
| `i2h-execute` | `spec/execution/stage5-complete.txt` | `spec/migration-report.md`, `spec/execution/ui-state-ownership.json` |
| `i2h-retrospect` | `spec/retrospect-complete.txt` | the final `docs/retrospect-report*.md` |

`i2h-verify` has no separate JSON marker: `spec/verify-report.md` is the
canonical report and its `CHECK-1` plus status evidence are checked directly.

For an existing project, `pipeline_resume.py` can parse the explicit legacy
aliases and schema-1/text markers to explain why a stage is incomplete. A
legacy path containing a valid schema-2 marker is accepted in compatibility
mode with a warning; `--strict` requires rewriting it to the canonical path.
Unhashed text/schema-1 markers never advance the pipeline.
