# -*- coding: utf-8 -*-
"""ledger-unassembled-dependency（verify_closure_ledger Part 5 / ref_graph_lib/assembly.py）。

Anchors:
  · gpt1030_3（2026-10-19）：`EntryAbility.configureNetwork(client)` 零调用，13 个仓库的 client 永远 null，
    登录 / 模板全在本地抛「not configured」，装机后 mock 服务一条请求都没收到；
  · AIPPT_0910_walk / AIPPT_830_test_22：`ApplicationCompositionRoot.installApiClient(client)` 零调用，
    各门面 `X.shared().configure(client)`，另有页面里同名的 `this.viewModel.configure(policy)` 在用；
  · AIPPT_CodeX_0829：依赖从未装配、但用它的地方本身也走不到（死代码）——不算运行时故障。

Run: python3 tests/test_unassembled_dependency.py   (any cwd)
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))
import verify_closure_ledger  # noqa: E402
from ref_graph_lib.assembly import AssemblyAnalysis  # noqa: E402

CLIENT = """
export class NetworkClient {
  async post(path: string): Promise<string> { return path }
}
"""

REPO = """
import { NetworkClient } from '../network/NetworkClient'
export class UserRepository {
  private static client: NetworkClient | null = null
  static configureNetwork(client: NetworkClient): void { UserRepository.client = client }
  private client(): NetworkClient {
    if (UserRepository.client === null) throw new Error('User gateway is not configured')
    return UserRepository.client
  }
  async login(): Promise<string> { return await this.client().post('/user/login') }
}
"""

LOGIN_PAGE = """
import { UserRepository } from '../repositories/UserRepository'
@Entry
@ComponentV2
struct LoginPage {
  private repo: UserRepository = new UserRepository()
  build() {
    Button('登录').onClick(() => { this.repo.login() })
  }
}
"""


def ability(body: str, extra_methods: str = "") -> str:
    return f"""
import {{ UIAbility }} from '@kit.AbilityKit'
import {{ NetworkClient }} from '../network/NetworkClient'
import {{ UserRepository }} from '../repositories/UserRepository'
export default class EntryAbility extends UIAbility {{
  static configureNetwork(client: NetworkClient): void {{
    UserRepository.configureNetwork(client)
  }}
  onWindowStageCreate(windowStage: Object): void {{
{body}
  }}
{extra_methods}
}}
"""


def analyse(files: dict) -> list:
    return AssemblyAnalysis({k: v for k, v in files.items()}).dependencies()


def base_files(entry: str) -> dict:
    return {
        "entry/src/main/ets/network/NetworkClient.ets": CLIENT,
        "entry/src/main/ets/repositories/UserRepository.ets": REPO,
        "entry/src/main/ets/pages/LoginPage.ets": LOGIN_PAGE,
        "entry/src/main/ets/entryability/EntryAbility.ets": entry,
    }


class UnassembledDependency(unittest.TestCase):
    def test_injection_entry_never_called_is_reported(self):
        deps = analyse(base_files(ability("    console.info('start')")))
        self.assertEqual([(d["type"], d["verdict"]) for d in deps], [("NetworkClient", "UNASSEMBLED")])
        self.assertEqual(deps[0]["breakpoints"], ["EntryAbility.configureNetwork"])
        self.assertEqual(deps[0]["fields"][0]["field"], "client")

    def test_wired_at_startup_is_clean(self):
        deps = analyse(base_files(ability("    EntryAbility.configureNetwork(new NetworkClient())")))
        self.assertEqual(deps, [])

    def test_lifecycle_inherited_through_project_base_class(self):
        files = base_files(ability("    EntryAbility.configureNetwork(new NetworkClient())")
                           .replace("extends UIAbility", "extends BaseAbility"))
        files["entry/src/main/ets/entryability/BaseAbility.ets"] = (
            "import { UIAbility } from '@kit.AbilityKit'\nexport class BaseAbility extends UIAbility {}\n")
        self.assertEqual(analyse(files), [])

    def test_same_named_method_on_another_receiver_does_not_hide_the_gap(self):
        # 0910_walk：门面 `X.shared().configure(client)` 只在零调用的 installApiClient 里；
        # 页面里 `this.viewModel.configure(policy)` 是另一个类的同名方法，不能把门面的 configure 算活
        files = {
            "entry/src/main/ets/network/ApiClient.ets": "export class ApiClient { send(): void {} }\n",
            "entry/src/main/ets/services/AuthApi.ets": """
import { ApiClient } from '../network/ApiClient'
export class AuthApi {
  private static instanceValue: AuthApi = new AuthApi()
  private client: ApiClient | null = null
  static shared(): AuthApi { return AuthApi.instanceValue }
  configure(client: ApiClient): void { this.client = client }
  login(): void {
    if (this.client === null) {
      throw new Error('Auth network is unavailable until the verified ApiClient composition root is installed')
    }
    this.client.send()
  }
}
""",
            "entry/src/main/ets/services/ApplicationCompositionRoot.ets": """
import { ApiClient } from '../network/ApiClient'
import { AuthApi } from './AuthApi'
export class ApplicationCompositionRoot {
  static installProcess(): void {}
  static installApiClient(client: ApiClient): void { AuthApi.shared().configure(client) }
}
""",
            "entry/src/main/ets/viewmodels/WebViewModel.ets": """
export class WebViewModel {
  private policy: string = ''
  configure(policy: string): void { this.policy = policy }
}
""",
            "entry/src/main/ets/pages/WebPage.ets": """
import { WebViewModel } from '../viewmodels/WebViewModel'
import { AuthApi } from '../services/AuthApi'
@Entry
@Component
struct WebPage {
  private viewModel: WebViewModel = new WebViewModel()
  aboutToAppear(): void {
    this.viewModel.configure('x')
    AuthApi.shared().login()
  }
  build() { Text('x') }
}
""",
            "entry/src/main/ets/entryability/EntryAbility.ets": """
import { UIAbility } from '@kit.AbilityKit'
import { ApplicationCompositionRoot } from '../services/ApplicationCompositionRoot'
export default class EntryAbility extends UIAbility {
  onCreate(): void { ApplicationCompositionRoot.installProcess() }
}
""",
        }
        deps = analyse(files)
        self.assertEqual([(d["type"], d["verdict"]) for d in deps], [("ApiClient", "UNASSEMBLED")])
        self.assertEqual(deps[0]["breakpoints"], ["ApplicationCompositionRoot.installApiClient"])

    def test_interface_without_implementation_is_only_listed(self):
        files = base_files(ability("    EntryAbility.configureNetwork(new NetworkClient())"))
        files["entry/src/main/ets/repositories/PptRepository.ets"] = """
export interface PptSlideRenderer { render(): void }
export class PptRepository {
  private static renderer: PptSlideRenderer | null = null
  static configureSlideRenderer(renderer: PptSlideRenderer): void { PptRepository.renderer = renderer }
  preview(): void {
    if (PptRepository.renderer === null) throw new Error('renderer missing')
    PptRepository.renderer.render()
  }
}
"""
        files["entry/src/main/ets/pages/LoginPage.ets"] = LOGIN_PAGE.replace(
            "this.repo.login()", "this.repo.login(); new PptRepository().preview()").replace(
            "import { UserRepository }", "import { PptRepository } from '../repositories/PptRepository'\nimport { UserRepository }")
        deps = analyse(files)
        self.assertEqual([(d["type"], d["verdict"]) for d in deps], [("PptSlideRenderer", "NO_IMPLEMENTATION")])

    def test_interface_with_unwired_implementation_is_reported(self):
        files = base_files(ability("    EntryAbility.configureNetwork(new NetworkClient())"))
        files["entry/src/main/ets/repositories/OutlineRepository.ets"] = """
export interface OutlineTransport { send(): void }
export class NetworkOutlineTransport implements OutlineTransport { send(): void {} }
export class OutlineRepository {
  private static transport: OutlineTransport | null = null
  static configureTransport(t: OutlineTransport): void { OutlineRepository.transport = t }
  upload(): void {
    const transport = OutlineRepository.transport
    if (transport === null) throw new Error('transport missing')
    transport.send()
  }
}
"""
        files["entry/src/main/ets/pages/LoginPage.ets"] = LOGIN_PAGE.replace(
            "this.repo.login()", "this.repo.login(); new OutlineRepository().upload()")
        deps = analyse(files)
        self.assertEqual([(d["type"], d["verdict"], d["implementations"]) for d in deps],
                         [("OutlineTransport", "UNASSEMBLED", ["NetworkOutlineTransport"])])

    def test_unused_dependency_is_dead_code_not_a_gap(self):
        # AIPPT_CodeX_0829：PayUtils.init 只被零调用的 initPayTracking 调，requireDependencies 也只被死代码用
        files = base_files(ability("    EntryAbility.configureNetwork(new NetworkClient())"))
        files["entry/src/main/ets/common/PayUtils.ets"] = """
export class PayUtilsDependencies { storage: string = '' }
export class PayUtils {
  private static dependencies: PayUtilsDependencies | null = null
  static init(dependencies: PayUtilsDependencies): void { PayUtils.dependencies = dependencies }
  static addPayFrom(): void { PayUtils.requireDependencies() }
  private static requireDependencies(): PayUtilsDependencies {
    if (PayUtils.dependencies === null) { throw new Error('PayUtils.init must be called before addPayFrom') }
    return PayUtils.dependencies
  }
}
export class AppContant {
  static initPayTracking(d: PayUtilsDependencies): void { PayUtils.init(d) }
  static addPayFrom(): void { PayUtils.addPayFrom() }
}
"""
        self.assertEqual(analyse(files), [])

    def test_nullable_state_without_throw_guard_is_ignored(self):
        files = base_files(ability("    EntryAbility.configureNetwork(new NetworkClient())"))
        files["entry/src/main/ets/services/MembershipService.ets"] = """
export class VipFloatBean { title: string = '' }
export class MembershipService {
  private vipFloatCache: VipFloatBean | null = null
  title(): string { return this.vipFloatCache === null ? '' : this.vipFloatCache.title }
}
"""
        self.assertEqual(analyse(files), [])

    def test_callback_reference_and_constructor_assignment_count_as_wired(self):
        files = base_files(ability("    SplashViewModel.configureUserInitializer(this.initUser)\n"
                                   "    new Holder(new NetworkClient())",
                                   "  initUser(): void { EntryAbility.configureNetwork(new NetworkClient()) }"))
        files["entry/src/main/ets/viewmodels/SplashViewModel.ets"] = """
export class SplashViewModel {
  static configureUserInitializer(cb: () => void): void { cb() }
}
"""
        files["entry/src/main/ets/viewmodels/Holder.ets"] = """
import { NetworkClient } from '../network/NetworkClient'
export class Holder {
  private client: NetworkClient | null = null
  constructor(client: NetworkClient) { this.client = client }
  run(): void { if (this.client === null) throw new Error('x') }
}
"""
        self.assertEqual(analyse(files), [])

    def test_watch_callback_is_an_entry(self):
        files = base_files(ability("    console.info('start')"))
        files["entry/src/main/ets/pages/LoginPage.ets"] = LOGIN_PAGE.replace(
            "  build() {", """  @Local @Watch('onReady') ready: boolean = false
  onReady(): void { EntryAbility.configureNetwork(new NetworkClient()) }
  build() {""")
        self.assertEqual(analyse(files), [])

    def test_ledger_gate_reports_fail_and_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, text in base_files(ability("    console.info('start')")).items():
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
            out = root / "ledger.json"
            rc = verify_closure_ledger.main(["--project-root", str(root), "--output-json", str(out)])
            data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(rc, 1)
        self.assertEqual(data["errors"], [])
        self.assertEqual(data["summary"]["unassembled_dependencies"], 1)
        fails = [f for f in data["findings"] if f["severity_at_scope"] == "FAIL"]
        self.assertEqual([f["subtype"] for f in fails], ["ledger-unassembled-dependency"])
        self.assertIn("EntryAbility.configureNetwork", fails[0]["detail"])



def files_with(entry_body: str = "    console.info('start')", **over) -> dict:
    f = base_files(ability(entry_body))
    f.update({f"entry/src/main/ets/{k}": v for k, v in over.items()})
    return f


def verdicts(files: dict) -> list:
    return [(d["type"], d["verdict"]) for d in analyse(files)]


class ReviewFindings1019(unittest.TestCase):
    """1019 独立审核（H1–H5、M1–M3、FP-8/10/15）的回归用例。"""

    def test_typed_same_name_call_in_unrelated_file_does_not_hide_gap(self):
        # H1：`AppStorage.get<WebViewModel>()` 能推出类型，就不会把同名的注入函数救活
        other = "export class WebViewModel { configureNetwork(p: string): void {} }\n"
        page = """
import { WebViewModel } from '../viewmodels/WebViewModel'
@Entry
@Component
struct WebPage {
  aboutToAppear(): void {
    const vm = AppStorage.get<WebViewModel>('vm')
    vm.configureNetwork('x')
  }
  build() { Text('x') }
}
"""
        got = verdicts(files_with(**{"viewmodels/WebViewModel.ets": other, "pages/WebPage.ets": page}))
        self.assertIn(("NetworkClient", "UNASSEMBLED"), got)

    def test_untyped_receiver_falls_back_to_all_same_name_methods(self):
        # 复审 #4 N8：容器取出来的对象没有类型线索，按全工程同名算（宁可少报）——不能因为本文件
        # 碰巧 import 了另一个有同名方法的类就判「没装上」
        assembly = """
import { NetworkClient } from '../network/NetworkClient'
import { UserRepository } from '../repositories/UserRepository'
export class NetworkAssembly { install(c: NetworkClient): void { UserRepository.configureNetwork(c) } }
"""
        other = "export class WebViewModel { install(p: string): void {} }\n"
        entry = ability("    const net = AppContainer.resolve('network') as ESObject\n"
                        "    net.install(new NetworkClient())").replace(
            "import { UIAbility }", "import { WebViewModel } from '../viewmodels/WebViewModel'\nimport { UIAbility }")
        files = base_files(entry)
        files["entry/src/main/ets/app/NetworkAssembly.ets"] = assembly
        files["entry/src/main/ets/viewmodels/WebViewModel.ets"] = other
        self.assertEqual(verdicts(files), [])

    def test_local_variable_shadows_top_level_object_of_another_file(self):
        # 复审 #4 O1：别的文件有顶层 `export const assembly = {…}`，本地参数同名时按参数解析
        obj = "export const assembly = { install(x: string): void {} }\n"
        holder = """
import { NetworkClient } from '../network/NetworkClient'
import { UserRepository } from '../repositories/UserRepository'
export class Holder { install(c: NetworkClient): void { UserRepository.configureNetwork(c) } }
"""
        entry = ability("    run(new Holder(), new NetworkClient())",
                        "  run(assembly: Holder, c: NetworkClient): void { assembly.install(c) }").replace(
            "import { UIAbility }", "import { Holder } from '../app/Holder'\nimport { UIAbility }")
        files = base_files(entry)
        files["entry/src/main/ets/app/Obj.ets"] = obj
        files["entry/src/main/ets/app/Holder.ets"] = holder
        self.assertEqual(verdicts(files), [])

    def test_duplicate_class_names_do_not_create_false_gap(self):
        # 复审 #4 N9：两份 `class Repo`，真实那份经 `Repo.configure()` 接上了
        def repo(tag: str) -> str:
            return ("import { NetworkClient } from '../network/NetworkClient'\n"
                    "export class Repo {\n  private static client: NetworkClient | null = null\n"
                    "  static configure(c: NetworkClient): void { Repo.client = c }\n"
                    f"  static use{tag}(): void {{ if (Repo.client === null) throw new Error('x') }}\n}}\n")
        entry = ability("    EntryAbility.configureNetwork(new NetworkClient())\n    Repo.configure(new NetworkClient())"
                        ).replace("import { UIAbility }", "import { Repo } from '../b/Repo'\nimport { UIAbility }")
        files = base_files(entry)
        files["entry/src/main/ets/a/Repo.ets"] = repo("A")
        files["entry/src/main/ets/b/Repo.ets"] = repo("B")
        files["entry/src/main/ets/pages/LoginPage.ets"] = LOGIN_PAGE.replace(
            "this.repo.login()", "this.repo.login(); Repo.useA(); Repo.useB()").replace(
            "import { UserRepository }", "import { Repo } from '../b/Repo'\nimport { UserRepository }")
        self.assertEqual(verdicts(files), [])

    def test_non_null_assertion_on_data_bean_is_only_soft(self):
        # 复审 #3：`this.cover!.url`，cover 由 Object.assign / JSON.parse 填充——不能判成 hard
        bean = """
export class CoverBean { url: string = '' }
export class TemplateBean {
  cover: CoverBean | null = null
  url(): string { return this.cover!.url }
}
"""
        page = LOGIN_PAGE.replace("this.repo.login()", "this.repo.login(); (JSON.parse('{}') as TemplateBean).url()") \
            .replace("import { UserRepository }", "import { TemplateBean } from '../models/TemplateBean'\nimport { UserRepository }")
        files = base_files(ability("    EntryAbility.configureNetwork(new NetworkClient())"))
        files["entry/src/main/ets/models/TemplateBean.ets"] = bean
        files["entry/src/main/ets/pages/LoginPage.ets"] = page
        self.assertNotIn("UNASSEMBLED", [v for _t, v in verdicts(files)])

    def test_local_alias_of_field_is_resolved(self):
        # H1 复现：`const vm = this.viewModel; vm.configure()`
        other = "export class WebViewModel { configureNetwork(p: string): void {} }\n"
        page = """
import { WebViewModel } from '../viewmodels/WebViewModel'
import { UserRepository } from '../repositories/UserRepository'
@Entry
@Component
struct WebPage {
  private viewModel: WebViewModel = new WebViewModel()
  aboutToAppear(): void {
    const vm = this.viewModel
    vm.configureNetwork('x')
  }
  build() { Text('x') }
}
"""
        got = verdicts(files_with(**{"viewmodels/WebViewModel.ets": other, "pages/WebPage.ets": page}))
        self.assertIn(("NetworkClient", "UNASSEMBLED"), got)

    def test_installer_imported_but_never_called_is_reported(self):
        # H2：import 语句里的名字不算「当回调传出」
        inst = """
import { NetworkClient } from '../network/NetworkClient'
import { UserRepository } from '../repositories/UserRepository'
export function installNetwork(c: NetworkClient): void { UserRepository.configureNetwork(c) }
"""
        entry = ability("    console.info('x')").replace(
            "import { UIAbility }", "import { installNetwork } from '../app/Install'\nimport { UIAbility }")
        files = base_files(entry)
        files["entry/src/main/ets/app/Install.ets"] = inst
        self.assertIn(("NetworkClient", "UNASSEMBLED"), verdicts(files))

    def test_unimported_file_top_level_does_not_count(self):
        dead = """
import { NetworkClient } from '../network/NetworkClient'
import { UserRepository } from '../repositories/UserRepository'
UserRepository.configureNetwork(new NetworkClient())
"""
        self.assertIn(("NetworkClient", "UNASSEMBLED"), verdicts(files_with(**{"legacy/Dead.ets": dead})))

    def test_or_joined_guard_and_log_before_throw(self):
        repo = REPO.replace("if (UserRepository.client === null) throw new Error('User gateway is not configured')",
                            "if (this.ready === false || UserRepository.client === undefined) {\n"
                            "      console.error('no client')\n      throw new Error('x')\n    }")
        repo = repo.replace("private static client: NetworkClient | null = null",
                            "private static client: NetworkClient | undefined = undefined\n  private ready: boolean = true")
        files = base_files(ability("    console.info('x')"))
        files["entry/src/main/ets/repositories/UserRepository.ets"] = repo
        self.assertEqual(verdicts(files), [("NetworkClient", "UNASSEMBLED")])

    def test_return_guard_is_soft(self):
        repo = REPO.replace("if (UserRepository.client === null) throw new Error('User gateway is not configured')",
                            "if (UserRepository.client === null) { return UserRepository.client as NetworkClient }")
        files = base_files(ability("    console.info('x')"))
        files["entry/src/main/ets/repositories/UserRepository.ets"] = repo
        self.assertEqual(verdicts(files), [("NetworkClient", "UNASSEMBLED_SOFT")])

    def test_framework_subclass_public_method_is_an_entry(self):
        # M3：AppStartup 的 StartupTask.init 由框架调（不以 on 开头）
        task = """
import { StartupTask } from '@kit.AbilityKit'
import { NetworkClient } from '../network/NetworkClient'
import { UserRepository } from '../repositories/UserRepository'
export default class NetworkStartupTask extends StartupTask {
  async init(): Promise<void> { UserRepository.configureNetwork(new NetworkClient()) }
}
"""
        self.assertEqual(verdicts(files_with(**{"startup/NetworkStartupTask.ets": task})), [])

    def test_ternary_template_bracket_and_nullish_assignment_count(self):
        for body in ("    const ok = true ? EntryAbility.configureNetwork(new NetworkClient()) : undefined",
                     "    console.info(`${EntryAbility.configureNetwork(new NetworkClient())}`)"):
            with self.subTest(body=body):
                self.assertEqual(verdicts(base_files(ability(body))), [])
        repo_b = REPO.replace("UserRepository.client = client", "UserRepository['client'] = client")
        repo_n = REPO.replace("UserRepository.client = client", "UserRepository.client ??= client")
        for repo in (repo_b, repo_n):
            files = base_files(ability("    EntryAbility.configureNetwork(new NetworkClient())"))
            files["entry/src/main/ets/repositories/UserRepository.ets"] = repo
            with self.subTest(repo=repo[-80:]):
                self.assertEqual(verdicts(files), [])

    def test_regex_literal_with_brace_does_not_break_parsing(self):
        files = base_files(ability("    EntryAbility.configureNetwork(new NetworkClient())"))
        files["entry/src/main/ets/network/NetworkClient.ets"] = (
            "const PAT: RegExp = /\\{(\\w+)/\n" + CLIENT)
        self.assertEqual(verdicts(files), [])
        files = base_files(ability("    console.info('x')"))
        files["entry/src/main/ets/network/NetworkClient.ets"] = "const PAT: RegExp = /\\{(\\w+)/\n" + CLIENT
        self.assertEqual(verdicts(files), [("NetworkClient", "UNASSEMBLED")])

    def test_analysis_crash_is_a_fail_not_a_silent_pass(self):
        # H5：分析一崩不能退成 WARN（hard 结论会被吞掉）
        import ref_graph_lib.assembly as assembly_mod
        original = assembly_mod.AssemblyAnalysis.__init__
        assembly_mod.AssemblyAnalysis.__init__ = lambda self, texts: (_ for _ in ()).throw(RecursionError("simulated"))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for rel, text in base_files(ability("    console.info('x')")).items():
                    p = root / rel
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(text, encoding="utf-8")
                out = root / "ledger.json"
                rc = verify_closure_ledger.main(["--project-root", str(root), "--output-json", str(out)])
                data = json.loads(out.read_text(encoding="utf-8"))
        finally:
            assembly_mod.AssemblyAnalysis.__init__ = original
        self.assertEqual(rc, 1)
        self.assertEqual([f["subtype"] for f in data["findings"] if f["severity_at_scope"] == "FAIL"],
                         ["ledger-assembly-analysis-error"])
        self.assertTrue(data["errors"])


if __name__ == "__main__":
    unittest.main()
