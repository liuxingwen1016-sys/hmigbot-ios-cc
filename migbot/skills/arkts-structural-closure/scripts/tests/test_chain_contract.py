# -*- coding: utf-8 -*-
"""chain-auth 契约断言（verify_closure_ledger Part 6 / ref_graph_lib/chain_contract.py）。

Anchors:
  · gpt1030_3（2026-10-19）：L3 设备标识被做成三方 SDK 占位（P-S2-033），全工程没有平台设备标识调用，
    缓存 OAID 永远为空 → /user/initUser 永不发；Base-3 自报「没有 golden」后跳过了字节对账；
  · AIPPT_0910_walk / AIPPT_830_test：`saveOaidAfterAgreement` 零调用，同样没有设备标识来源。

Run: python3 tests/test_chain_contract.py   (any cwd)
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))
import verify_closure_ledger  # noqa: E402

AUTH = {
    "identity_model": "device-bound",
    "identity_notes": "Splash 等待 OAID 后 initUser",
    "axis_b_device_role": ["identity-basis", "request-trust-component"],
    "token_acquisition": [{"endpoint": "POST /user/initUser"}, {"endpoint": "POST /user/bindMobileByToken"}],
}
INVENTORY = {"base_urls": [{"url": "http://127.0.0.1:8899"}], "auth_model": AUTH}

CLIENT = """
import { http } from '@kit.NetworkKit'
export class NetworkClient {
  static readonly BASE: string = 'http://127.0.0.1:8899'
  async post(path: string): Promise<string> {
    const request = http.createHttp()
    await request.request(NetworkClient.BASE + path)
    return ''
  }
}
"""

REPO = """
import { NetworkClient } from '../network/NetworkClient'
export class UserRepository {
  private client: NetworkClient = new NetworkClient()
  async initUser(oaid: string): Promise<string> { return await this.client.post('/user/initUser') }
}
"""

IDENTITY_LIVE = """
import { identifier } from '@kit.AdsKit'
export class DeviceIdentity {
  static async read(): Promise<string> { return await identifier.getOAID() }
}
"""


def entry(body: str) -> str:
    return f"""
import {{ UIAbility }} from '@kit.AbilityKit'
import {{ UserRepository }} from '../repositories/UserRepository'
import {{ DeviceIdentity }} from '../services/DeviceIdentity'
export default class EntryAbility extends UIAbility {{
  async onCreate(): Promise<void> {{
{body}
  }}
}}
"""


class ChainContract(unittest.TestCase):
    def run_ledger(self, files: dict, inventory=INVENTORY, chain=True, golden=False, oh_package=None,
                   extra=None, build_profile=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            if oh_package is not None:
                (root / "oh-package.json5").write_text(oh_package, encoding="utf-8")
            if build_profile is not None:
                (root / "build-profile.json5").write_text(build_profile, encoding="utf-8")
            for rel, text in (extra or {}).items():
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
            for rel, text in files.items():
                p = root / "entry/src/main/ets" / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
            chains = root / "spec/baseline/api-inventory/data-chains"
            chains.mkdir(parents=True)
            if inventory is not None:
                (root / "spec/baseline/api-inventory/api-inventory.json").write_text(
                    json.dumps(inventory, ensure_ascii=False), encoding="utf-8")
            if chain:
                (chains / "chain-auth.md").write_text("# auth\n### L3 设备身份\n- OAID 缓存及获取\n", encoding="utf-8")
            if golden:
                (chains / "chain-auth.golden.json").write_text("{}", encoding="utf-8")
            out = root / "ledger.json"
            rc = verify_closure_ledger.main(["--project-root", str(root), "--output-json", str(out)])
            data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data["errors"], [])               # 分析崩溃时「不应出现」类断言会假通过（审核 M7）
        chain_findings = [f for f in data["findings"] if f["subtype"].startswith("ledger-chain")]
        return rc, {(f["layer"], f["check"], f["severity_at_scope"], f["subtype"]) for f in chain_findings}, data

    def base(self, body: str, identity: str = IDENTITY_LIVE) -> dict:
        return {"network/NetworkClient.ets": CLIENT, "repositories/UserRepository.ets": REPO,
                "services/DeviceIdentity.ets": identity, "entryability/EntryAbility.ets": entry(body)}

    def test_complete_chain_only_leaves_notes(self):
        rc, got, _ = self.run_ledger(self.base("    const oaid = await DeviceIdentity.read()\n"
                                               "    await new UserRepository().initUser(oaid)"), golden=True)
        self.assertEqual(rc, 0)
        self.assertEqual(got, {("L5", "token-acquisition-partial", "WARN", "ledger-chain-assertion-note")})

    def test_missing_device_identity_source_is_hard_fail(self):
        rc, got, data = self.run_ledger(self.base("    await new UserRepository().initUser('')",
                                                  identity="export class DeviceIdentity {}\n"))
        self.assertEqual(rc, 1)
        self.assertIn(("L3", "device-identity-source", "FAIL", "ledger-chain-identity-source-missing"), got)
        self.assertEqual(data["summary"]["chain_assertions_unmet"], 1)

    def test_identity_api_only_in_dead_code_does_not_count(self):
        dead = IDENTITY_LIVE.replace("static async read", "static async neverCalled")
        rc, got, _ = self.run_ledger(self.base("    await new UserRepository().initUser('')", identity=dead))
        self.assertIn(("L3", "device-identity-source", "FAIL", "ledger-chain-identity-source-missing"), got)

    def test_identity_check_needs_device_bound_platform_id(self):
        inv = json.loads(json.dumps(INVENTORY))
        inv["auth_model"]["axis_b_device_role"] = ["request-trust-component"]
        rc, got, _ = self.run_ledger(self.base("    await new UserRepository().initUser('')",
                                               identity="export class DeviceIdentity {}\n"), inventory=inv)
        self.assertFalse(any(layer == "L3" for layer, *_ in got))

    def test_identity_check_needs_android_platform_identifier(self):
        # 绑设备但安卓用的是自生成 UUID（非平台标识）：鸿蒙也可以自生成，不要求平台接口
        inv = json.loads(json.dumps(INVENTORY))
        inv["auth_model"]["identity_notes"] = "首启生成 UUID 存本地作为设备号"
        files = self.base("    await new UserRepository().initUser('')", identity="export class DeviceIdentity {}\n")
        rc, got, _ = self.run_ledger(files, inventory=inv, chain=False)
        self.assertFalse(any(layer == "L3" for layer, *_ in got))

    def test_unreachable_transport_and_no_token_endpoint_fail(self):
        files = self.base("    console.info('start')")
        files["repositories/UserRepository.ets"] = REPO.replace("'/user/initUser'", "'/user/other'")
        rc, got, _ = self.run_ledger(files)
        self.assertIn(("L2", "transport-reachable", "FAIL", "ledger-chain-assertion-unmet"), got)
        self.assertIn(("L5", "token-acquisition", "FAIL", "ledger-chain-assertion-unmet"), got)

    def test_endpoint_in_comment_does_not_count(self):
        files = self.base("    const oaid = await DeviceIdentity.read()\n    await new UserRepository().initUser(oaid)")
        files["repositories/UserRepository.ets"] = REPO.replace(
            "this.client.post('/user/initUser')", "this.client.post('') // '/user/initUser'")
        rc, got, _ = self.run_ledger(files, golden=True)
        self.assertIn(("L5", "token-acquisition", "FAIL", "ledger-chain-assertion-unmet"), got)

    def test_base_url_absent_fails_l0(self):
        files = self.base("    const oaid = await DeviceIdentity.read()\n    await new UserRepository().initUser(oaid)")
        files["network/NetworkClient.ets"] = CLIENT.replace("127.0.0.1:8899", "example.com")
        rc, got, _ = self.run_ledger(files, golden=True)
        self.assertIn(("L0", "base-url", "FAIL", "ledger-chain-assertion-unmet"), got)

    def test_golden_missing_is_a_note(self):
        rc, got, _ = self.run_ledger(self.base("    const oaid = await DeviceIdentity.read()\n"
                                               "    await new UserRepository().initUser(oaid)"))
        self.assertIn(("L2", "golden", "WARN", "ledger-chain-assertion-note"), got)
        self.assertEqual(rc, 0)

    def test_no_auth_chain_is_not_applicable(self):
        rc, got, _ = self.run_ledger(self.base("    console.info('x')"), inventory={"base_urls": []}, chain=False)
        self.assertEqual(got, set())

    def test_chain_without_inventory_is_reported_not_skipped(self):
        rc, got, _ = self.run_ledger(self.base("    console.info('x')"), inventory=None)
        self.assertEqual(got, {("-", "facts", "WARN", "ledger-chain-assertion-note")})

    # ── 1019 独立审核回归 ───────────────────────────────────────────────
    def test_offline_app_is_not_applicable(self):
        inv = {"base_urls": [], "auth_model": {"identity_model": "none", "axis_b_device_role": []}}
        files = {"pages/Index.ets": "@Entry\n@Component\nstruct Index { build() { Text('dice') } }\n"}
        rc, got, _ = self.run_ledger(files, inventory=inv, chain=True)
        self.assertFalse(any(sev == "FAIL" for _l, _c, sev, _s in got))
        self.assertEqual(rc, 0)

    def test_stub_method_named_like_platform_api_does_not_satisfy_l3(self):
        stub = "export class DeviceIdentity {\n  async getOAIDPlaceholder(): Promise<string> { return '' }\n" \
               "  static async read(): Promise<string> { return await new DeviceIdentity().getOAIDPlaceholder() }\n}\n"
        rc, got, _ = self.run_ledger(self.base("    await new UserRepository().initUser(await DeviceIdentity.read())",
                                               identity=stub))
        self.assertIn(("L3", "device-identity-source", "FAIL", "ledger-chain-identity-source-missing"), got)

    def test_aliased_import_and_odid_bracket_satisfy_l3(self):
        for ident in (IDENTITY_LIVE.replace("import { identifier }", "import { identifier as adId }")
                      .replace("identifier.getOAID", "adId.getOAID"),
                      "import { deviceInfo } from '@kit.BasicServicesKit'\nexport class DeviceIdentity {\n"
                      "  static async read(): Promise<string> { return deviceInfo['ODID'] }\n}\n"):
            with self.subTest(ident=ident[:40]):
                rc, got, _ = self.run_ledger(self.base("    const oaid = await DeviceIdentity.read()\n"
                                                       "    await new UserRepository().initUser(oaid)", identity=ident),
                                             golden=True)
                self.assertFalse(any(layer == "L3" for layer, *_ in got))

    def test_negated_platform_identifier_is_not_counted(self):
        inv = json.loads(json.dumps(INVENTORY))
        inv["auth_model"]["identity_notes"] = "设备号为本地 UUID；不读取 IMEI / ANDROID_ID"
        rc, got, _ = self.run_ledger(self.base("    await new UserRepository().initUser('')",
                                               identity="export class DeviceIdentity {}\n"), inventory=inv, chain=False)
        self.assertFalse(any(layer == "L3" for layer, *_ in got))

    def test_structured_device_id_source_wins(self):
        inv = json.loads(json.dumps(INVENTORY))
        inv["auth_model"]["device_id_source"] = "self-uuid"
        rc, got, _ = self.run_ledger(self.base("    await new UserRepository().initUser('')",
                                               identity="export class DeviceIdentity {}\n"), inventory=inv)
        self.assertFalse(any(layer == "L3" for layer, *_ in got))

    def test_endpoint_with_colon_does_not_crash(self):
        inv = json.loads(json.dumps(INVENTORY))
        inv["auth_model"]["token_acquisition"].append({"endpoint": "POST /v1/token:refresh"})
        rc, got, data = self.run_ledger(self.base("    const oaid = await DeviceIdentity.read()\n"
                                                  "    await new UserRepository().initUser(oaid)"), inventory=inv)
        self.assertIn(("L5", "token-acquisition-partial", "WARN", "ledger-chain-assertion-note"), got)

    def test_endpoint_only_in_unused_constant_does_not_count(self):
        files = self.base("    const oaid = await DeviceIdentity.read()\n    await new UserRepository().initUser(oaid)")
        files["repositories/UserRepository.ets"] = REPO.replace("'/user/initUser'", "'/user/other'") + \
            "export class Api {\n  static readonly INIT_USER: string = '/user/initUser'\n}\n"
        rc, got, _ = self.run_ledger(files, golden=True)
        self.assertIn(("L5", "token-acquisition", "FAIL", "ledger-chain-assertion-unmet"), got)
        files["repositories/UserRepository.ets"] = REPO.replace("'/user/initUser'", "Api.INIT_USER") + \
            "export class Api {\n  static readonly INIT_USER: string = '/user/initUser'\n}\n"
        rc, got, _ = self.run_ledger(files, golden=True)
        self.assertFalse(any(layer == "L5" and sev == "FAIL" for layer, _c, sev, _s in got))

    def test_identity_in_never_constructed_class_does_not_count(self):
        # 复审 #1：只被 import / 类型标注 / 读静态常量的类，它实例字段里的 ODID 不会执行
        dead = ("import { deviceInfo } from '@kit.BasicServicesKit'\n"
                "export class DeadId {\n  static readonly TAG: string = 'id'\n  private id: string = deviceInfo.ODID\n}\n"
                "export class DeviceIdentity {\n  static async read(): Promise<string> { return DeadId.TAG }\n}\n")
        body = ("    let holder: DeadId | null = null\n    const oaid = await DeviceIdentity.read()\n"
                "    await new UserRepository().initUser(oaid)")
        files = self.base(body, identity=dead)
        files["entryability/EntryAbility.ets"] = files["entryability/EntryAbility.ets"].replace(
            "import { DeviceIdentity }", "import { DeadId, DeviceIdentity }")
        rc, got, _ = self.run_ledger(files, golden=True)
        self.assertIn(("L3", "device-identity-source", "FAIL", "ledger-chain-identity-source-missing"), got)
        files["services/DeviceIdentity.ets"] = dead.replace("return DeadId.TAG", "return new DeadId().toString()")
        rc, got, _ = self.run_ledger(files, golden=True)
        self.assertFalse(any(layer == "L3" and sev == "FAIL" for layer, _c, sev, _s in got))

    def test_unregistered_placeholder_package_does_not_count(self):
        # 复审 #1：随手 import 一个名字像设备标识的包不算取到；oh-package.json5 登记的远端包算（另报 WARN）
        stub = ("import { DeviceIdHelper } from '@app/device-stub'\nexport class DeviceIdentity {\n"
                "  static async read(): Promise<string> { return DeviceIdHelper.placeholder() }\n}\n")
        files = self.base("    const oaid = await DeviceIdentity.read()\n    await new UserRepository().initUser(oaid)",
                          identity=stub)
        rc, got, _ = self.run_ledger(files, golden=True)
        self.assertIn(("L3", "device-identity-source", "FAIL", "ledger-chain-identity-source-missing"), got)
        rc, got, _ = self.run_ledger(files, golden=True,
                                     oh_package='{ "dependencies": { "@app/device-stub": "^1.0.0" } }')
        self.assertFalse(any(layer == "L3" and sev == "FAIL" for layer, _c, sev, _s in got))
        self.assertIn(("L3", "device-identity-third-party", "WARN", "ledger-chain-assertion-note"), got)
        rc, got, _ = self.run_ledger(files, golden=True,
                                     oh_package='{ "dependencies": { "@app/device-stub": "file:../stub" } }')
        self.assertIn(("L3", "device-identity-source", "FAIL", "ledger-chain-identity-source-missing"), got)

    def test_unregistered_backup_copy_is_not_scanned(self):
        # 复审 #2：工程里放一份未登记的备份副本（里面接好了），不能把真问题解析到副本那边吞掉
        files = self.base("    const oaid = await DeviceIdentity.read()\n    await new UserRepository().initUser(oaid)",
                          identity="export class DeviceIdentity {\n  static async read(): Promise<string> { return '' }\n}\n")
        extra = {"backup/entry/src/main/ets/services/DeviceIdentity.ets": IDENTITY_LIVE}
        rc, got, _ = self.run_ledger(files, golden=True, extra=extra,
                                     build_profile='{ modules: [ { name: "entry", srcPath: "./entry" } ] }')
        self.assertIn(("L3", "device-identity-source", "FAIL", "ledger-chain-identity-source-missing"), got)

    def test_endpoint_in_multiline_static_table_counts_when_table_is_used(self):
        # 0910_walk 写法：多行 `private static readonly endpoints = [ new Endpoint('…', '/user/initUser') ]`，
        # 续行不在声明那一行，也要认出是静态字段初始化
        table = ("class Endpoint {\n  path: string\n  constructor(p: string) { this.path = p }\n}\n"
                 "export class Registry {\n  private static readonly endpoints: Endpoint[] = [\n"
                 "    new Endpoint('/user/other'),\n    new Endpoint('/user/initUser'),\n  ]\n"
                 "  static find(i: number): string { return Registry.endpoints[i].path }\n}\n")
        files = self.base("    const oaid = await DeviceIdentity.read()\n    await new UserRepository().initUser(oaid)")
        files["repositories/UserRepository.ets"] = REPO.replace("'/user/initUser'", "Registry.find(1)") + table
        rc, got, _ = self.run_ledger(files, golden=True)
        self.assertFalse(any(layer == "L5" and sev == "FAIL" for layer, _c, sev, _s in got))

    def test_transport_needs_platform_module_receiver(self):
        files = self.base("    const oaid = await DeviceIdentity.read()\n    await new UserRepository().initUser(oaid)")
        files["network/NetworkClient.ets"] = CLIENT.replace("import { http } from '@kit.NetworkKit'\n", "") \
            .replace("http.createHttp()", "Http.createHttp()").replace("export class NetworkClient",
                                                                       "class Http { static createHttp(): Object { return new Object() } }\nexport class NetworkClient")
        rc, got, _ = self.run_ledger(files, golden=True)
        self.assertIn(("L2", "transport-reachable", "FAIL", "ledger-chain-assertion-unmet"), got)


if __name__ == "__main__":
    unittest.main()
