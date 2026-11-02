"""Router engine for runtime migration-strategy switching (standard <-> parity-1to-1).

Pure-stdlib port of the router engine. Logical entries are
`skills/<name>` (directory) or `agents/<name>.md` / `commands/<name>.md` (single
file); the repo keeps them under `skills/`, `agents/`, `commands/` and the install
targets keep them under `.claude/{skills,agents,commands}/`. Ownership digests are
tree-level sha256 so the installer and the router share one authoritative
definition.

Resource location is layout-aware: a flat-v1 delivery package (package.json with
`hmigbot.layout: "flat-v1"`) keeps `skills/` etc. at the package root, while the
repo checkout and nested packages keep them under `migbot/`.
"""

import hashlib
import json
import os
import re
import shutil
import stat as _stat
import uuid

from fs_support import fs_path, walk_files, copy_file, copy_tree, Progress, count_files, hashing, hashed_file

PROFILES = ["standard", "parity-1to-1"]

# Collection -> repo directory (inside a package tree) and install target root.
COLLECTIONS = [
    {"logical": "skills", "repo": "skills", "target": ".claude", "sub": "skills"},
    {"logical": "agents", "repo": "agents", "target": ".claude", "sub": "agents"},
    {"logical": "commands", "repo": "commands", "target": ".claude", "sub": "commands"},
]
HOSTS = ["claude"]

_ENTRY_RE = re.compile(r"^(skills|agents|commands)/[A-Za-z0-9][A-Za-z0-9._-]*$")
_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")
_UUID_RE = re.compile(r"^[\da-f-]{36}$")


def _repo_dir(logical):
    for item in COLLECTIONS:
        if item["logical"] == logical:
            return item["repo"]
    return None


def _target_dir(logical):
    for item in COLLECTIONS:
        if item["logical"] == logical:
            return item["target"]
    return None


def _sub_dir(logical):
    for item in COLLECTIONS:
        if item["logical"] == logical:
            return item["sub"]
    return None


def read_json(filename):
    if not os.path.exists(fs_path(filename)):
        return None
    with open(fs_path(filename), encoding="utf-8") as handle:
        return json.load(handle)


def resource_root(package_root):
    """Flat-v1 交付包资源在根；旧嵌套包/repo 在 migbot/ 下。"""
    pkg = read_json(os.path.join(package_root, "package.json"))
    layout = (pkg or {}).get("hmigbot", {}).get("layout") if isinstance(pkg, dict) else None
    if layout == "flat-v1":
        return package_root
    if layout is not None:
        raise RuntimeError(f"不支持的资源布局：{layout}")
    return os.path.join(package_root, "migbot")


def profile_name(value):
    profile = "parity-1to-1" if value == "1to1" else value
    if profile not in PROFILES:
        raise RuntimeError(f"未知策略：{value}")
    return profile


def write_json(filename, value):
    temporary = f"{filename}.{uuid.uuid4().hex}.tmp"
    try:
        fd = os.open(fs_path(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(fs_path(temporary), fs_path(filename))
    finally:
        if os.path.exists(fs_path(temporary)):
            os.unlink(fs_path(temporary))


def _safe_path(relative):
    if (not relative or os.path.isabs(relative) or "\\" in relative
            or any(part in ("", ".", "..") for part in relative.split("/"))):
        raise RuntimeError(f"不安全的资源路径：{relative}")
    return relative


def no_links(filename):
    current = os.path.abspath(filename)
    while True:
        if os.path.islink(fs_path(current)):
            raise RuntimeError(f"不支持符号链接：{current}")
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent


def tree_digest(filename, excludes=()):
    """Matches the installer's ownership digest; excludes are relative to this entry."""
    digest = hashlib.sha256()
    st = os.lstat(fs_path(filename))
    if _stat.S_ISLNK(st.st_mode):
        raise RuntimeError(f"不支持符号链接：{filename}")
    if _stat.S_ISDIR(st.st_mode):
        for name in sorted(os.listdir(fs_path(filename))):
            if name in excludes:
                continue
            children = tuple(e[len(name) + 1:] for e in excludes if e.startswith(name + "/"))
            digest.update(f"{name}\0".encode())
            digest.update(tree_digest(os.path.join(filename, name), children).encode("ascii"))
            digest.update(b"\n")
    elif _stat.S_ISREG(st.st_mode):
        with open(fs_path(filename), "rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        hashed_file()
    else:
        raise RuntimeError(f"不是普通资源文件：{filename}")
    return digest.hexdigest()


def _overlay_entry(relative):
    _safe_path(relative)
    parts = relative.split("/")
    logical = parts[0]
    if not _repo_dir(logical):
        raise RuntimeError(f"未知的资源集合：{parts[0]}")
    entry = f"{logical}/{parts[1]}"
    if not _ENTRY_RE.fullmatch(entry):
        raise RuntimeError(f"无效的差量资源：{relative}")
    repo_relative = f"{_repo_dir(logical)}/{'/'.join(parts[1:])}"
    return {"logical": logical, "entry": entry, "parts": parts, "repo_relative": repo_relative}


def compose_profile(package_root, selected):
    """A variant owns an entire skill directory or a single agent/command file."""
    profile = profile_name(selected)
    entries = {}
    for collection in COLLECTIONS:
        root = os.path.join(resource_root(package_root), collection["repo"])
        no_links(root)
        for name in sorted(os.listdir(fs_path(root))):
            relative = f"{collection['logical']}/{name}"
            if not _ENTRY_RE.fullmatch(relative):
                raise RuntimeError(f"无效的标准资源条目：{relative}")
            entries[relative] = {"path": relative, "source": os.path.join(root, name),
                                 "excludes": [], "sourceProfile": "standard"}
    if profile != "standard":
        overlay = read_json(os.path.join(package_root, "distribution", "manifests", "1to1.overlay.json"))
        if (not overlay or overlay.get("granularity") != "skill"
                or overlay.get("package_dir") != "migbot-1to1"
                or not isinstance(overlay.get("files"), dict)
                or not isinstance(overlay.get("excludes"), list)):
            raise RuntimeError("缺少有效的一比一差量清单")
        owned = set()
        for relative in overlay["files"]:
            info = _overlay_entry(relative)
            entry, parts = info["entry"], info["parts"]
            if (entry.startswith(("agents/", "commands/")) and len(parts) != 2) or \
                    (entry.startswith("skills/") and len(parts) < 3):
                raise RuntimeError(f"无效的差量资源：{relative}")
            owned.add(entry)
            source = os.path.join(package_root, "migbot-1to1", *parts)
            no_links(source)
            if not os.path.exists(fs_path(source)):
                raise RuntimeError(f"差量清单中的文件不存在：{relative}")
        for entry in owned:
            logical = entry.split("/", 1)[0]
            source = os.path.join(package_root, "migbot-1to1", _repo_dir(logical),
                                  entry[len(logical) + 1:])
            if entry.startswith("skills/") and not os.path.exists(fs_path(os.path.join(source, "SKILL.md"))):
                raise RuntimeError(f"差量 skill 缺少 SKILL.md：{entry}")
            entries[entry] = {"path": entry, "source": source, "excludes": [], "sourceProfile": profile}
        for relative in overlay["excludes"]:
            info = _overlay_entry(relative)
            entry, parts = info["entry"], info["parts"]
            if not _ENTRY_RE.fullmatch(entry):
                raise RuntimeError(f"无效的差量排除路径：{relative}")
            if len(parts) == 2:
                entries.pop(entry, None)
            elif entry in entries:
                entries[entry]["excludes"].append("/".join(parts[2:]))
    with hashing("Verify profile", sum(count_files(e["source"], e["excludes"]) for e in entries.values())):
        return [{**entry, "digest": tree_digest(entry["source"], entry["excludes"])}
                for entry in entries.values()]


def copy_entry(entry, destination):
    if os.path.isdir(fs_path(entry["source"])):
        copy_tree(entry["source"], destination, copy_function=shutil.copy2)
    else:
        os.makedirs(fs_path(os.path.dirname(destination)), exist_ok=True)
        copy_file(entry["source"], destination)
    for relative in entry["excludes"]:
        target = os.path.join(destination, relative)
        if os.path.isdir(fs_path(target)):
            shutil.rmtree(fs_path(target))
        elif os.path.exists(fs_path(target)):
            os.unlink(fs_path(target))


class Context:
    def __init__(self, project, state, record_file, record, package_root, router):
        self.project = project
        self.state = state
        self.record_file = record_file
        self.record = record
        self.package_root = package_root
        self.router = router

    def destination(self, relative):
        index = relative.find("/")
        logical, rest = relative[:index], relative[index + 1:]
        target = _target_dir(logical)
        if not target:
            raise RuntimeError(f"未知的资源集合：{logical}")
        return os.path.join(self.project, target, _sub_dir(logical), rest)


def installation(project):
    project = os.path.realpath(project)
    state = os.path.join(project, ".migbot", "plugin")
    record_file = os.path.join(state, "install.json")
    no_links(record_file)
    record = read_json(record_file)
    if (not record or record.get("schema") != 1 or record.get("host") not in HOSTS
            or not _DIGEST_RE.fullmatch(record.get("packageDigest", ""))
            or not isinstance(record.get("owned"), list)):
        raise RuntimeError("本工程尚未通过插件安装器安装 HMigBot")
    profile_name(record.get("profile") or "standard")
    package_root = os.path.join(state, "packages", record["packageDigest"])
    if os.path.abspath(record.get("packageRoot", "")) != package_root:
        raise RuntimeError("安装包不属于当前工程；请重新安装插件")
    router = os.path.join(project, ".migbot", "router")
    targets = [os.path.join(project, rel) for rel in
               (".claude", ".claude/skills", ".claude/agents", ".claude/commands")]
    for filename in [package_root, router, *targets]:
        no_links(filename)
    resources = [entry for entry in record["owned"] if entry["path"].startswith(("skills/", "agents/", "commands/"))]
    if any(not _ENTRY_RE.fullmatch(entry["path"]) or not _DIGEST_RE.fullmatch(entry["digest"])
           for entry in resources) or len({entry["path"] for entry in resources}) != len(resources):
        raise RuntimeError("安装记录的资源归属无效")
    return Context(project, state, record_file, record, package_root, router)


def _locked(context, callback):
    lock = os.path.join(context.state, "install.lock")
    try:
        os.mkdir(fs_path(lock))
    except FileExistsError:
        raise RuntimeError("安装或切换正在进行，请稍后重试")
    try:
        write_json(os.path.join(lock, "owner.json"), {"pid": os.getpid(), "project": context.project})
        return callback()
    finally:
        owner = os.path.join(lock, "owner.json")
        if os.path.exists(fs_path(owner)):
            os.unlink(fs_path(owner))
        os.rmdir(fs_path(lock))


def _artifact_gate(context, profile):
    if profile == (context.record.get("profile") or "standard"):
        return
    for relative in ("spec/baseline", "spec/execution", "spec/migration-report.md", "spec/verify-report.md"):
        filename = os.path.join(context.project, relative)
        if os.path.exists(fs_path(filename)) and (not os.path.isdir(fs_path(filename)) or os.listdir(fs_path(filename))):
            raise RuntimeError(f"已有迁移产物 {relative}，不能直接跨策略续跑；请在新的迁移工程中选择策略")


def _plan_switch(context, profile, backup_modified):
    _artifact_gate(context, profile)
    desired = compose_profile(context.package_root, profile)
    operations, conflicts = [], []
    old = {entry["path"]: entry for entry in context.record["owned"] if _ENTRY_RE.fullmatch(entry["path"])}
    nxt = {entry["path"]: entry for entry in desired}
    for relative in sorted(set(old) | set(nxt)):
        filename = context.destination(relative)
        no_links(filename)
        actual = tree_digest(filename) if os.path.exists(fs_path(filename)) else None
        if actual and relative not in old:
            conflicts.append(f"未受管同名资源：{relative}")
            continue
        if actual and actual != old.get(relative, {}).get("digest") and not backup_modified:
            conflicts.append(f"受管资源已修改：{relative}")
            continue
        wanted = nxt[relative]["digest"] if relative in nxt else None
        if actual != wanted:
            operations.append({"path": relative, "before": actual, "entry": nxt.get(relative)})
    if conflicts:
        raise RuntimeError("\n".join(conflicts) + "\n自定义资源会保留；需要覆盖受管修改时可明确使用 --backup-modified。")
    return desired, operations


def router_status(project):
    context = installation(project)
    return {"project": context.project, "profile": context.record.get("profile") or "standard",
            "profiles": PROFILES, "request": read_json(os.path.join(context.router, "request.json")),
            "result": read_json(os.path.join(context.router, "result.json")),
            "recoveryRequired": os.path.exists(fs_path(os.path.join(context.router, "transaction.json")))}


def request_switch(project, selected, dry_run=False, backup_modified=False):
    context = installation(project)
    profile = profile_name(selected)

    def run():
        if os.path.exists(fs_path(os.path.join(context.router, "transaction.json"))):
            raise RuntimeError("上次切换未完成，请退出宿主后执行 --recover --offline")
        if read_json(os.path.join(context.router, "request.json")):
            raise RuntimeError("已有待处理的策略切换；可先查看状态或 --cancel")
        _desired, operations = _plan_switch(context, profile, backup_modified)
        preview = {
            "from": context.record.get("profile") or "standard", "to": profile,
            "replace": [op["path"] for op in operations if op["entry"] and op["before"]],
            "add": [op["path"] for op in operations if op["entry"] and not op["before"]],
            "remove": [op["path"] for op in operations if not op["entry"]],
        }
        if dry_run:
            return {"status": "preview", **preview}
        if preview["from"] == profile and not operations:
            return {"status": "unchanged", "profile": profile}
        os.makedirs(fs_path(context.router), exist_ok=True)
        request = {"schema": 1, "id": str(uuid.uuid4()), "project": context.project,
                   "packageDigest": context.record["packageDigest"],
                   "from": preview["from"], "profile": profile, "backupModified": backup_modified,
                   "createdAt": _now()}
        write_json(os.path.join(context.router, "request.json"), request)
        return {"status": "queued", "requestID": request["id"], **preview}

    return _locked(context, run)


def _now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _rollback(context, journal):
    if journal["project"] != context.project or not _UUID_RE.fullmatch(journal["id"]):
        raise RuntimeError("恢复记录不属于本工程")
    directory = os.path.join(context.router, "transactions", journal["id"])
    for index, item in reversed(list(enumerate(journal["operations"]))):
        if not _ENTRY_RE.fullmatch(item["path"]):
            raise RuntimeError("恢复记录中含有无效路径")
        destination = context.destination(item["path"])
        backup = os.path.join(directory, "backup", str(index))
        incoming = os.path.join(directory, "incoming", str(index))
        for filename in (destination, backup, incoming):
            no_links(filename)
        if os.path.exists(fs_path(backup)) or (not item["before"] and not os.path.exists(fs_path(incoming))):
            if os.path.exists(fs_path(destination)) and tree_digest(destination) != item["after"]:
                raise RuntimeError(f"恢复时发现新的修改，已保留现场：{item['path']}")
            if os.path.isdir(fs_path(destination)):
                shutil.rmtree(fs_path(destination))
            elif os.path.exists(fs_path(destination)):
                os.unlink(fs_path(destination))
            if os.path.exists(fs_path(backup)):
                os.rename(fs_path(backup), fs_path(destination))
    write_json(context.record_file, journal["beforeRecord"])
    projection = os.path.join(context.router, "projection-manifest.json")
    if journal.get("beforeProjection"):
        write_json(projection, journal["beforeProjection"])
    elif os.path.exists(fs_path(projection)):
        os.unlink(fs_path(projection))
    os.unlink(fs_path(os.path.join(context.router, "transaction.json")))


def apply_pending(project):
    context = installation(project)
    request_file = os.path.join(context.router, "request.json")
    if not os.path.exists(fs_path(request_file)):
        return None

    def run():
        if os.path.exists(fs_path(os.path.join(context.router, "transaction.json"))):
            raise RuntimeError("上次切换未完成，请退出宿主后执行 --recover --offline")
        request = read_json(request_file)
        if not request:
            return None
        journal = None
        directory = None
        try:
            if (request.get("schema") != 1 or not _UUID_RE.fullmatch(request.get("id", ""))
                    or request.get("project") != context.project
                    or request.get("packageDigest") != context.record["packageDigest"]
                    or request.get("from") != (context.record.get("profile") or "standard")):
                raise RuntimeError("切换请求与当前安装不匹配，请重新选择策略")
            profile = profile_name(request["profile"])
            desired, operations = _plan_switch(context, profile, request.get("backupModified") is True)
            directory = os.path.join(context.router, "transactions", request["id"])
            no_links(directory)
            os.makedirs(fs_path(os.path.join(directory, "incoming")), exist_ok=True)
            os.makedirs(fs_path(os.path.join(directory, "backup")), exist_ok=True)
            for index, item in enumerate(operations):
                if not item["entry"]:
                    continue
                incoming = os.path.join(directory, "incoming", str(index))
                copy_entry(item["entry"], incoming)
                if tree_digest(incoming) != item["entry"]["digest"]:
                    raise RuntimeError(f"暂存资源校验失败：{item['path']}")
            for item in operations:
                destination = context.destination(item["path"])
                no_links(destination)
                current = tree_digest(destination) if os.path.exists(fs_path(destination)) else None
                if current != item["before"]:
                    raise RuntimeError(f"暂存期间资源被修改：{item['path']}")
            journal = {"schema": 1, "id": request["id"], "project": context.project,
                       "beforeRecord": context.record,
                       "beforeProjection": read_json(os.path.join(context.router, "projection-manifest.json")),
                       "operations": [{"path": item["path"], "before": item["before"],
                                       "after": item["entry"]["digest"] if item["entry"] else None}
                                      for item in operations]}
            write_json(os.path.join(directory, "journal.json"), journal)
            write_json(os.path.join(context.router, "transaction.json"), journal)
            for index, item in enumerate(operations):
                destination = context.destination(item["path"])
                os.makedirs(fs_path(os.path.dirname(destination)), exist_ok=True)
                if item["before"]:
                    os.rename(fs_path(destination), fs_path(os.path.join(directory, "backup", str(index))))
                if item["entry"]:
                    os.rename(fs_path(os.path.join(directory, "incoming", str(index))), fs_path(destination))
            owned = [entry for entry in context.record["owned"] if not _ENTRY_RE.fullmatch(entry["path"])]
            owned += [{"path": entry["path"], "digest": entry["digest"]} for entry in desired]
            write_json(context.record_file, {**context.record, "profile": profile, "owned": owned})
            write_json(os.path.join(context.router, "projection-manifest.json"), {
                "schema": 1, "profile": profile, "packageDigest": context.record["packageDigest"],
                "transactionID": request["id"],
                "resources": [{"path": entry["path"], "digest": entry["digest"],
                               "sourceProfile": entry["sourceProfile"]} for entry in desired]})
            result = {"status": "applied", "requestID": request["id"], "profile": profile,
                      "changedEntries": len(operations),
                      "backup": os.path.join(directory, "backup"), "appliedAt": _now()}
            write_json(os.path.join(context.router, "result.json"), result)
            os.unlink(fs_path(request_file))
            os.unlink(fs_path(os.path.join(context.router, "transaction.json")))
            journal = None
            return result
        except Exception as exc:
            if journal:
                _rollback(context, journal)
            elif directory and os.path.exists(fs_path(directory)):
                # Failed before a journal was published; drop the staged transaction directory.
                shutil.rmtree(fs_path(directory))
            result = {"status": "failed", "requestID": request.get("id"), "error": str(exc)}
            write_json(os.path.join(context.router, "result.json"), result)
            if os.path.exists(fs_path(request_file)):
                os.unlink(fs_path(request_file))
            return result

    return _locked(context, run)


def cancel_request(project):
    context = installation(project)

    def run():
        if os.path.exists(fs_path(os.path.join(context.router, "transaction.json"))):
            raise RuntimeError("事务正在执行或需要恢复，不能取消")
        request_file = os.path.join(context.router, "request.json")
        if os.path.exists(fs_path(request_file)):
            os.unlink(fs_path(request_file))
        return {"status": "cancelled", "profile": context.record.get("profile") or "standard"}

    return _locked(context, run)


def recover_switch(project):
    context = installation(project)
    lock = os.path.join(context.state, "install.lock")
    if os.path.exists(fs_path(lock)):
        no_links(lock)
        owner = read_json(os.path.join(lock, "owner.json"))
        if not owner or not isinstance(owner.get("pid"), int) or owner["pid"] <= 0 \
                or owner.get("project") != context.project:
            raise RuntimeError("安装锁归属未知，请确认旧安装进程退出后人工检查安装锁")
        try:
            os.kill(owner["pid"], 0)
            raise RuntimeError("安装或切换进程仍在运行，不能恢复")
        except ProcessLookupError:
            pass
        shutil.rmtree(fs_path(lock))

    def run():
        journal = read_json(os.path.join(context.router, "transaction.json"))
        if not journal:
            return {"status": "unchanged", "profile": context.record.get("profile") or "standard"}
        _rollback(context, journal)
        request_file = os.path.join(context.router, "request.json")
        if os.path.exists(fs_path(request_file)):
            os.unlink(fs_path(request_file))
        result = {"status": "recovered", "profile": journal["beforeRecord"].get("profile") or "standard",
                  "requestID": journal["id"]}
        write_json(os.path.join(context.router, "result.json"), result)
        return result

    return _locked(context, run)
