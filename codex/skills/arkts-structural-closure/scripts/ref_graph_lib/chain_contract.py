"""chain_contract.py — 数据链路契约断言（chain-auth）：spec 的结构化事实 → 代码里机械可核的完成判据。

为什么：a2h-plan Step 4.3 把 chain-auth 逐层扇出成 owner 任务的 MUST 文字，做没做靠 worker 在 brief 里自报。
gpt1030_3（2026-10-19）三处都是这个形状：Base-3 自报「没有 golden」就跳过字节对账；L3「平台替代」被做成
三方 SDK 占位，设备标识永远拿不到、/user/initUser 永不发；第 1 组自报「没有调用点」后登记延后项。

本模块按层**固定**推导断言（输入只有 `spec/baseline/api-inventory/api-inventory.json` 的 `base_urls` /
`auth_model` 与 chain-auth 契约的 L3 小节），不由实现方自写；判定只看代码与启动可达性（AssemblyAnalysis），
全程静态、不需要设备。运行态才能证明的（签名字节对不对、后端认不认）不在这里判，交 spec 探针与 a2h-verify。

适用条件：没有 base_url、没有取 token 端点、身份不绑设备（离线应用）时各层都不适用，不报；auth_model 为 null 但有
base_url 的工程照跑 L0 / L2。已知边界见 arkts-structural-closure SKILL.md「已知边界」。

  L0  base_urls 里至少一个主机（含 ${…} 占位的不算）出现在代码的字符串里            → 不满足 FAIL
  L2  从平台网络模块导入的命名空间上调用发请求接口（http.createHttp / rcp.createSession / axios），
      且调用处在可达代码里；兜底：名字像网络库的三方包成员被可达代码调用也算     → 不满足 FAIL
  L2  有 chain-auth 契约却没有 chain-auth.golden.json（签名没和后端核对过）            → WARN
  L3  身份绑设备（axis_b 含 identity-basis）且安卓用的是平台标识（优先读 auth_model.device_id_source；
      没有该字段时看 identity_notes 与 chain-auth 的 L3 小节，否定句不算）→ 可达代码里必须在从平台模块
      导入的命名空间上调用设备标识接口（AdsKit identifier.getOAID / PushKit AAID.getAAID /
      BasicServicesKit deviceInfo.ODID）                                          → 不满足 FAIL（hard）
      兜底：在 oh-package.json5 登记的远端三方包（非 file: 本地包）上、名字像设备标识的成员被可达代码调用，
      算满足但另报 WARN（包内实现看不到）；未登记的包（随手写的占位）不算。
  L5  取 token 端点的路径，至少一个出现在可达函数体里，或出现在被可达函数引用的常量 / 端点表里
      → 一个都没有 FAIL；单个端点缺失 WARN（常见是缺三方 SDK 的登录方式）；路径解析不出 WARN
"""
from __future__ import annotations

import json
import re
from pathlib import Path

INVENTORY_REL = "spec/baseline/api-inventory/api-inventory.json"
CHAIN_REL = "spec/baseline/api-inventory/data-chains/chain-auth.md"
GOLDEN_REL = "spec/baseline/api-inventory/data-chains/chain-auth.golden.json"

# 平台模块 → 该模块里发请求 / 取设备标识的成员（接收者必须是从这些模块导入的名字，工程自写的同名方法不算）
NETWORK_MODULES = {"@kit.NetworkKit": ("createHttp",), "@ohos.net.http": ("createHttp",),
                   "@kit.RemoteCommunicationKit": ("createSession",), "@hms.collaboration.rcp": ("createSession",)}
AXIOS_MODULES = ("@ohos/axios",)
IDENTITY_MODULES = {"@kit.AdsKit": ("getOAID",), "@ohos.identifier.oaid": ("getOAID",),
                    "@kit.PushKit": ("getAAID",), "@hms.core.push.pushService": ("getAAID",),
                    "@kit.BasicServicesKit": ("ODID",), "@ohos.deviceInfo": ("ODID",)}
ANDROID_PLATFORM_ID_RE = re.compile(r"OAID|IMEI|ANDROID_ID|AndroidId|androidId|MediaDrm|Widevine|AAID|getDeviceId")
PLATFORM_ID_SOURCES = {"platform-oaid", "platform-aaid", "android-id", "imei", "media-drm", "platform"}
NON_PLATFORM_SOURCES = {"self-uuid", "server", "none", "account"}
NEGATION_RE = re.compile(r"(?:不|无|未|没有|禁止|不再|not\s+|no\s+|never\s+)[^。；;，,\n]{0,14}$", re.I)
PLATFORM_PREFIXES = ("@kit.", "@ohos.", "@hms.", "@system.")
IDENTITY_WORDS = re.compile(r"oaid|aaid|odid|udid|deviceid|device_id", re.I)
NETWORK_WORDS = re.compile(r"http|axios|request|net(?:work)?\b|retrofit|okhttp", re.I)


def _load(project_root: Path):
    inv_path = project_root / INVENTORY_REL
    chain = project_root / CHAIN_REL
    chain_text = chain.read_text(encoding="utf-8", errors="replace") if chain.is_file() else ""
    if not inv_path.is_file():
        return None, chain_text, ("有 chain-auth 契约但缺 api-inventory.json" if chain_text else None)
    try:
        inv = json.loads(inv_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, chain_text, f"api-inventory.json 读不了：{exc}"
    if not isinstance(inv, dict):
        return None, chain_text, "api-inventory.json 不是对象"
    return inv, chain_text, None


def _l3_section(chain_text: str) -> str:
    """chain-auth 契约里只跟 L3 有关的文字：L3 小节 + 表格里以 L3 开头的行。"""
    parts = re.findall(r"^#{2,4}\s*L3\b.*?(?=^#{2,4}\s|\Z)", chain_text, re.M | re.S)
    parts += re.findall(r"^\|\s*L3\s*\|.*$", chain_text, re.M)
    return "\n".join(parts)


def _platform_identifier(auth: dict, chain_text: str):
    """安卓侧身份用的是不是平台标识：(是否, 依据)。结构化字段优先，否则读 identity_notes + L3 小节。"""
    source = str(auth.get("device_id_source") or "").strip().lower()
    if source:
        return (source in PLATFORM_ID_SOURCES or source.startswith("platform-")), f"device_id_source={source}"
    text = " ".join([str(auth.get("identity_notes") or ""), _l3_section(chain_text)])
    for m in ANDROID_PLATFORM_ID_RE.finditer(text):
        if not NEGATION_RE.search(text[max(0, m.start() - 20):m.start()]):
            return True, m.group(0)
    return False, ""


def _module_names(analysis, f: str, modules) -> dict:
    """本文件从这些平台模块导入的本地名 → 原名。"""
    out = {}
    for local, (orig, spec) in analysis.imports.get(f, {}).items():
        if spec in modules:
            out[local] = orig
    for alias, spec in analysis.ns_imports.get(f, {}).items():
        if spec in modules:
            out[alias] = alias
    return out


def _platform_calls(analysis, modules: dict, attribute: bool = False) -> list:
    """在「从平台模块导入的名字」上的调用 / 属性访问 → [(file, line, live)]。"""
    out = []
    for f, code in analysis.code.items():
        names = _module_names(analysis, f, modules)
        if not names:
            continue
        members = sorted({m for spec, ms in modules.items() for m in ms})
        rx = re.compile(r"(?<![\w$.])(?P<ns>" + "|".join(re.escape(n) for n in sorted(names)) + r")\s*\.\s*(?P<m>"
                        + "|".join(re.escape(m) for m in members) + r")\b" + ("" if attribute else r"\w*\s*\("))
        for m in rx.finditer(code):
            if analysis._in_skip(f, m.start()):
                continue
            out.append((f, analysis.raw[f].count("\n", 0, m.start()) + 1, analysis.live_at(f, m.start())))
        if attribute:                                      # deviceInfo['ODID'] / const { ODID } = deviceInfo
            kept = analysis.kept[f]
            ns_alt = "|".join(re.escape(n) for n in sorted(names))
            mem_alt = "|".join(re.escape(m) for m in members)
            for m in re.finditer(r"(?<![\w$.])(?:" + ns_alt + r")\s*\[\s*['\"](?:" + mem_alt + r")['\"]\s*\]"
                                 r"|\{[^{}]*\b(?:" + mem_alt + r")\b[^{}]*\}\s*=\s*(?:" + ns_alt + r")\b", kept):
                if code[m.start()] != " ":
                    out.append((f, analysis.raw[f].count("\n", 0, m.start()) + 1, analysis.live_at(f, m.start())))
    return out


def declared_remote_packages(project_root: Path) -> set:
    """各 oh-package.json5 里登记、且不是本地 `file:` 路径的依赖包名（真正从仓库装的三方包）。"""
    out = set()
    for pkg in [project_root / "oh-package.json5", *project_root.glob("*/oh-package.json5")]:
        try:
            text = pkg.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for block in re.findall(r"\b(?:dependencies|devDependencies|dynamicDependencies)\s*\"?\s*:\s*\{([^}]*)\}", text):
            for name, version in re.findall(r"""["']([^"']+)["']\s*:\s*["']([^"']*)["']""", block):
                if not version.startswith("file:"):
                    out.add(name)
    return out


def _opaque_package_calls(analysis, words: re.Pattern, packages=None) -> list:
    """从工程外三方包（非平台模块、源码不在扫描范围）导入、名字像网络 / 设备标识的成员上的调用：
    看不到包内实现。packages 给了就只认在 oh-package.json5 里登记的远端包（复审 #1：随手写个
    `import { DeviceIdHelper } from '@app/device-stub'` 不能算取到了设备标识）。"""
    out = []
    for f, code in analysis.code.items():
        names = [local for local, (orig, spec) in analysis.imports.get(f, {}).items()
                 if not spec.startswith(PLATFORM_PREFIXES) and not spec.startswith(".")
                 and (packages is None or spec in packages)
                 and (words.search(spec) or words.search(orig))]
        if not names:
            continue
        rx = re.compile(r"(?<![\w$.])(?:" + "|".join(re.escape(n) for n in names) + r")\b\s*(?:\.\s*\w+\s*)*(?:\(|\.)")
        for m in rx.finditer(code):
            if not analysis._in_skip(f, m.start()):
                out.append((f, analysis.raw[f].count("\n", 0, m.start()) + 1, analysis.live_at(f, m.start())))
    return out


def _axios_calls(analysis) -> list:
    out = []
    for f, code in analysis.code.items():
        names = _module_names(analysis, f, AXIOS_MODULES)
        if not names:
            continue
        rx = re.compile(r"(?<![\w$.])(?:" + "|".join(re.escape(n) for n in sorted(names)) + r")\s*"
                        r"(?:\.\s*(?:create|request|get|post|put|delete)\s*)?\(")
        for m in rx.finditer(code):
            if not analysis._in_skip(f, m.start()):
                out.append((f, analysis.raw[f].count("\n", 0, m.start()) + 1, analysis.live_at(f, m.start())))
    return out


def _string_hits(analysis, rx: re.Pattern) -> list:
    """只认字符串字面量里的命中 → [(file, offset)]。"""
    out = []
    for f, kept in analysis.kept.items():
        code = analysis.code[f]
        for m in rx.finditer(kept):
            if m.start() < len(code) and m.end() > m.start() and code[m.start()] == " ":
                out.append((f, m.start()))
    return out


def _decl_name_at(analysis, f: str, pos: int):
    """字面量所在的顶层声明名：类体里 → 类名；模块顶层 → 最近的 const / let 名。"""
    cls = analysis._class_at(f, pos)
    if cls is not None:
        return cls.name
    code = analysis.code[f]
    last = None
    for m in re.finditer(r"(?:^|\n)\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_]\w*)", code[:pos]):
        last = m.group(1)
    return last


def _sent(analysis, f: str, pos: int) -> bool:
    """端点字面量算「会发出」：在可达函数体里；或所在常量 / 端点表被可达函数引用。"""
    fn = analysis.enclosing_unit(f, pos)
    if fn is not None:
        return fn.key in analysis.alive
    if not analysis.live_at(f, pos):
        return False
    name = _decl_name_at(analysis, f, pos)
    if not name or f not in analysis.loaded:
        return False
    rx = re.compile(r"(?<![\w$])" + re.escape(name) + r"\b")
    for other in analysis.funcs:
        if other.key in analysis.alive and rx.search(analysis.code[other.file], other.body_start, other.end):
            return True
    return False


def _loc(analysis, hits: list, limit: int = 4) -> list:
    out = []
    for h in hits[:limit]:
        f, pos = h[0], h[1]
        line = pos if len(h) == 3 else analysis.raw[f].count("\n", 0, pos) + 1
        out.append({"file": f, "line": line})
    return out


def _path_of(endpoint: str):
    text = str(endpoint).strip().split()[-1] if str(endpoint).strip() else ""
    text = re.sub(r"^[a-z]+://[^/]+", "", text)          # 完整 URL → 路径
    text = text.split("?", 1)[0]
    return text if text.startswith("/") else None


def evaluate(project_root: Path, analysis) -> list[dict]:
    """每条断言一项：{layer, check, ok, severity, detail, evidence[{file,line}], notes[], suggested_action}。"""
    inv, chain_text, problem = _load(project_root)
    results: list[dict] = []

    def add(layer, check, ok, severity, detail, evidence=(), notes=(), action=""):
        results.append({"layer": layer, "check": check, "ok": ok, "severity": severity, "detail": detail,
                        "evidence": list(evidence), "notes": list(notes), "suggested_action": action})

    if inv is None:
        if problem:
            add("-", "facts", False, "WARN", f"契约断言无法推导：{problem}",
                action="补齐 android-api-inventory 的结构化产物后重跑。")
        return results
    auth = inv.get("auth_model")
    if not isinstance(auth, dict):
        if chain_text or auth:
            add("-", "facts", False, "WARN", "契约断言无法推导：api-inventory.json 的 auth_model 缺失或不是对象",
                action="按 android-api-inventory output_schema 补 auth_model 后重跑。")
        auth = {}
    base_urls = [str(b.get("url", "")) for b in inv.get("base_urls") or [] if isinstance(b, dict)]
    hosts = sorted({h for h in (re.sub(r"^[a-z]+://", "", u).split("/")[0].strip() for u in base_urls)
                    if h and "$" not in h and "{" not in h and " " not in h})
    raw_endpoints = [str(i.get("endpoint")) for i in auth.get("token_acquisition") or []
                     if isinstance(i, dict) and i.get("endpoint")]
    endpoints = [p for p in (_path_of(e) for e in raw_endpoints) if p]
    unparsed = [e for e in raw_endpoints if not _path_of(e)]
    identity = str(auth.get("identity_model") or "").lower()
    if not hosts and not raw_endpoints and identity in ("", "none", "offline"):
        return results                                     # 离线应用 / 没有登录链：不适用

    # L0 网关地址
    if hosts:
        found = []
        for h in hosts:
            variants = {h, h.split(":")[0]} if ":" in h else {h}
            if any(_string_hits(analysis, re.compile(re.escape(v))) for v in variants):
                found.append(h)
        add("L0", "base-url", bool(found), "FAIL",
            f"安卓网关地址 {', '.join(hosts)} " + (f"中 {', '.join(found)} 已出现在代码里" if found else "一个都没出现在代码里"),
            notes=found, action="按安卓源码的 base_url（或决策账本改定的地址）配置网络层常量。")

    # L2 请求真的能发出去
    if hosts or endpoints:
        transport = _platform_calls(analysis, NETWORK_MODULES) + _axios_calls(analysis) + \
            _opaque_package_calls(analysis, NETWORK_WORDS)
        live = [h for h in transport if h[2]]
        add("L2", "transport-reachable", bool(live), "FAIL",
            (f"发请求的平台接口在可达代码里有 {len(live)} 处调用" if live else
             "发请求的平台接口（从 @kit.NetworkKit / @kit.RemoteCommunicationKit / @ohos/axios 导入的 "
             "http.createHttp / rcp.createSession / axios）" +
             ("只出现在走不到的代码里" if transport else "全工程没有调用") + "：应用发不出任何请求"),
            evidence=_loc(analysis, live or transport),
            action="让网络客户端在启动链上被创建并被各仓库使用（配合 ledger-unassembled-dependency 的断点）；"
                   "网络层若在 HAR 模块里，确认该模块源码在扫描范围内。")
    if chain_text and not (project_root / GOLDEN_REL).is_file():
        add("L2", "golden", False, "WARN",
            "有 chain-auth 契约但没有 chain-auth.golden.json：请求签名没有和后端核对过，计划里「按 golden 字节对账」这条 MUST 没有输入",
            notes=[CHAIN_REL], action="spec 探针补跑（免凭证靶点）产出 golden；跑不了的原因记进迁移报告。")

    # L3 设备身份来源
    roles = auth.get("axis_b_device_role") or []
    roles = roles if isinstance(roles, list) else [roles]
    uses_platform, basis = _platform_identifier(auth, chain_text)
    if "identity-basis" in roles and uses_platform:
        ids = _platform_calls(analysis, {k: v for k, v in IDENTITY_MODULES.items() if v != ("ODID",)}) + \
            _platform_calls(analysis, {k: v for k, v in IDENTITY_MODULES.items() if v == ("ODID",)}, attribute=True)
        live_ids = [h for h in ids if h[2]]
        if not live_ids:                                   # 三方 SDK 取标识：只认 oh-package.json5 登记的远端包，且另报 WARN
            sdk = [h for h in _opaque_package_calls(analysis, IDENTITY_WORDS, declared_remote_packages(project_root))
                   if h[2]]
            if sdk:
                live_ids = sdk
                add("L3", "device-identity-third-party", False, "WARN",
                    "设备标识由 oh-package.json5 登记的三方包提供，包内实现静态看不到，是否真的取到交 a2h-verify 核实",
                    evidence=_loc(analysis, sdk), action="真机核对设备标识非空、初始化请求带上了它。")
        add("L3", "device-identity-source", bool(live_ids), "FAIL",
            f"安卓身份绑设备、用平台标识（{basis}）；鸿蒙可达代码里" +
            (f"有 {len(live_ids)} 处平台设备标识调用" if live_ids else
             ("的平台设备标识调用只在走不到的代码里" if ids else
              "没有在平台模块（@kit.AdsKit / @kit.PushKit / @kit.BasicServicesKit）上调用设备标识接口") +
             "：设备标识永远为空，依赖它的游客初始化 / 取 token 不会发生"),
            evidence=_loc(analysis, live_ids or ids),
            action="按「平台替代」实现：同意隐私后用鸿蒙系统接口取设备标识（广告标识 OAID 需跟踪授权；ODID 无需权限），"
                   "写入缓存再触发初始化。不要登记成三方 SDK 占位。")

    # L5 取 token 的端点
    if unparsed:
        add("L5", "token-acquisition-unparsed", False, "WARN",
            f"这些取 token 端点解析不出路径，没法核对：{', '.join(unparsed)}", notes=unparsed,
            action="auth_model.token_acquisition[].endpoint 按 `METHOD /path` 写。")
    if endpoints:
        state = {}
        for path in endpoints:
            segment = "/" + path.rstrip("/").rsplit("/", 1)[-1]
            hits = _string_hits(analysis, re.compile(re.escape(path) + r"(?![\w-])"))
            if not hits and segment != path:          # 路径拼接（USER + '/initUser'）：退到末段
                hits = _string_hits(analysis, re.compile(r"(?<=['\"`}])" + re.escape(segment) + r"(?![\w-])"))
            state[path] = [h for h in hits if _sent(analysis, *h)]
        sent = [p for p, h in state.items() if h]
        missing = [p for p, h in state.items() if not h]
        add("L5", "token-acquisition", bool(sent), "FAIL",
            (f"取 token 的端点在可达代码里发出 {len(sent)}/{len(endpoints)} 个" if sent else
             f"取 token 的端点（{', '.join(endpoints)}）一个都没在可达代码里发出：登录链没有实现"),
            evidence=[e for p in sent for e in _loc(analysis, state[p], 1)],
            action="按 chain-auth L5 实现游客初始化 / 登录接口并接到启动或登录页。")
        if sent and missing:
            add("L5", "token-acquisition-partial", False, "WARN",
                f"这些取 token 的端点没在可达代码里发出：{', '.join(missing)}（常见是缺三方 SDK 的登录方式）",
                notes=missing, action="确认是平台缺能力（如实列入迁移报告）还是漏实现（补上）。")
    return results
