#!/usr/bin/env python3
"""Stable router entry installed to .migbot/bin/i2h-router.py.

Reads .migbot/plugin/install.json and delegates to the installed package's
cli.py, so /i2h-init's invocation path stays fixed across package upgrades.
"""

import importlib.util
import json
import os
import re
import sys

sys.dont_write_bytecode = True


def _load_cli():
    args = sys.argv[1:]
    try:
        index = args.index("--project")
    except ValueError:
        index = -1
    project = os.path.realpath(args[index + 1] if index >= 0 and index + 1 < len(args) else os.getcwd())
    with open(os.path.join(project, ".migbot", "plugin", "install.json"), encoding="utf-8") as handle:
        record = json.load(handle)
    digest = record.get("packageDigest", "")
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise RuntimeError("安装记录无效")
    router_dir = os.path.join(project, ".migbot", "plugin", "packages", digest, "router")
    sys.path.insert(0, router_dir)
    spec = importlib.util.spec_from_file_location("i2h_cli", os.path.join(router_dir, "cli.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    try:
        module = _load_cli()
        module.main(sys.argv[1:])
    except Exception as exc:
        print(f"I2H_ROUTER=FAIL\n请先通过插件安装器安装到当前工程。{exc}", file=sys.stderr)
        sys.exit(1)
