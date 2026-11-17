# Execution policy

`execution-policy.json` is the local routing source for `scripts/execution_policy.py`.
Default: implementation → Sonnet/medium. Search and deterministic tasks use
Haiku/low; complex tasks use Opus/high; Fable/max requires explicit expert/model
selection. Model families map to their own full IDs; generic Agents fall back to
Sonnet. Parent model and effort are CLI arguments, never a global effort override.
Context uses the CLI's 100000 auto-compaction window and a separate 60000 soft
working target; neither is a hard total-context guarantee.

All limit overrides must be finite and positive. Reuse **both `--task-id` and
`run_dir`** on every retry/resume. The guardian stores an atomic, locked ledger at
`run_dir/execution-ledger/<task-id-hash>.json`, and later attempts cannot enlarge
the original cumulative limits, including at most three attempts per task. It preserves the full wrapped command, including
sandbox restrictions, passes stdout bytes through, and kills its process group on
timeout or interruption. It does not stop a remote service's already accepted
work or enforce the provider's bill.

USD values come from CLI estimates, not provider billing. Session/result UUIDs
and message IDs prevent duplicate snapshots and resumed `modelUsage` from being
added twice. Known input/cache usage survives errors; unknown output/cost stays
`null`. A missing terminal result or unpriced usage conservatively blocks another
attempt. Inspect/resolve that task's accounting before resuming; a fresh task ID
is a new task, not a retry mechanism.

Offline validation: `python3 -B migbot/scripts/test_execution_policy.py`.
