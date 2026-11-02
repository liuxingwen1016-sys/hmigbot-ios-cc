"""assembly.py — 依赖装配可达性：用前判空的依赖字段，从启动入口能不能走到给它赋值的地方。

为什么（三次同族事故，名字每次都不一样）：
  · AIPPT_830_test_22（2026-09）：`ApplicationCompositionRoot.installApiClient(client)` 全仓零调用，
    `new ApiClient(` 零处，五个网络门面拿不到客户端；
  · AIPPT_0910_walk：同一个 installApiClient 仍零调用；
  · gpt1030_3（2026-10-19）：`EntryAbility.configureNetwork(client)` 零调用，`new NetworkClient(` 零处，
    13 个仓库的 client 字段永远是 null，登录 / 模板 / 生成全部在本地就抛「not configured」。
三次的共同形状与命名无关：
    依赖字段 `x: T | null = null`  ∧  使用前判空（抛错 / 返回）
    ∧  所有给它赋非空值的语句，都在启动入口走不到的地方
⇒ 这个依赖在运行时永远为空。

判定只用代码结构（不认注释、不认命名、不认 registry 登记）：
  · 入口 = 框架回调：struct 的全部方法；祖先链上继承工程外基类（UIAbility、StartupTask 等）、或实现工程外
    接口的类的实例方法；@Watch / @Monitor / @Builder / @Styles 回调；被加载文件（从入口文件沿 import 闭包、
    或其中的名字被可达代码引用）的模块顶层与类体代码。
  · 函数单元：方法、getter、箭头函数字段、顶层函数、顶层 const 箭头函数、顶层对象字面量的方法。
  · 调用解析：this / super / this.字段 / 类名静态调用 / X.shared()·getInstance()·instance / 参数、局部变量、
    箭头参数的类型标注或 new 推断（同名取最近一次声明）。解析不出接收者时：候选先限本文件定义或 import 进来
    的类上的同名方法，一个都没有才放宽到全工程同名方法（宁可少报，但不让无关文件里的同名调用救活注入点）。
  · 判空：if 条件里 `||` 连接的任一项（=== / == null|undefined、反写、`!x`）；块内第一条终止语句是
    throw / `return Promise.reject` → 硬判空；是 return → 软判空；`x!.` 非空断言算软判空。`x?.` 可选链不算
    （可选数据 / 可选回调大量这样写，算进来全是噪声）。
  · 分级：T 在本工程有具体实现且有硬判空 → UNASSEMBLED（必须修）；只有软判空 → UNASSEMBLED_SOFT（列清单，
    功能静默失效）；T 只有接口没有实现 → NO_IMPLEMENTATION（缺外部实现，列清单）。判空处本身走不到不报。
已知边界（不报 = 少报方向）：值依赖型故障（调用点在、但入参在运行时恒为空，如「有缓存 OAID 才初始化」）、
动态派发（字符串查表、反射）、经 HAR 包内代码完成的注入，静态判不了，交 chain-auth 契约断言与 a2h-verify。
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from typing import Optional

from .graph import mask_noncode, _matching_end, _brace_depths

_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "new", "super", "function", "typeof",
             "await", "throw", "else", "do", "try", "finally", "case", "in", "of", "delete", "void",
             "yield", "import", "export"}
_MEMBER_MODS = r"(?:(?:public|private|protected|static|async|override|readonly|declare)\s+)*"
_DECOS = r"(?P<decos>(?:@\w+(?:\s*\([^()\n]*\))?\s*)*)"
_CLASS_RE = re.compile(r"(?P<pre>(?:\bexport\s+)?(?:\bdefault\s+)?(?P<abstract>\babstract\s+)?)"
                       r"\b(?P<kind>class|struct|interface)\s+(?P<name>[A-Za-z_]\w*)(?P<head>[^{;]*)\{")
_TOP_FUNC_RE = re.compile(r"(?:\bexport\s+)?(?:\bdefault\s+)?(?:\basync\s+)?\bfunction\s+(?P<name>[A-Za-z_]\w*)"
                          r"\s*(?:<[^>{}]*>)?\s*\(")
_TOP_CONST_RE = re.compile(r"(?:\bexport\s+)?\b(?:const|let)\s+(?P<name>[A-Za-z_]\w*)\s*(?::[^=;\n]+)?=\s*")
_METHOD_RE = re.compile(_DECOS + r"(?P<mods>" + _MEMBER_MODS + r")(?:(?P<acc>get|set)\s+)?"
                        r"(?P<name>[A-Za-z_]\w*)\s*(?:<[^<>(){}]*(?:<[^<>(){}]*>[^<>(){}]*)*>)?\s*\(")
_ARROW_MEMBER_RE = re.compile(_DECOS + r"(?P<mods>" + _MEMBER_MODS + r")(?P<name>[A-Za-z_]\w*)\s*"
                              r"(?:\??\s*:\s*[^=;\n]+?)?\s*[=:]\s*(?:async\s+)?(?:<[^<>()]*>)?\s*\(")
_FIELD_RE = re.compile(r"^[ \t]*" + _DECOS + r"(?P<mods>" + _MEMBER_MODS + r")(?P<name>[A-Za-z_]\w*)\s*(?P<opt>\?)?\s*:\s*"
                       r"(?P<type>[^=;\n{}]+?)\s*(?:=\s*(?P<init>[^;\n]+?))?\s*;?\s*$", re.M)
_FIELD_INIT_RE = re.compile(r"^[ \t]*" + _DECOS + r"(?P<mods>" + _MEMBER_MODS + r")(?P<name>[A-Za-z_]\w*)\s*=\s*"
                            r"(?P<init>[^;\n]+)", re.M)
_LOCAL_RE = re.compile(r"\b(?:const|let|var)\s+(?P<name>[A-Za-z_]\w*)\s*(?::\s*(?P<type>[A-Za-z_][\w.]*))?"
                       r"[^=;\n]*?=\s*(?P<init>[^;\n]+)")
_CALL_RE = re.compile(r"(?<![\w$.])(?P<recv>(?:[A-Za-z_$][\w$]*(?:\s*\(\s*\))?\s*!?\s*\??\.\s*)*)"
                      r"(?P<name>[A-Za-z_$][\w$]*)\s*(?:<[^<>()]*>)?\s*\(")
_REF_RE = re.compile(r"(?<![\w$.])(?P<recv>(?:[A-Za-z_$][\w$]*(?:\s*\(\s*\))?\s*!?\s*\??\.\s*)+)"
                     r"(?P<name>[A-Za-z_$][\w$]*)\b(?!\s*(?:\(|<[^<>()]*>\s*\(|=(?!=)))")
_NEW_RE = re.compile(r"\bnew\s+(?P<cls>[A-Za-z_]\w*)\s*(?:<[^<>()]*>)?\s*\(")
_WATCH_RE = re.compile(r"@(?:Watch|Monitor)\s*\(\s*['\"](?P<name>[\w.]+)['\"]")
_IMPORT_RE = re.compile(r"\bimport\s+(?:type\s+)?(?P<what>[^;'\"]*?)\s*\bfrom\s*['\"](?P<spec>[^'\"]+)['\"]", re.S)
_SIDE_IMPORT_RE = re.compile(r"\bimport\s*['\"](?P<spec>[^'\"]+)['\"]")
_EXPORT_LIST_RE = re.compile(r"\bexport\s+(?:type\s+)?\{[^}]*\}(?:\s*from\s*['\"][^'\"]+['\"])?", re.S)
_DECL_PREFIX = re.compile(r"(?:^|[{};,\n])\s*(?:@\w+(?:\s*\([^()\n]*\))?\s*)*"
                          r"(?:(?:export|default|static|async|public|private|protected|override|readonly|get|set|function)\s+)*$")
_SUFFIXES = ("", ".ets", ".ts", "/Index.ets", "/index.ets", "/Index.ts")


@dataclass
class Func:
    key: tuple
    name: str
    owner: Optional[str]
    static: bool
    file: str
    start: int
    body_start: int
    end: int
    params: dict = field(default_factory=dict)
    decos: str = ""
    name_pos: int = -1
    owner_cls: Optional["Cls"] = None
    ret: Optional[str] = None                  # 返回类型（Promise<T> 拆成 T），用来解析 X.create().m()


@dataclass
class Field:
    name: str
    type_name: Optional[str]
    nullable: bool
    static: bool
    decorated: bool
    file: str
    offset: int


@dataclass
class Cls:
    name: str
    kind: str                 # class | struct | interface | object（顶层对象字面量）
    abstract: bool
    file: str
    start: int
    body_start: int
    end: int
    extends: Optional[str]
    implements: list
    fields: dict = field(default_factory=dict)
    methods: dict = field(default_factory=dict)   # name -> [Func]
    decos: str = ""


def _base_type(text: str) -> Optional[str]:
    """`T | null`、`null | T`、`T | undefined`、`Array<T>` → 第一个非 null/undefined 的类型名。"""
    for part in re.split(r"\|", text or ""):
        match = re.match(r"\s*([A-Za-z_]\w*)", part)
        if match and match.group(1) not in ("null", "undefined"):
            return match.group(1)
    return None


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _params(text: str) -> dict:
    out, depth, cur = {}, 0, ""
    for char in text + ",":
        if char in "(<[{":
            depth += 1
        elif char in ")>]}":
            depth -= 1
        if char == "," and depth == 0:
            match = re.match(r"\s*(?:\.\.\.)?([A-Za-z_]\w*)\s*\??\s*:\s*(.+)", cur, re.S)
            if match:
                out[match.group(1)] = _base_type(match.group(2))
            cur = ""
        else:
            cur += char
    return out


_TEMPLATE_RE = re.compile(r"`(?:\\.|[^`\\])*`", re.S)
_REGEX_PREV = re.compile(r"(?:[(,=:\[!&|?{};+\-*%<>~^]|\breturn|\btypeof|\bcase)\s*$")


def _restore_interpolations(raw: str, masked: str) -> str:
    """模板串整体被抹掉了；`${…}` 里是真代码（调用 / 赋值），按原文放回。"""
    out = list(masked)
    for m in _TEMPLATE_RE.finditer(raw):
        if masked[m.start()] != " ":
            continue                                       # 不是被当作字符串抹掉的那段（比如在注释里）
        i = m.start() + 1
        while i < m.end() - 1:
            if raw.startswith("${", i):
                depth, j = 0, i + 1
                while j < m.end() - 1:
                    if raw[j] == "{":
                        depth += 1
                    elif raw[j] == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                out[i + 2:j] = raw[i + 2:j]
                i = j + 1
            else:
                i += 1
    return "".join(out)


def _mask_regex_literals(code: str) -> str:
    """正则字面量里的 { } ( ) 会搅乱括号配对：按 JS 规则认出 /…/flags 并抹成空白（保持偏移）。"""
    out = list(code)
    i, n = 0, len(code)
    while i < n:
        if code[i] == "/" and i + 1 < n and code[i + 1] not in "/*" and _REGEX_PREV.search(code[max(0, i - 12):i]):
            j, in_class = i + 1, False
            while j < n and code[j] != "\n":
                ch = code[j]
                if ch == "\\":
                    j += 2
                    continue
                if ch == "[":
                    in_class = True
                elif ch == "]":
                    in_class = False
                elif ch == "/" and not in_class:
                    break
                j += 1
            if j < n and code[j] == "/":
                for k in range(i + 1, j):
                    out[k] = " "
                i = j + 1
                continue
        i += 1
    return "".join(out)


class AssemblyAnalysis:
    def __init__(self, texts: dict[str, str]):
        self.raw = texts
        self.code = {f: _mask_regex_literals(_restore_interpolations(t, mask_noncode(t))) for f, t in texts.items()}
        self.kept = {f: _mask_regex_literals(mask_noncode(t, keep_strings=True)) for f, t in texts.items()}
        self.classes: dict[str, Cls] = {}            # 名字 → 首个定义（解析用）
        self.all_classes: list[Cls] = []             # 全部定义（重名类各查各的）
        self.funcs: list[Func] = []
        self.top_funcs: dict[str, list[Func]] = {}
        self.by_name: dict[str, list[Func]] = {}
        self._file_funcs: dict[str, list[Func]] = {}
        self.imports: dict[str, dict] = {}           # 文件 → {本地名: (原名, spec)}
        self.ns_imports: dict[str, dict] = {}        # 文件 → {命名空间别名: spec}
        self.import_files: dict[str, set] = {}       # 文件 → 解析到的工程内文件
        self._skip_spans: dict[str, list] = {}       # import / export 列表区间（不算引用）
        self.defined_in: dict[str, set] = {}         # 名字（类 / 顶层函数 / 顶层 const）→ 定义文件
        for f in sorted(texts):
            self._parse_imports(f)
            self._parse_file(f)
        self.children: dict[str, set] = {}
        for c in self.all_classes:
            for parent in [c.extends, *c.implements]:
                if parent:
                    self.children.setdefault(parent, set()).add(c.name)
        self.edges: dict[tuple, set] = {}
        self.alive: set = set()
        self.loaded: set = set()
        self._solve()

    # ── 解析 ──────────────────────────────────────────────────────────
    def _resolve_spec(self, importer: str, spec: str) -> Optional[str]:
        if not (spec.startswith("./") or spec.startswith("../")):
            return None
        base = posixpath.normpath(posixpath.join(posixpath.dirname(importer.replace("\\", "/")), spec))
        for suffix in _SUFFIXES:
            if base + suffix in self._norm_keys:
                return self._norm_keys[base + suffix]
        return None

    def _parse_imports(self, f: str) -> None:
        if not hasattr(self, "_norm_keys"):
            self._norm_keys = {k.replace("\\", "/"): k for k in self.raw}
        code, kept = self.code[f], self.kept[f]
        names, ns, files, spans = {}, {}, set(), []
        for m in _IMPORT_RE.finditer(kept):
            if code[m.start()] == " ":
                continue                                   # 落在字符串里
            spans.append((m.start(), m.end()))
            spec, what = m.group("spec"), m.group("what")
            target = self._resolve_spec(f, spec)
            if target:
                files.add(target)
            star = re.search(r"\*\s*as\s+([A-Za-z_]\w*)", what)
            if star:
                ns[star.group(1)] = spec
            braces = re.search(r"\{([^}]*)\}", what, re.S)
            if braces:
                for item in braces.group(1).split(","):
                    parts = item.strip().split(" as ")
                    if parts[0].strip():
                        orig = parts[0].replace("type ", "").strip()
                        names[(parts[1] if len(parts) > 1 else orig).strip()] = (orig, spec)
            default = re.match(r"\s*([A-Za-z_]\w*)\s*(?:,|$)", what)
            if default and default.group(1) not in ("type",):
                names[default.group(1)] = (default.group(1), spec)
                ns.setdefault(default.group(1), spec)       # 默认导入也可能是命名空间（import http from '@ohos.net.http'）
        for m in _SIDE_IMPORT_RE.finditer(kept):
            if code[m.start()] != " ":
                target = self._resolve_spec(f, m.group("spec"))
                if target:
                    files.add(target)
        for m in _EXPORT_LIST_RE.finditer(code):
            spans.append((m.start(), m.end()))
        self.imports[f], self.ns_imports[f], self.import_files[f], self._skip_spans[f] = names, ns, files, spans

    def _in_skip(self, f: str, pos: int) -> bool:
        return any(a <= pos < b for a, b in self._skip_spans.get(f, ()))

    def _parse_file(self, f: str) -> None:
        code = self.code[f]
        depths = _brace_depths(code)
        for m in _CLASS_RE.finditer(code):
            if depths[m.start("kind")] != 0:
                continue
            body = m.end() - 1
            end = _matching_end(code, body)
            if end is None:
                continue
            head = m.group("head")
            ext = re.search(r"\bextends\s+([A-Za-z_]\w*)", head)
            imp = re.search(r"\bimplements\s+([^{]+)", head)
            impls = [_base_type(x) for x in re.split(r",(?![^<]*>)", imp.group(1))] if imp else []
            if m.group("kind") == "interface" and ext:
                impls, ext_name = [_base_type(x) for x in re.split(r",(?![^<]*>)",
                                                                   head.split("extends", 1)[1])], None
            else:
                ext_name = ext.group(1) if ext else None
            line_start = code.rfind("\n", 0, m.start()) + 1
            decos = code[max(0, line_start - 200):m.start()]
            cls = Cls(m.group("name"), m.group("kind"), bool(m.group("abstract")), f, m.start(), body + 1, end,
                      ext_name, [i for i in impls if i], decos=decos)
            self._add_class(cls)
            if cls.kind != "interface":
                self._parse_members(cls, code, depths)
        for m in _TOP_FUNC_RE.finditer(code):
            if depths[m.start()] != 0:
                continue
            line_start = code.rfind("\n", 0, m.start()) + 1
            decos = code[max(0, line_start - 120):m.start()]
            fn = self._func_at(f, code, m.group("name"), None, False, m.start(), m.end() - 1, decos)
            if fn:
                self.top_funcs.setdefault(fn.name, []).append(fn)
                self.defined_in.setdefault(fn.name, set()).add(f)
        for m in _TOP_CONST_RE.finditer(code):
            if depths[m.start()] != 0:
                continue
            name, rest = m.group("name"), m.end()
            self.defined_in.setdefault(name, set()).add(f)
            arrow = re.match(r"(?:async\s+)?(?:<[^<>()]*>)?\s*\(", code[rest:rest + 40])
            if arrow:                                     # const f = (…) => { … }
                fn = self._func_at(f, code, name, None, False, m.start(), rest + arrow.end() - 1, "", arrow=True)
                if fn:
                    self.top_funcs.setdefault(name, []).append(fn)
                continue
            if code[rest:rest + 1] == "{":                # const X = { m() {…}, n: () => {…} }
                end = _matching_end(code, rest)
                if end is not None:
                    obj = Cls(name, "object", False, f, m.start(), rest + 1, end, None, [])
                    self._add_class(obj)
                    self._parse_members(obj, code, depths)

    def _add_class(self, cls: Cls) -> None:
        self.classes.setdefault(cls.name, cls)
        self.all_classes.append(cls)
        self.defined_in.setdefault(cls.name, set()).add(cls.file)

    def _func_at(self, f, code, name, owner, static, start, paren, decos, arrow=False,
                 owner_cls=None) -> Optional[Func]:
        close = _matching_end(code, paren, "(", ")")
        if close is None:
            return None
        i = close + 1
        while i < len(code) and code[i] in " \t\r\n":
            i += 1
        ret_start = i + 1 if i < len(code) and code[i] == ":" else None
        if i < len(code) and code[i] == ":":            # 返回类型：到第一个不在 <>/() 里的 {（或 =>）
            depth, i = 0, i + 1
            while i < len(code):
                ch = code[i]
                if ch in "<(":
                    depth += 1
                elif ch in ">)" and not (ch == ">" and code[i - 1] == "="):
                    depth -= 1
                elif depth <= 0 and code.startswith("=>", i):
                    break
                elif ch == "{" and depth <= 0:
                    prev = code[:i].rstrip()
                    if not prev.endswith((":", "|", "&", "<", ",")):
                        break
                elif ch in ";=" and depth <= 0:
                    return None
                i += 1
        if arrow:
            while i < len(code) and code[i] in " \t\r\n":
                i += 1
            if not code.startswith("=>", i):
                return None
            i += 2
            while i < len(code) and code[i] in " \t\r\n":
                i += 1
            if i >= len(code) or code[i] != "{":        # 表达式体箭头：体到行尾
                end = code.find("\n", i)
                end = len(code) if end < 0 else end
                fn = Func((f, start), name, owner, static, f, start, i, end, _params(code[paren + 1:close]),
                          decos, name_pos=start if owner is not None else code.rfind(name, start, paren + 1),
                          owner_cls=owner_cls)
                fn.ret = self._ret_type(code, ret_start, i)
                self._register(fn)
                return fn
        if i >= len(code) or code[i] != "{":
            return None
        end = _matching_end(code, i)
        if end is None:
            return None
        fn = Func((f, start), name, owner, static, f, start, i + 1, end, _params(code[paren + 1:close]), decos,
                  name_pos=start if owner is not None else code.rfind(name, start, paren + 1), owner_cls=owner_cls)
        fn.ret = self._ret_type(code, ret_start, i)
        self._register(fn)
        return fn

    @staticmethod
    def _ret_type(code: str, start: Optional[int], end: int) -> Optional[str]:
        if start is None:
            return None
        text = code[start:end].strip().rstrip("=>").strip()
        inner = re.match(r"Promise\s*<\s*(.+)>\s*$", text)
        return _base_type(inner.group(1) if inner else text)

    def _register(self, fn: Func) -> None:
        self.funcs.append(fn)
        self.by_name.setdefault(fn.name, []).append(fn)
        self._file_funcs.setdefault(fn.file, []).append(fn)

    def _parse_members(self, cls: Cls, code: str, depths: list) -> None:
        base = depths[cls.body_start] if cls.body_start < len(depths) else 0
        for m in _METHOD_RE.finditer(code, cls.body_start, cls.end):
            name = m.group("name")
            if depths[m.start("name")] != base or name in _KEYWORDS:
                continue
            line_start = code.rfind("\n", 0, m.start("name")) + 1
            before = code[line_start:m.start("name")]
            if re.search(r"[=.(:]\s*$", before) or "=>" in before:
                continue
            fn = self._func_at(cls.file, code, name, cls.name, "static" in m.group("mods").split(),
                               m.start("name"), m.end() - 1, m.group("decos"), owner_cls=cls)
            if fn:
                cls.methods.setdefault(name, []).append(fn)
        for m in _ARROW_MEMBER_RE.finditer(code, cls.body_start, cls.end):  # 箭头函数字段 / 对象字面量箭头属性
            name = m.group("name")
            if depths[m.start("name")] != base or name in _KEYWORDS or name in cls.methods:
                continue
            fn = self._func_at(cls.file, code, name, cls.name, "static" in m.group("mods").split(),
                               m.start("name"), m.end() - 1, m.group("decos"), arrow=True, owner_cls=cls)
            if fn:
                cls.methods.setdefault(name, []).append(fn)
        if cls.kind == "object":
            return
        body_lines = code[cls.body_start:cls.end]
        offset = cls.body_start
        for m in _FIELD_RE.finditer(body_lines):
            pos = offset + m.start("name")
            if depths[pos] != base or m.group("name") in _KEYWORDS:
                continue
            type_text, init = m.group("type"), (m.group("init") or "").strip()
            unionable = bool(re.search(r"\b(?:null|undefined)\b", type_text))
            nullable = (unionable and init in ("null", "undefined")) or (bool(m.group("opt")) and not init) \
                or (unionable and not init)
            cls.fields.setdefault(m.group("name"), Field(
                m.group("name"), _base_type(type_text), nullable, "static" in m.group("mods").split(),
                bool(m.group("decos").strip()), cls.file, pos))
        for m in _FIELD_INIT_RE.finditer(body_lines):
            pos = offset + m.start("name")
            name = m.group("name")
            if depths[pos] != base or name in cls.fields or name in _KEYWORDS:
                continue
            init = m.group("init").strip()
            new = _NEW_RE.match(init)
            single = re.match(r"([A-Za-z_]\w*)\s*\.\s*(?:(?:shared|getInstance)\s*\(\s*\)|(?:instance|INSTANCE|shared)\b)", init)
            typ = new.group("cls") if new else (single.group(1) if single else None)
            cls.fields[name] = Field(name, typ, False, "static" in m.group("mods").split(),
                                     bool(m.group("decos").strip()), cls.file, pos)

    # ── 类型与调用解析 ────────────────────────────────────────────────
    def _enclosing(self, f: str, pos: int) -> Optional[Func]:
        best = None
        for fn in self._file_funcs.get(f, ()):
            if fn.body_start <= pos <= fn.end and (best is None or fn.body_start > best.body_start):
                best = fn
        return best

    def _class_at(self, f: str, pos: int) -> Optional[Cls]:
        best = None
        for c in self.all_classes:
            if c.file == f and c.body_start <= pos <= c.end and (best is None or c.body_start > best.body_start):
                best = c
        return best

    def _ancestors(self, name: Optional[str]):
        seen = set()
        while name and name in self.classes and name not in seen:
            seen.add(name)
            yield self.classes[name]
            name = self.classes[name].extends

    def _field_type(self, cls_name: Optional[str], fname: str) -> Optional[str]:
        for c in self._ancestors(cls_name):
            if fname in c.fields:
                return c.fields[fname].type_name
        return None

    def _type_of_expr(self, expr: str, fn: Optional[Func], pos: int) -> Optional[str]:
        expr = re.sub(r"^(?:await\s+)", "", expr.strip()).rstrip(";").strip()
        cast = re.search(r"\bas\s+([A-Za-z_]\w*)\s*(?:\|\s*(?:null|undefined)\s*)*$", expr)
        if cast and cast.group(1) in self.classes:
            return cast.group(1)                           # expr as T
        generic = re.search(r"\.\s*\w+\s*<\s*([A-Za-z_]\w*)\s*>\s*\(", expr)
        if generic and generic.group(1) in self.classes:
            return generic.group(1)                        # AppStorage.get<T>(…)
        new = _NEW_RE.match(expr)
        if new:
            return new.group("cls")
        prop = re.fullmatch(r"([A-Za-z_]\w*)\s*\.\s*(?:instance|INSTANCE|shared|sharedInstance|default)", expr)
        if prop and prop.group(1) in self.classes:
            return prop.group(1)
        call = re.fullmatch(r"(?P<recv>(?:[A-Za-z_$][\w$]*(?:\s*\(\s*\))?\s*\??\.\s*)+)(?P<m>[A-Za-z_]\w*)\s*\(.*\)", expr, re.S)
        if call:
            owner = self.resolve(call.group("recv"), fn, pos)
            for c in self._ancestors(owner):
                for m in c.methods.get(call.group("m"), []):
                    if m.ret in self.classes:
                        return m.ret                       # X.create() / this.getRepo() 的返回类型
        single = re.fullmatch(r"([A-Za-z_]\w*)\s*\.\s*(?:shared|getInstance)\s*\(\s*\)", expr)
        if single:
            return single.group(1)
        chain = re.fullmatch(r"[A-Za-z_$][\w$]*(?:\s*\??\.\s*[A-Za-z_$][\w$]*)*", expr)
        if chain and "." in expr:
            return self.resolve(expr + ".", fn, pos)
        return None

    def _local_type(self, fn: Optional[Func], var: str, pos: int) -> Optional[str]:
        if fn is None:
            return None
        code = self.code[fn.file]
        found = None
        for m in _LOCAL_RE.finditer(code, fn.body_start, pos):          # 同名取最近一次声明
            if m.group("name") != var:
                continue
            found = _base_type(m.group("type")) if m.group("type") else self._type_of_expr(m.group("init"), fn, m.start())
        typed = None
        for m in re.finditer(r"(?<![\w$.])" + re.escape(var) + r"\s*\??\s*:\s*([A-Za-z_]\w*)", code[fn.body_start:pos]):
            typed = m.group(1)                                         # 箭头参数 / 带标注的局部变量
        if not (found or typed):                                       # xs.forEach(v => …)：取数组元素类型
            for m in re.finditer(r"(?P<recv>(?:[A-Za-z_$][\w$]*\s*\??\.\s*)*[A-Za-z_$][\w$]*)\s*\.\s*"
                                 r"(?:forEach|map|filter|find|some|every|flatMap)\s*\(\s*\(?\s*"
                                 + re.escape(var) + r"\s*\)?\s*=>", code[fn.body_start:pos]):
                recv = m.group("recv")
                typed = self.resolve(recv + ".", fn, fn.body_start + m.start()) if "." in recv \
                    else self._local_type(fn, recv, fn.body_start + m.start())
        if found or typed:
            return found or typed
        return fn.params.get(var)

    def resolve(self, recv: str, fn: Optional[Func], pos: int) -> Optional[str]:
        """接收者表达式 → 类名；解析不出返回 None。"""
        parts = [p.strip().rstrip("!") for p in re.split(r"!?\??\.", recv.strip().rstrip(".?!").strip()) if p.strip()]
        if not parts:
            return None
        owner = fn.owner if fn else None
        head = parts[0]
        static_ctx = False
        if head == "this":
            cur = owner
        elif head == "super":
            cur = self.classes[owner].extends if owner in self.classes else None
        elif re.fullmatch(r"[A-Za-z_]\w*\s*\(\s*\)", head):
            return None
        elif self._is_local(fn, head, pos):
            cur = self._local_type(fn, head, pos)          # 局部变量 / 参数优先：同名的全局类 / 顶层对象不算（复审 #4）
        elif head in self.classes and self._class_visible(head, fn):
            cur, static_ctx = head, True
        elif fn is not None and fn.file in self.imports and head in self.imports[fn.file] \
                and self.imports[fn.file][head][0] in self.classes:
            cur, static_ctx = self.imports[fn.file][head][0], True       # import 别名
        else:
            cur = self._local_type(fn, head, pos)
        for part in parts[1:]:
            if cur is None:
                return None
            call = re.fullmatch(r"([A-Za-z_]\w*)\s*\(\s*\)", part)
            if call:
                if static_ctx and call.group(1) in ("shared", "getInstance", "instance", "get"):
                    static_ctx = False
                    continue
                ret = next((m.ret for c in self._ancestors(cur) for m in c.methods.get(call.group(1), [])
                            if m.ret in self.classes), None)
                if ret is None:
                    return None
                cur, static_ctx = ret, False
                continue
            if static_ctx and part in ("instance", "shared", "default", "INSTANCE", "sharedInstance"):
                static_ctx = False
                continue
            cur, static_ctx = self._field_type(cur, part), False
        return cur if cur in self.classes else None

    def _is_local(self, fn: Optional[Func], name: str, pos: int) -> bool:
        if fn is None:
            return False
        if name in fn.params:
            return True
        body = self.code[fn.file][fn.body_start:pos]
        n = re.escape(name)
        if re.search(r"\b(?:const|let|var)\s+" + n + r"\b|\bcatch\s*\(\s*" + n + r"\s*\)"
                     r"|(?<![\w$.])" + n + r"\s*=>", body):
            return True
        for m in re.finditer(r"\(([^()]*)\)\s*(?::\s*[\w<>\[\]|., ]+)?\s*=>", body):   # 箭头函数参数表
            if re.search(r"(?:^|,)\s*(?:\.\.\.)?" + n + r"\s*(?:\??\s*:|,|=|$)", m.group(1)):
                return True
        return False

    def _class_visible(self, name: str, fn: Optional[Func]) -> bool:
        """顶层对象字面量（小写名常见）只在定义文件或 import 了它的文件里按它解析。"""
        c = self.classes[name]
        if c.kind != "object" or fn is None:
            return True
        return c.file == fn.file or name in self.imports.get(fn.file, {})

    def _targets(self, cls_name: Optional[str], name: str, bare: bool, f: Optional[str] = None) -> list:
        if bare:
            return list(self.top_funcs.get(name, ()))
        if cls_name is None:
            return [fn for fn in self.by_name.get(name, ()) if fn.owner is not None]
        found = []
        for c in self._ancestors(cls_name):                # 重名类：同名的各份定义一起算（宁可少报，复审 #4 N9）
            same = [m for x in self.all_classes if x.name == c.name for m in x.methods.get(name, [])]
            if same:
                found += same
                break
        stack, seen = [cls_name], set()
        while stack:                                      # 子类覆写 / 接口实现
            cur = stack.pop()
            for child in self.children.get(cur, ()):
                if child in seen:
                    continue
                seen.add(child)
                found += self.classes[child].methods.get(name, []) if child in self.classes else []
                stack.append(child)
        return found

    def _is_declaration(self, code: str, name_pos: int, paren: int) -> bool:
        """`name(…)` 后紧跟 `:` / `{`、且处在成员位置（前面是 `{ } ; ,` / 行首 / 修饰符）→ 声明，不是调用。"""
        close = _matching_end(code, paren, "(", ")")
        if close is None:
            return False
        rest = code[close + 1:close + 40].lstrip()
        if not (rest.startswith(":") or rest.startswith("{")):
            return False
        return bool(_DECL_PREFIX.search(code[max(0, name_pos - 200):name_pos]))

    # ── 可达性 ────────────────────────────────────────────────────────
    def _roots(self) -> list:
        roots = []
        project = set(self.classes)
        for c in self.all_classes:
            if c.kind == "object":
                continue
            chain = [c] + [a for a in self._ancestors(c.extends)] if c.extends else [c]
            framework_base = any(x.extends is not None and x.extends not in project for x in chain)
            framework_iface = any(i not in project for x in chain for i in x.implements)
            watched = {m.group("name").split(".")[-1]
                       for m in _WATCH_RE.finditer(self.kept[c.file], c.body_start, c.end)}
            for name, fns in c.methods.items():
                for fn in fns:
                    if c.kind == "struct":
                        roots.append(fn)                  # 组件方法都由框架或 build 调
                    elif not fn.static and (framework_base or framework_iface):
                        roots.append(fn)                  # 框架子类 / 框架接口实现：实例方法由框架回调
                    elif name in watched or re.search(r"@(?:Monitor|Builder|Styles|Extend)\b", fn.decos):
                        roots.append(fn)
        for fns in self.top_funcs.values():
            for fn in fns:
                if re.search(r"@(?:Builder|Styles|Extend|Concurrent)\b", fn.decos):
                    roots.append(fn)
        return roots

    def _sites(self, fn: Optional[Func], f: str, lo: int, hi: int):
        """区间内的调用 / 方法引用 / new → 目标函数集合。"""
        code = self.code[f]
        out, seen_names = [], set()
        decl = self._decl_names.get(f, set())
        for m in _CALL_RE.finditer(code, lo, hi):
            name, recv = m.group("name"), m.group("recv")
            seen_names.add(m.start("name"))
            if name in _KEYWORDS or m.start("name") in decl or self._in_skip(f, m.start()) \
                    or self._is_declaration(code, m.start("name"), m.end() - 1):
                continue
            bare = not recv
            cls = None if bare else self.resolve(recv, fn, m.start())
            if bare and fn is not None and not self.top_funcs.get(name):
                continue
            out += self._targets(cls, name, bare, f)
        for m in re.finditer(r"\.\s*(?P<name>[A-Za-z_$][\w$]*)\s*(?:<[^<>()]*>)?\s*\(", code[lo:hi]):
            pos = lo + m.start("name")                    # 链式中段（a.of(x).b(…)）：接收者解析不了，按可见类同名算
            if pos in seen_names or self._is_declaration(code, pos, lo + m.end() - 1):
                continue
            out += self._targets(None, m.group("name"), False, f)
        for m in _REF_RE.finditer(code, lo, hi):
            name = m.group("name")
            if name not in self.by_name or self._in_skip(f, m.start()):
                continue
            cls = self.resolve(m.group("recv"), fn, m.start())
            out += self._targets(cls, name, False, f)
        for m in _NEW_RE.finditer(code, lo, hi):
            for c in self._ancestors(m.group("cls")):
                out += c.methods.get("constructor", [])
        for m in re.finditer(r"(?<![\w$.])(?P<name>[A-Za-z_]\w*)\b(?!\s*\()", code[lo:hi]):
            if m.group("name") in self.top_funcs and not self._in_skip(f, lo + m.start()) \
                    and lo + m.start() not in decl:
                out += self.top_funcs[m.group("name")]    # 顶层函数当回调传出去（import / export 语句不算）
        return out

    def _segments(self, f: str) -> list:
        """不在任何函数体里的代码区间（模块顶层、类体）。"""
        inside = sorted((fn.body_start, fn.end) for fn in self._file_funcs.get(f, ()))
        pos, segs = 0, []
        for s, e in inside:
            if s > pos:
                segs.append((pos, s))
            pos = max(pos, e)
        segs.append((pos, len(self.code[f])))
        return segs

    def _referenced_files(self, f: str, lo: int, hi: int) -> set:
        """区间里引用到的、在别的文件定义的名字 → 那些文件会被加载。"""
        out = set()
        for m in re.finditer(r"(?<![\w$.])([A-Za-z_]\w*)\b", self.code[f][lo:hi]):
            out |= self.defined_in.get(m.group(1), set())
        return out - {f}

    def _solve(self) -> None:
        self._decl_names = {}
        for fn in self.funcs:
            self._decl_names.setdefault(fn.file, set()).add(fn.name_pos)
        for fn in self.funcs:
            self.edges[fn.key] = {t.key for t in self._sites(fn, fn.file, fn.body_start, fn.end)}
        by_key = {fn.key: fn for fn in self.funcs}
        module_edges, module_refs = {}, {}
        for f in self.code:
            module_edges[f], module_refs[f] = set(), set()
            for lo, hi in self._segments(f):
                module_edges[f] |= {t.key for t in self._sites(None, f, lo, hi)}
                module_refs[f] |= self._referenced_files(f, lo, hi)
        fn_refs = {}
        work = [fn.key for fn in self._roots()]
        loaded_work = sorted({fn.file for fn in self._roots()})
        while work or loaded_work:
            while loaded_work:                            # 被加载的文件：模块顶层 / 类体代码执行，import 闭包跟着加载
                f = loaded_work.pop()
                if f in self.loaded:
                    continue
                self.loaded.add(f)
                work += [k for k in module_edges.get(f, ()) if k not in self.alive]
                loaded_work += [x for x in self.import_files.get(f, ()) | module_refs.get(f, set())
                                if x not in self.loaded]
            if not work:
                break
            key = work.pop()
            if key in self.alive:
                continue
            self.alive.add(key)
            fn = by_key[key]
            if fn.file not in self.loaded:
                loaded_work.append(fn.file)
            if key not in fn_refs:
                fn_refs[key] = self._referenced_files(fn.file, fn.body_start, fn.end)
            loaded_work += [x for x in fn_refs[key] if x not in self.loaded]
            work += [k for k in self.edges.get(key, ()) if k not in self.alive]

    def _constructed_classes(self) -> set:
        """运行时真的会被构造的类：struct（框架构造）、有可达实例方法的类、在可达函数体 / 被加载文件的模块顶层 /
        静态字段初始化 / 已构造类的实例字段初始化里被 `new` 的类（不动点）。只被 import、只出现在类型标注、
        只读了静态成员的类不算——它的实例字段初始化不会执行（复审 #1）。"""
        if hasattr(self, "_constructed"):
            return self._constructed
        project = set(self.classes)
        built = {c.name for c in self.all_classes if c.kind == "struct"}
        for c in self.all_classes:                         # 框架构造：继承框架基类 / 实现框架接口
            chain = [c] + list(self._ancestors(c.extends)) if c.extends else [c]
            if any((x.extends and x.extends not in project) or any(i not in project for i in x.implements)
                   for x in chain):
                built.add(c.name)
        texts = [self.code[fn.file][fn.body_start:fn.end] for fn in self.funcs if fn.key in self.alive]
        instance_inits: dict[str, list] = {}
        for f in self.loaded:
            code = self.code[f]
            text = list(code)
            for c in self.all_classes:
                if c.file != f:
                    continue
                text[c.start:c.end + 1] = " " * (c.end + 1 - c.start)
                for line in self._field_lines(c):
                    (texts if re.match(r"\s*(?:@\w+\s*)*(?:(?:public|private|protected|readonly)\s+)*static\b", line)
                     else instance_inits.setdefault(c.name, [])).append(line)
            for fn in self._file_funcs.get(f, ()):
                text[fn.body_start:fn.end] = " " * (fn.end - fn.body_start)
            texts.append("".join(text))
        new_re = re.compile(r"\bnew\s+([A-Za-z_]\w*)\s*(?:<[^<>()]*>)?\s*\(")
        for t in texts:
            built |= set(new_re.findall(t))
        changed = True
        while changed:                                     # 已构造类的实例字段初始化里再 new 的类
            changed = False
            for name in list(built):
                for line in instance_inits.get(name, ()):
                    for cls in new_re.findall(line):
                        if cls not in built:
                            built.add(cls)
                            changed = True
        self._explicit = set(built)                        # 明确会被构造的类（new / 框架）
        self._constructed = built | {fn.owner for fn in self.funcs if fn.key in self.alive and fn.owner and not fn.static}
        return self._constructed

    def explicitly_constructed(self) -> set:
        self._constructed_classes()
        return self._explicit

    def _field_lines(self, c: Cls) -> list:
        """类体顶层（不在方法体里）的各行。"""
        code = self.code[c.file]
        text = list(code[c.body_start:c.end])
        for fn in self._file_funcs.get(c.file, ()):
            if c.body_start <= fn.body_start <= c.end:
                lo, hi = fn.body_start - c.body_start, fn.end - c.body_start
                text[lo:hi] = " " * (hi - lo)
        return "".join(text).split("\n")

    def enclosing_unit(self, f: str, pos: int) -> Optional[Func]:
        """位置所属的函数：函数体里，或函数头（参数默认值等）。"""
        fn = self._enclosing(f, pos)
        if fn is None:
            for cand in self._file_funcs.get(f, ()):
                if cand.start <= pos < cand.body_start:
                    return cand
        return fn

    def live_at(self, f: str, pos: int) -> bool:
        """该位置的代码会被执行：在可达函数里（函数头也算该函数）；或在被加载文件的模块顶层；
        或在被可达代码用到的类的类体里（字段初始化）。"""
        fn = self.enclosing_unit(f, pos)
        if fn is not None:
            return fn.key in self.alive
        if f not in self.loaded:
            return False
        cls = self._class_at(f, pos)
        if cls is None or cls.kind == "object":
            return True                                    # 模块顶层 / 顶层对象字面量：随文件加载执行
        if re.match(r"\s*(?:@\w+\s*)*(?:(?:public|private|protected|readonly)\s+)*static\b",
                    self._member_line(cls, pos)):
            return True                                    # 静态字段初始化：类定义时（文件加载）就执行
        return cls.name in self._constructed_classes()     # 实例字段初始化：类被构造过才执行

    def _member_line(self, cls: Cls, pos: int) -> str:
        """pos 所在的类成员声明的首行（多行数组 / 对象初始化的续行要追到声明那一行）。"""
        code = self.code[cls.file]
        if not hasattr(self, "_nest"):
            self._nest = {}
        if cls.file not in self._nest:
            depth, out = 0, []
            for ch in code:
                out.append(depth)
                depth += (ch in "([{") - (ch in ")]}")
            self._nest[cls.file] = out
        nest = self._nest[cls.file]
        base = nest[cls.body_start]
        start = code.rfind("\n", 0, pos) + 1
        while start > cls.body_start:
            first = start + len(code[start:pos]) - len(code[start:pos].lstrip())
            if first < len(nest) and nest[first] == base and code[first:pos].strip():
                break
            start = code.rfind("\n", 0, start - 1) + 1
        return code[start:code.find("\n", start) if code.find("\n", start) >= 0 else len(code)]

    # ── 依赖字段 ──────────────────────────────────────────────────────
    def _family(self, c: Cls) -> set:
        return {x.name for x in self._ancestors(c.name)} | self._descendants(c.name) | {c.name}

    def _guards(self, c: Cls, fname: str) -> tuple[list, list]:
        """(硬判空位置, 软判空位置)。只认本类（及子类）类体里的判空。"""
        family = self._family(c)
        hard, soft = [], []
        recv = r"(?:this|" + "|".join(re.escape(n) for n in sorted(family)) + r")\s*\.\s*" + re.escape(fname) + r"\b"
        files = {x.file for x in self.all_classes if x.name in family}
        for f in files:
            code = self.code[f]

            def inside(pos: int) -> bool:
                at = self._class_at(f, pos)
                return at is not None and at.name in family

            aliases = {m.group(1) for m in re.finditer(
                r"\b(?:const|let)\s+(\w+)\s*(?::[^=;\n]+)?=\s*" + recv + r"(?!\s*\.|\s*\()", code)}
            subject = recv if not aliases else r"(?:" + recv + "|" + "|".join(re.escape(a) for a in aliases) + r"\b)"
            clause = re.compile(r"(?:" + subject + r"\s*===?\s*(?:null|undefined)\b"
                                r"|\b(?:null|undefined)\s*===?\s*" + subject +
                                r"|!\s*" + subject + r"(?!\s*[.(\[]))")
            for m in re.finditer(r"\bif\s*\(", code):
                if not inside(m.start()):
                    continue
                close = _matching_end(code, m.end() - 1, "(", ")")
                if close is None:
                    continue
                cond = code[m.end():close]
                if "&&" in cond and "||" not in cond:
                    continue                              # `a && x === null` 不是「x 为空就失败」
                if not any(clause.search(part) for part in re.split(r"\|\|", cond)):
                    continue
                verdict = self._terminal(code, close + 1)
                if verdict == "hard":
                    hard.append((f, m.start()))
                elif verdict == "soft":
                    soft.append((f, m.start()))
            for m in re.finditer(recv + r"\s*!\s*[.(\[]", code):
                if inside(m.start()):
                    soft.append((f, m.start()))           # 非空断言：数据 bean 常这么写（Object.assign / JSON.parse 填充），只算软（复审 #3）
        return hard, soft

    @staticmethod
    def _terminal(code: str, pos: int) -> Optional[str]:
        """if 之后：块内第一条终止语句（throw / reject → hard；return → soft）。"""
        rest = code[pos:pos + 600]
        stripped = rest.lstrip()
        if stripped.startswith("{"):
            body_start = pos + (len(rest) - len(stripped))
            end = _matching_end(code, body_start)
            body = code[body_start + 1:end if end is not None else body_start + 600]
        else:
            body = stripped.split(";", 1)[0].split("\n", 1)[0]
        for m in re.finditer(r"\b(throw|return)\b", body):
            if m.group(1) == "throw":
                return "hard"
            return "hard" if re.match(r"return\s+Promise\s*\.\s*reject\b", body[m.start():]) else "soft"
        return None

    def _assignments(self, c: Cls, fname: str):
        """所有给 c.fname 赋非空值的位置 → [(file, offset)]。"""
        out = []
        pat = re.compile(r"(?<![\w$.])(?P<recv>[A-Za-z_$][\w$]*(?:\s*(?:\(\s*\))?\s*!?\s*\??\.\s*[A-Za-z_$][\w$]*)*)"
                         r"\s*\.\s*" + re.escape(fname) + r"\s*(?:\?\?|\|\||&&)?=(?![=>])\s*(?P<rhs>[^;\n]*)")
        family = self._family(c)
        needle = "." + fname
        destructure = re.compile(r"\[[^\[\]=;\n]*(?<![\w$])(?P<recv>[A-Za-z_$][\w$]*)\s*\.\s*" + re.escape(fname)
                                 + r"\b[^\[\]=;\n]*\]\s*=(?![=>])")
        for f, code in self.code.items():                  # [t.cover] = raw
            if fname not in code:
                continue
            for m in destructure.finditer(code):
                resolved = self.resolve(m.group("recv"), self._enclosing(f, m.start()), m.start())
                if resolved is None or resolved in family:
                    out.append((f, m.start()))
        bracket = re.compile(r"(?<![\w$.])(?P<recv>[A-Za-z_$][\w$]*(?:\s*\??\.\s*[A-Za-z_$][\w$]*)*)\s*\[\s*['\"]"
                             + re.escape(fname) + r"['\"]\s*\]\s*(?:\?\?|\|\||&&)?=(?![=>])\s*(?P<rhs>[^;\n]*)")
        for f, kept in self.kept.items():                  # X['client'] = c
            if fname not in kept:
                continue
            for m in bracket.finditer(kept):
                rhs = m.group("rhs").strip()
                if self.code[f][m.start()] == " " or not rhs or re.match(r"(?:null|undefined)\b", rhs):
                    continue
                resolved = self.resolve(m.group("recv"), self._enclosing(f, m.start()), m.start())
                if resolved is None or resolved in family:
                    out.append((f, m.start()))
        for f, code in self.code.items():
            if needle not in code and ". " + fname not in code:
                continue
            for m in pat.finditer(code):
                rhs = m.group("rhs").strip()
                if not rhs or re.match(r"(?:null|undefined)\b", rhs):
                    continue
                fn = self._enclosing(f, m.start())
                recv = m.group("recv")
                if recv == "this":
                    at = self._class_at(f, m.start())
                    if at is None or at.name not in family:
                        continue
                else:
                    resolved = self.resolve(recv, fn, m.start())
                    if resolved is not None and resolved not in family:
                        continue
                out.append((f, m.start()))
        return out

    def _bulk_filled(self, c: Cls) -> list:
        """整体填充的数据对象：`Object.assign(new T(), json)`、`JSON.parse(…) as T`、解构 `[t.f] = …`——
        字段不会以 `x.f = …` 的形式出现，不能据此判「没装上」（复审 #3 N10）。返回填充位置。"""
        out = []
        n = re.escape(c.name)
        rx = re.compile(r"\bObject\s*\.\s*assign\s*\(\s*new\s+" + n + r"\b"
                        r"|\bJSON\s*\.\s*parse\s*\([^;\n]*\)\s*as\s+" + n + r"\b"
                        r"|\bas\s+" + n + r"\b(?=[^;\n]*$)")
        for f, code in self.code.items():
            if c.name not in code:
                continue
            for m in rx.finditer(code):
                if not m.group(0).startswith("as") or "JSON" in code[code.rfind("\n", 0, m.start()):m.start()] \
                        or "Object" in code[code.rfind("\n", 0, m.start()):m.start()]:
                    out.append((f, m.start()))
            for m in re.finditer(r"\bObject\s*\.\s*assign\s*\(\s*([A-Za-z_]\w*)\s*,", code):
                fn = self._enclosing(f, m.start())
                if self._local_type(fn, m.group(1), m.start()) == c.name:
                    out.append((f, m.start()))
        return out

    def _descendants(self, name: str) -> set:
        out, stack = set(), [name]
        while stack:
            for child in self.children.get(stack.pop(), ()):
                if child not in out:
                    out.add(child)
                    stack.append(child)
        return out

    def _implemented(self, type_name: str) -> list:
        impls = []
        for name in {type_name} | self._descendants(type_name):
            for c in self.all_classes:
                if c.name == name and c.kind == "class" and not c.abstract:
                    impls.append(name)
        return sorted(set(impls))

    def _breakpoints(self, fn: Optional[Func], limit: int = 6) -> list:
        """沿调用方往上找：没有任何调用方的那个函数就是断点。"""
        if fn is None:
            return []
        if not hasattr(self, "_callers"):
            self._callers: dict[tuple, set] = {}
            for src, dsts in self.edges.items():
                for d in dsts:
                    self._callers.setdefault(d, set()).add(src)
        by_key = {x.key: x for x in self.funcs}
        out, seen, stack = [], set(), [(fn.key, 0)]
        while stack:
            key, depth = stack.pop()
            if key in seen:
                continue
            seen.add(key)
            ups = self._callers.get(key, set()) - {key}
            if not ups or depth >= limit:
                f = by_key[key]
                out.append(f"{f.owner + '.' if f.owner else ''}{f.name}")
                continue
            stack += [(u, depth + 1) for u in ups]
        return sorted(set(out))

    def dependencies(self) -> list[dict]:
        """每个依赖类型一条：{type, verdict, fields[], assignments[], breakpoints[], implementations[]}。"""
        grouped: dict[tuple, dict] = {}
        for c in self.all_classes:
            if c.kind == "object":
                continue
            for fd in c.fields.values():
                type_name = fd.type_name
                if type_name and type_name not in self.classes and type_name in self.imports.get(c.file, {}):
                    type_name = self.imports[c.file][type_name][0]          # import { X as Y }
                if not fd.nullable or not type_name or type_name not in self.classes:
                    continue
                if fd.decorated and c.kind == "struct":
                    continue                                  # 组件状态（@State / @Local / @Param …）不是注入依赖
                if not fd.static and not ({c.name} | self._descendants(c.name)) & self.explicitly_constructed():
                    continue                                  # 实例字段、可达代码从不 new 这个类：数据对象（JSON / 反序列化来的），判不了
                fd = Field(fd.name, type_name, fd.nullable, fd.static, fd.decorated, fd.file, fd.offset)
                hard, soft = self._guards(c, fd.name)
                hard_live = [g for g in hard if self.live_at(*g)]
                soft_live = [g for g in soft if self.live_at(*g)]
                if not hard_live and not soft_live:
                    continue                              # 没人用（或用的地方本身走不到）：死代码，不算运行时故障
                sites = self._assignments(c, fd.name)
                if any(self.live_at(f, off) for f, off in sites):
                    continue
                if any(self.live_at(f, off) for f, off in self._bulk_filled(c)):
                    continue                              # 数据对象整体填充（JSON / Object.assign / 解构）
                impls = self._implemented(fd.type_name)
                verdict = ("UNASSEMBLED" if hard_live else "UNASSEMBLED_SOFT") if impls else "NO_IMPLEMENTATION"
                g = grouped.setdefault((fd.type_name, verdict), {
                    "type": fd.type_name, "verdict": verdict,
                    "implementations": impls, "fields": [], "assignments": [], "breakpoints": set()})
                g["fields"].append({"file": c.file, "line": _line(self.raw[c.file], fd.offset),
                                    "class": c.name, "field": fd.name})
                for f, off in sites:
                    fn = self._enclosing(f, off)
                    g["assignments"].append({"file": f, "line": _line(self.raw[f], off),
                                             "function": (f"{fn.owner + '.' if fn and fn.owner else ''}{fn.name}"
                                                          if fn else "<模块顶层 / 类体>")})
                    g["breakpoints"].update(self._breakpoints(fn))
        out = []
        for g in grouped.values():
            g["fields"].sort(key=lambda x: (x["file"], x["line"]))
            uniq = sorted({(a["file"], a["line"], a["function"]) for a in g["assignments"]})
            g["assignments"] = [{"file": f, "line": ln, "function": fn} for f, ln, fn in uniq]
            g["breakpoints"] = sorted(g["breakpoints"])
            out.append(g)
        order = {"UNASSEMBLED": 0, "UNASSEMBLED_SOFT": 1, "NO_IMPLEMENTATION": 2}
        return sorted(out, key=lambda g: (order[g["verdict"]], g["type"]))
