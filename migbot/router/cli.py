"""CLI for the migration-strategy router. Invoked directly or via the installed
a2h-router.py launcher (which adds the package router dir to sys.path first)."""

import json
import os
import sys

sys.dont_write_bytecode = True

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profiles import apply_pending, cancel_request, recover_switch, request_switch, router_status  # noqa: E402


HELP = """用法：python3 .migbot/bin/a2h-router.py [--project <工程>] [--profile standard|1to1] [--dry-run] [--backup-modified]
不传 --profile：只查看当前策略。--profile X：提交切换（Claude Code 无会话空闲回调，默认排队）；加 --offline 立即应用。
--offline（不带 --profile）：应用已排队的请求。--cancel：取消待处理请求。--recover --offline：恢复中断事务。
首次安装默认 standard；/a2h-init 最后会提问选择迁移策略，并用 --profile … --offline 提交替换。"""


def main(args=None):
    if args is None:
        args = sys.argv[1:]
    try:
        options = {"project": os.getcwd()}
        seen = set()
        index = 0
        while index < len(args):
            key = args[index]
            if key in seen:
                raise RuntimeError(f"参数重复：{key}")
            seen.add(key)
            if key in ("--project", "--profile"):
                if index + 1 >= len(args) or args[index + 1].startswith("--"):
                    raise RuntimeError(f"参数无效：{key}")
                options[key[2:]] = args[index + 1]
                index += 2
            elif key in ("--dry-run", "--backup-modified", "--offline", "--cancel", "--recover", "--help"):
                options[key[2:]] = True
                index += 1
            else:
                raise RuntimeError(f"未知参数：{key}")

        if options.get("help"):
            print(HELP)
            return

        if (sum(bool(options.get(k)) for k in ("profile", "cancel", "recover")) > 1
                or (options.get("recover") and not options.get("offline"))
                or ((options.get("dry-run") or options.get("backup-modified")) and not options.get("profile"))):
            raise RuntimeError("参数组合无效；恢复需要 --recover --offline")

        if options.get("recover"):
            result = recover_switch(options["project"])
        elif options.get("cancel"):
            result = cancel_request(options["project"])
        elif options.get("profile"):
            result = request_switch(options["project"], options["profile"],
                                    dry_run=bool(options.get("dry-run")),
                                    backup_modified=bool(options.get("backup-modified")))
            if options.get("offline") and result.get("status") == "queued":
                result = apply_pending(options["project"])
        elif options.get("offline"):
            # Claude Code has no idle-session consumer; a bare --offline applies a queued request.
            result = apply_pending(options["project"]) or {"status": "unchanged", "note": "无待处理的切换请求"}
        else:
            result = router_status(options["project"])

        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("status") == "queued":
            print("切换已排队。请结束本回合，待全部会话空闲后应用；下一回合再查看状态，不要在本回合等待或启动迁移。")
        elif result.get("status") == "applied":
            print("磁盘资源已切换。agents/skills 会在当前会话内自动拾取（agent watcher 几秒内生效）；commands 两个策略相同、不随切换改变，无需 /reload-plugins。若宿主报新 skill/agent 不可见，用 /reload-skills 兜底；已有迁移产物不会被转换。")
        if result.get("status") == "failed":
            print(f"A2H_ROUTER=FAIL\n{result.get('error', '')}", file=sys.stderr)
            sys.exit(1)
    except Exception as exc:
        print(f"A2H_ROUTER=FAIL\n{exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
