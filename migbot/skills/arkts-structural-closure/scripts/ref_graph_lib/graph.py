"""EtsRefGraph — Project-wide reference graph.

Nodes: .ets files
Edges:
  - import:        importer → imported file
  - instantiation: file → class (resolved across imports to find owner file)

Orphan detection: given a set of candidate "VM/Repo" files, check that each
exported class has at least one UI file (page/component/widget) that
imports + instantiates it.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from .ets_parser import EtsFileInfo, parse_ets_file
from .import_resolver import resolve_import_path


ASSEMBLY_STEM = "AppAssembly"
_UI_PATH_HINTS = ("/pages/", "/components/", "/widgets/", "/views/", "/dialogs/", "/dialog/")
# Symmetric matcher for Windows backslashes
_UI_PATH_HINTS_BS = tuple(p.replace("/", "\\") for p in _UI_PATH_HINTS)

# Type-level exports: consumed via member access (Enum.Member) or type position
# (`: IFoo`), never via `new X(` — instantiation-based orphan checks don't apply.
# (Known-FP class: enums like HomeUiState flagged IMPORTED_BUT_NOT_INSTANTIATED.)
_TYPE_LEVEL_KINDS = ("enum", "interface")


# '…' / "…" 不跨行：正则字面量里落单的引号（/['"]/）若可跨行配对，会把后面
# 整段真实代码当字符串抹掉，制造"找不到调用"的误报。只有模板串允许跨行。
_NONCODE = re.compile(
    r"(?P<string>'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"|`(?:\\.|[^`\\])*`)"
    r"|//[^\n]*|/\*[\s\S]*?\*/"
)


def mask_noncode(text: str, *, keep_strings: bool = False) -> str:
    """Mask comments/literals without shifting offsets or line numbers.

    Keeping literals is only for reading route/import names; callers still
    check the keyword's offset in the fully masked text. Template literals
    are conservatively masked, including interpolations (no invented usage).
    """
    def replace(match):
        if keep_strings and match.group("string") is not None:
            return match.group()
        return re.sub(r"[^\n]", " ", match.group())
    return _NONCODE.sub(replace, text)


def _matching_end(text: str, opening: int, left="{", right="}") -> Optional[int]:
    depth = 0
    for i in range(opening, len(text)):
        if text[i] == left:
            depth += 1
        elif text[i] == right:
            depth -= 1
            if depth == 0:
                return i
    return None


def _brace_depths(text: str) -> list[int]:
    depth, result = 0, []
    for char in text:
        result.append(depth)
        depth += (char == "{") - (char == "}")
    return result


def _initializer(text: str, start: int) -> str:
    """Read a simple member initializer, ignoring delimiters inside containers."""
    start += len(text[start:]) - len(text[start:].lstrip())
    stack = []
    for end in range(start, len(text)):
        char = text[end]
        if not stack and char in ";,\n}":
            return text[start:end].strip()
        if char in "({[":
            stack.append(char)
        elif char in ")}]":
            if not stack:
                return ""
            stack.pop()
    return text[start:].strip()


def _new_type(expression: str) -> Optional[str]:
    match = re.match(r"new\s+([A-Za-z_]\w*)\s*\(", expression)
    if match and _matching_end(expression, match.end() - 1, "(", ")") == len(expression) - 1:
        return match.group(1)
    match = re.fullmatch(r"([A-Za-z_]\w*)\.(?:getInstance|shared)\(\)", re.sub(r"\s+", "", expression))
    return match.group(1) if match else None


def assembly_target_paths(source: str, target: str) -> set[str]:
    """Prove complete access paths to a target; unknown shapes stay unresolved.

    Supported: direct assembly fields (static or beneath a constructed singleton),
    module constants, capabilityTable slots, and single-return methods/getters.
    Merely returning the target *type* or having a same-named member elsewhere
    supplies no evidence. All candidates retain their complete receiver path.
    """
    code = mask_noncode(source)
    depths = _brace_depths(code)
    known, public, pending = {}, set(), []
    # Module constants are also legitimate holders used by capabilityTable.
    module_re = re.compile(r"(?P<export>export\s+)?(?:const|let)\s+(?P<name>\w+)\s*(?::[^=;\n]+)?=\s*")
    tables = []
    for match in module_re.finditer(code):
        if depths[match.start()] != 0:
            continue
        name, expression = match.group("name"), _initializer(code, match.end())
        if name == "capabilityTable" and expression.startswith("{") and expression.endswith("}"):
            tables.append(expression[1:-1])
        else:
            pending.append((name, expression, ""))
        if match.group("export"):
            public.add(name)

    classes = list(re.finditer(r"\bclass\s+AppAssembly\s*\{", code))
    if len(classes) == 1:
        end = _matching_end(code, classes[0].end() - 1)
        body = code[classes[0].end():end] if end is not None else ""
        body_depths = _brace_depths(body)
        member_re = re.compile(
            r"(?<![\w.])(?P<mods>(?:(?:public|private|protected|readonly|static)\s+)*)"
            r"(?P<name>[A-Za-z_]\w*)\s*(?::[^=;\n{}]+)?=\s*"
        )
        fields = []
        for match in member_re.finditer(body):
            if body_depths[match.start()] != 0:
                continue
            fields.append((match.group("name"), "static" in match.group("mods").split(),
                           _initializer(body, match.end())))
        roots = {"AppAssembly." + name for name, static, expr in fields
                 if static and _new_type(expr) == ASSEMBLY_STEM}
        for name, static, expression in fields:
            for receiver in ([ASSEMBLY_STEM] if static else sorted(roots)):
                path = receiver + "." + name
                pending.append((path, expression, receiver))
                public.add(path)
        methods = re.compile(
            r"(?<![\w.])(?P<mods>(?:(?:public|private|protected|static)\s+)*)"
            r"(?P<getter>get\s+)?(?P<name>[A-Za-z_]\w*)\s*\([^()]*\)\s*"
            r"(?::\s*[A-Za-z_]\w*)?\s*\{"
        )
        for match in methods.finditer(body):
            if body_depths[match.start()] != 0:
                continue
            end = _matching_end(body, match.end() - 1)
            method_body = body[match.end():end] if end is not None else ""
            returned = re.fullmatch(r"\s*return\s+(.+?)\s*;?\s*", method_body, re.S)
            if not returned:
                continue
            receivers = [ASSEMBLY_STEM] if "static" in match.group("mods").split() else sorted(roots)
            for receiver in receivers:
                path = receiver + "." + match.group("name") + ("" if match.group("getter") else "()")
                pending.append((path, returned.group(1).rstrip(";"), receiver))
                public.add(path)

    for table in tables:
        table_depths = _brace_depths(table)
        for match in re.finditer(r"\b([A-Za-z_]\w*)\s*:\s*", table):
            if table_depths[match.start()] == 0:
                path = "capabilityTable." + match.group(1)
                pending.append((path, _initializer(table, match.end()), ""))
                public.add(path)

    # Finite candidate paths: resolve aliases/returns without generating arbitrary
    # intermediate receivers (AppAssembly.shared.other.tracking is a distinct path).
    duplicates = {path for path, _, _ in pending if sum(p == path for p, _, _ in pending) > 1}
    for _ in range(len(pending) + 1):
        changed = False
        for path, expression, receiver in pending:
            if path in known or path in duplicates:
                continue
            constructed_type = _new_type(expression)
            expression = re.sub(r"\s+", "", expression)
            if expression.startswith("this.") and receiver:
                expression = receiver + expression[len("this"):]
            kind = constructed_type or known.get(expression)
            if kind:
                known[path] = kind
                changed = True
        if not changed:
            break
    return {path for path, kind in known.items() if kind == target and path in public}


@dataclass
class OrphanFinding:
    file: str               # repo-relative path of the orphan VM/Repo file
    class_name: str
    reason: str             # NO_IMPORTER | IMPORTED_BUT_NOT_INSTANTIATED | ONLY_INSTANTIATED_BY_VMS
    importers: list[str] = field(default_factory=list)
    instantiators: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# `import { A, X } from '...'` / `export { A, X } from '...'` / `import type { X }`（可跨行）
# 导入 / 导出列表都不是使用：`import { A, X } from` / `import D, { X } from` / `import type { X } from` /
# `export { A, X }`（本地再导出，可不带 from）。_raw_text 已遮罩字符串，模块路径不可见，所以只匹配到 from 为止。
_IMPORT_EXPORT_LIST = re.compile(
    r"\b(?:import\s+(?:type\s+)?(?:[A-Za-z_$][\w$]*\s*,\s*)?\{[^}]*\}\s*from\b"
    r"|export\s+(?:type\s+)?\{[^}]*\}(?:\s*from\b)?)", re.S)


class EtsRefGraph:
    def __init__(self, project_root: Path, skip_parts: Optional[set[str]] = None):
        self.project_root = project_root.resolve()
        self.skip_parts = skip_parts or {"oh_modules", "node_modules", "build", ".cxx", ".preview", "ohosTest",
                                         "test", "tests", ".claude"}
        self.files: list[Path] = []
        self._assembly_files: list[Path] = []
        self.info: dict[Path, EtsFileInfo] = {}
        # class_name → set of files that export it
        self.export_index: dict[str, set[Path]] = {}
        # class_name → set of files that instantiate it
        self.instantiator_index: dict[str, set[Path]] = {}
        # importer_file → set of (imported_file, named_set)
        self.import_edges: dict[Path, list[dict]] = {}
        # path → comment-stripped source text (lazy cache for usage_evidence)
        self._text_cache: dict[Path, str] = {}
        self._import_bindings_cache: dict[tuple[Path, Path], dict[str, str]] = {}
        self._assembly_paths_cache: dict[tuple[Path, str], set[str]] = {}
        self._shared_use_cache: dict[tuple[Path, str], Optional[str]] = {}

    # ─── Build ───────────────────────────────────────────────────────────────
    def build(self) -> "EtsRefGraph":
        # 1. Discover .ets files (pruned walk — rglob would descend into
        #    oh_modules/build before filtering)
        import sys as _sys
        _scripts_dir = str(Path(__file__).resolve().parent.parent)
        if _scripts_dir not in _sys.path:
            _sys.path.insert(0, _scripts_dir)
        from fswalk import walk_files
        self.files = walk_files(self.project_root, ".ets", self.skip_parts)
        self._assembly_files = [path for path in self.files if path.stem == ASSEMBLY_STEM]

        # 2. Parse each
        for f in self.files:
            self.info[f] = parse_ets_file(f)

        # 3. Build export & instantiator indexes
        for f, info in self.info.items():
            for cls in info.exports:
                self.export_index.setdefault(cls, set()).add(f)
            for cls in info.instantiations:
                self.instantiator_index.setdefault(cls, set()).add(f)

        # 4. Resolve import edges to actual file paths
        for f, info in self.info.items():
            edges = []
            for imp in info.imports:
                src = imp.get("src", "")
                resolved = resolve_import_path(src, f, self.project_root)
                if resolved is not None:
                    edges.append({
                        "target": resolved,
                        "names": imp.get("names") or ([imp["name"]] if imp.get("name") else []),
                        "kind": imp["kind"],
                    })
            self.import_edges[f] = edges

        return self

    # ─── Queries ─────────────────────────────────────────────────────────────
    def importers_of(self, target_file: Path) -> list[Path]:
        """Files that have an `import ... from <target>` edge."""
        target = target_file.resolve()
        return [f for f, edges in self.import_edges.items()
                if any(e["target"] == target for e in edges)]

    def importers_of_class(self, class_name: str) -> list[Path]:
        """Files whose import names include `class_name` from a file that exports it."""
        out: list[Path] = []
        exporting_files = self.export_index.get(class_name, set()) | {
            f for f, info in self.info.items() if class_name in info.reexports
        }
        if not exporting_files:
            return out
        for f, edges in self.import_edges.items():
            for e in edges:
                if e["target"] in exporting_files and (
                    not e["names"] or class_name in e["names"]
                    or e["kind"] in ("ns", "default")
                ):
                    out.append(f)
                    break
        return out

    def instantiators_of_class(self, class_name: str) -> list[Path]:
        return list(self.instantiator_index.get(class_name, set()))

    def shared_instance_evidence(self, consumer: Path, target: str) -> Optional[str]:
        """Actual consumer access to a complete, proven assembly holder path."""
        # 无组装根的工程（930 主线默认形态）直接短路：find_orphans / 可达性闭包
        # 会按 文件×类 反复调用，先 resolve 再查缓存会让单 slice 慢一个数量级。
        if not self._assembly_files:
            return None
        consumer = consumer.resolve()
        key = (consumer, target)
        if key in self._shared_use_cache:
            return self._shared_use_cache[key]
        definitions = self.export_index.get(target, set())
        if len(definitions) != 1:
            self._shared_use_cache[key] = None
            return None
        defining = next(iter(definitions))
        for assembly in self._assembly_files:
            if assembly == consumer:
                continue
            if defining != assembly and self._real_import_bindings(assembly, defining).get(target) != target:
                continue
            bindings = self._real_import_bindings(consumer, assembly)
            if not bindings:
                continue
            path_key = (assembly, target)
            if path_key not in self._assembly_paths_cache:
                self._assembly_paths_cache[path_key] = assembly_target_paths(self._raw_text(assembly), target)
            for path in sorted(self._assembly_paths_cache[path_key]):
                root = path.split(".", 1)[0]
                local = bindings.get(root)
                if local is None:
                    continue
                local_path = local + path[len(root):]
                pattern = re.escape(local_path).replace(r"\.", r"\s*\.\s*").replace(r"\(\)", r"\s*\(\s*\)")
                code = self._raw_text(consumer)
                for match in re.finditer(r"(?<![\w$])" + pattern + r"(?![\w$])", code):
                    if re.search(r"\.\s*$", code[:match.start()]):
                        continue
                    self._shared_use_cache[key] = f"shared-instance:{self._rel(consumer)}:{path}"
                    return self._shared_use_cache[key]
        self._shared_use_cache[key] = None
        return None

    # ─── Orphan detection ────────────────────────────────────────────────────
    def find_orphans(self, candidate_files: list[Path]) -> list[OrphanFinding]:
        """For each candidate (typically VM/Repo file), check every exported
        class for: at-least-one importer AND at-least-one instantiator AND
        at-least-one UI-wired instantiator.

        Exemptions (known false-positive classes, see pokedex retrospective):
        - enum / interface exports: type-level, consumed via member access or
          type position — `new`-based checks don't apply, skipped entirely.
        - self-consumed helper: a class instantiated/typed-ref'd inside its own
          defining file (e.g. UI-state class built by static factories) is not
          an orphan when its defining file is itself UI-wired.
        - transitive instantiation: the "UI-layer instantiator" check accepts
          UI-*reachable* files (Repo instantiated by a VM that a page
          instantiates counts as wired), not only direct /pages|components/.
        """
        results: list[OrphanFinding] = []
        ui_reach = self._ui_reachable_files()
        for vm_file in candidate_files:
            vm_file = vm_file.resolve()
            info = self.info.get(vm_file)
            if info is None:
                continue
            exported = info.exports
            if not exported:
                continue

            for cls in exported:
                # Exemption 1: type-level exports (enum / interface)
                if info.export_kinds.get(cls) in _TYPE_LEVEL_KINDS:
                    continue

                # Exemption 2: self-consumed helper in a UI-wired file
                self_use = cls in info.instantiations or cls in info.typed_refs
                if self_use and vm_file in ui_reach:
                    continue

                importers = self.importers_of_class(cls)
                # Exclude self-import edge cases
                importers = [i for i in importers if i != vm_file]

                if not importers:
                    results.append(OrphanFinding(
                        file=self._rel(vm_file),
                        class_name=cls,
                        reason="NO_IMPORTER",
                    ))
                    continue

                instantiators = self.instantiators_of_class(cls)
                instantiators = [i for i in instantiators if i != vm_file]

                # Allow @Param/@Local typed-ref to count toward "in use"
                typed_ref_files = [
                    f for f, fi in self.info.items()
                    if cls in fi.typed_refs and f != vm_file
                ]

                if not instantiators and not typed_ref_files:
                    results.append(OrphanFinding(
                        file=self._rel(vm_file),
                        class_name=cls,
                        reason="IMPORTED_BUT_NOT_INSTANTIATED",
                        importers=[self._rel(p) for p in importers],
                    ))
                    continue

                # Check UI-wired instantiator (Exemption 3: transitive closure —
                # an instantiator counts if it is a UI file OR is itself
                # instantiated by a UI-reachable file, e.g. Page→VM→Repo).
                ui_instantiators = [
                    p for p in instantiators + typed_ref_files
                    if p in ui_reach and p.stem != ASSEMBLY_STEM
                ]
                ui_instantiators.extend(p for p in ui_reach if self.shared_instance_evidence(p, cls))
                if not ui_instantiators and (instantiators or typed_ref_files):
                    results.append(OrphanFinding(
                        file=self._rel(vm_file),
                        class_name=cls,
                        reason="ONLY_INSTANTIATED_BY_NON_UI",
                        instantiators=[self._rel(p) for p in instantiators + typed_ref_files],
                    ))

        return results

    def _ui_reachable_files(self) -> set[Path]:
        """Files transitively wired to the UI layer.

        Seed: files under a UI path hint (/pages|components|widgets|views|dialogs/).
        Closure: a file joins the set when any class it exports is instantiated
        (or typed-ref'd) by a file already in the set. This models the
        Page → ViewModel → Repository/Callbacks instantiation chain so that
        deep-layer classes instantiated by a UI-wired VM are not flagged
        ONLY_INSTANTIATED_BY_NON_UI (known false-positive class).
        """
        reach: set[Path] = {f for f in self.files if self._is_ui_file(f) and f.stem != ASSEMBLY_STEM}
        changed = True
        while changed:
            changed = False
            for f, info in self.info.items():
                if f in reach:
                    continue
                # An assembly owns independent capabilities. Importing or using
                # one member must never make every instance in its file reachable.
                if f.stem == ASSEMBLY_STEM:
                    continue
                for cls in info.exports:
                    users = set(self.instantiator_index.get(cls, set())) | {
                        uf for uf, fi in self.info.items() if cls in fi.typed_refs
                    }
                    users.discard(f)
                    if users & reach or any(self.shared_instance_evidence(p, cls) for p in reach):
                        reach.add(f)
                        changed = True
                        break
        return reach

    def find_orphan_components(self, candidate_files: list[Path]) -> list[OrphanFinding]:
        """Component-struct inbound check (E1: Fragment/child-page inbound edge).

        UI components are rendered via `Foo()` (not `new`), so the VM
        instantiation checks don't apply. The one reliable orphan signal for a
        component is NO_IMPORTER: ArkUI requires an `import` to reference a
        component, so a /components|views|widgets|dialogs/ struct that no other .ets file
        imports is never embedded anywhere. Only NO_IMPORTER is emitted — an
        imported-but-render-invoked component has an importer and is NOT flagged,
        so there is no false-positive on legitimately-embedded components.

        Exception (same-file sibling render): ArkUI needs no import to embed a
        struct from its OWN defining file, so a multi-struct file (e.g. a parent
        component rendering child variants declared alongside it) embeds without
        any import edge. `_same_file_rendered` recognizes exactly that render
        call, keeping the import proxy's "never embedded" claim true for the
        same-file case. Exclusions (`new X(`, `builder: X(`, `.X(`) keep the
        @CustomDialog self-reference loophole (see structural_loop Exemption 4
        comment) firmly closed.
        """
        results: list[OrphanFinding] = []
        for comp_file in candidate_files:
            comp_file = comp_file.resolve()
            info = self.info.get(comp_file)
            if info is None or not info.exports:
                continue
            src = self._raw_text(comp_file)
            for cls in info.exports:
                if info.export_kinds.get(cls) in _TYPE_LEVEL_KINDS:
                    continue   # enum/interface exported alongside a struct — type-level
                importers = [i for i in self.importers_of_class(cls) if i != comp_file]
                if not importers:
                    if self._same_file_rendered(cls, src):
                        continue   # embedded by a sibling struct in the same file — not an orphan
                    results.append(OrphanFinding(
                        file=self._rel(comp_file),
                        class_name=cls,
                        reason="NO_IMPORTER",
                    ))
        return results

    def _same_file_rendered(self, cls: str, src: str) -> bool:
        """True when `cls` is render-invoked (`X({...`) inside its own defining
        file — same-file ArkUI embedding needs no import. Conservative prefix
        exclusions: an occurrence whose nearest preceding non-whitespace is
        `new` (constructor), `:` (builder: X( / param-literal — the @CustomDialog
        self-reference case), `.` (member access) or any word char never counts.
        A declaration line (`struct X {`) carries no parenthesis and never
        matches. Commented-out calls are already stripped by _raw_text."""
        call_re = re.compile(r"\b" + re.escape(cls) + r"\s*\(")
        excl_re = re.compile(r"(?::|\.|[\w$])\s*$")
        for m in call_re.finditer(src):
            prefix = src[max(0, m.start() - 24):m.start()]
            if not excl_re.search(prefix):
                return True
        return False

    def find_unrendered_components(self, candidate_files: list[Path]) -> list[OrphanFinding]:
        """E1 residual (WARN, non-blocking): a component IMPORTED by some file but never
        used as a `Name(` call anywhere (not rendered, not new'd, not a typed @Param/@Local).
        Distinct from NO_IMPORTER. Heuristic — a component rendered indirectly (assigned to a
        variable first) is not detected, hence WARN rather than a blocking orphan.
        """
        results: list[OrphanFinding] = []
        for comp_file in candidate_files:
            comp_file = comp_file.resolve()
            info = self.info.get(comp_file)
            if info is None or not info.exports:
                continue
            for cls in info.exports:
                if info.export_kinds.get(cls) in _TYPE_LEVEL_KINDS:
                    continue   # enum/interface — never "rendered", type-level
                importers = [i for i in self.importers_of_class(cls) if i != comp_file]
                if not importers:
                    continue   # NO_IMPORTER handled by find_orphan_components
                if self.instantiators_of_class(cls):
                    continue   # new C() / C.getInstance() — used
                if any(cls in fi.typed_refs for fi in self.info.values()):
                    continue   # @Param/@Local typed ref — used
                call_re = re.compile(r"\b" + re.escape(cls) + r"\s*\(")
                rendered = any(
                    call_re.search(re.sub(r"//[^\n]*", "", p.read_text(encoding="utf-8", errors="replace")))
                    for p in importers
                )
                if not rendered:
                    results.append(OrphanFinding(
                        file=self._rel(comp_file),
                        class_name=cls,
                        reason="IMPORTED_BUT_NOT_RENDERED",
                        importers=[self._rel(p) for p in importers],
                    ))
        return results

    # ─── Utilities ───────────────────────────────────────────────────────────
    def _is_ui_file(self, p: Path) -> bool:
        s = str(p)
        return any(h in s for h in _UI_PATH_HINTS) or any(h in s for h in _UI_PATH_HINTS_BS)

    def _rel(self, p: Path) -> str:
        try:
            return str(p.relative_to(self.project_root))
        except ValueError:
            return str(p)

    def _has_real_import(self, importer: Path, target: Path) -> bool:
        """Validate import edges from the legacy parser against code tokens."""
        return bool(self._real_import_bindings(importer, target))

    def _real_import_bindings(self, importer: Path, target: Path) -> dict[str, str]:
        """Return original-to-local bindings only from actual import statements."""
        key = (importer.resolve(), target.resolve())
        if key in self._import_bindings_cache:
            return self._import_bindings_cache[key]
        raw = importer.read_text(encoding="utf-8", errors="replace")
        with_literals = mask_noncode(raw, keep_strings=True)
        code = mask_noncode(raw)
        bindings = {}
        for match in re.finditer(
            r"\bimport\s+(\{[^}]*\}|\*\s+as\s+\w+|\w+)\s+from\s*(['\"])([^'\"]+)\2",
            with_literals,
        ):
            if code[match.start():match.start() + 6] != "import":
                continue
            resolved = resolve_import_path(match.group(3), importer, self.project_root)
            if resolved is not None and resolved.resolve() == target.resolve():
                names = match.group(1)
                if names.startswith("{"):
                    for name in names[1:-1].split(","):
                        parts = re.split(r"\s+as\s+", name.strip())
                        if parts and re.fullmatch(r"[A-Za-z_]\w*", parts[0]):
                            bindings[parts[0]] = parts[-1]
                elif names.startswith("*"):
                    bindings["*"] = names.split()[-1]
                else:
                    bindings["default"] = names
        self._import_bindings_cache[key] = bindings
        return bindings

    def _raw_text(self, p: Path) -> str:
        """Code tokens, cached: comments and strings never prove usage."""
        cached = self._text_cache.get(p)
        if cached is None:
            try:
                raw = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                raw = ""
            cached = mask_noncode(raw)
            self._text_cache[p] = cached
        return cached

    def usage_evidence(self, class_name: str, defining_file_rel: str) -> Optional[str]:
        """Positive evidence that `class_name` is USED via a NON-`new` mechanism —
        precisely the blind spot of the instantiation-based orphan check (it only
        recognizes `new X()` / `X.getInstance()`). Returns an evidence tag string
        if such usage exists anywhere, else None.

        Four legitimate non-instantiation usages (validated against the aippt/
        pokedex retrospectives — these are the recurring orphan false positives):
          - supertype     `extends X` / `implements X`   → abstract base / interface
          - static-access `X.member` in another file     → static facade / const-path holder
          - own-file-use  `X.` / `: X` / `new X` in X's own file → file-private helper
          - typed-ref     `: X` / `<X>` type position     → consumed by type, not by new

        fail-tight contract: a class with NO evidence anywhere returns None and
        therefore STAYS a real orphan finding. Exemption never fires on a class
        that is genuinely referenced nowhere (a true orphan / unwired symbol).
        """
        cls = class_name
        sup = re.compile(r"(?:extends|implements)\s+(?:[\w.]+\s*,\s*)*" + re.escape(cls) + r"\b")
        static = re.compile(r"(?<!new\s)\b" + re.escape(cls) + r"\s*\.")
        # 类型位：`: X` / `<X>`，以及泛型第 N 个参数与联合类型 `Map<string, X>` / `A | X`、
        # 运行时类型判断 `instanceof X`、断言 `as X`（gpt1030_2 FV-1：PushPageInfo、RequestCancelledError）
        typ = re.compile(r"(?:[:<,|]\s*|\binstanceof\s+|\bas\s+)" + re.escape(cls) + r"\b")
        newre = re.compile(r"\bnew\s+" + re.escape(cls) + r"\b")

        def evidence_text(path):
            # Type annotations/factory returns inside the assembly prove that it
            # owns a target, not that a consumer selects that target. Let the
            # target-specific shared-use check decide; never blanket-exempt it.
            if path.stem == ASSEMBLY_STEM and cls in self.info[path].instantiations:
                return ""
            return self._raw_text(path)

        # 1. supertype use anywhere (abstract base / implemented interface)
        for f in self.files:
            if sup.search(evidence_text(f)):
                return f"supertype:{self._rel(f)}"
        # 2. static member access in ANOTHER file (static facade / const-path holder)
        for f in self.files:
            if self._rel(f) == defining_file_rel:
                continue
            src = evidence_text(f)
            if static.search(src) and not newre.search(src):
                return f"static-access:{self._rel(f)}"
        # 3. used inside its OWN defining file (file-private helper)
        for f in self.files:
            if self._rel(f) != defining_file_rel:
                continue
            src = self._raw_text(f)
            if static.search(src) or typ.search(_IMPORT_EXPORT_LIST.sub("", src)) or newre.search(src):
                return f"own-file-use:{defining_file_rel}"
            break
        # 4. typed-ref anywhere (consumed by type position, not instantiated)。导入 / 再导出列表
        #    `import { A, X } from` 里的 `, X` 不是使用——只导入不用的真孤儿不能借它豁免。
        for f in self.files:
            if typ.search(_IMPORT_EXPORT_LIST.sub("", evidence_text(f))):
                return f"typed-ref:{self._rel(f)}"
        return None
