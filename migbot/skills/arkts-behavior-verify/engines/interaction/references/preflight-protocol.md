<!-- when: initializing fast_fix preflight or diagnosing preflight CLI validation -->
<!-- topics: scan-dependencies, discover, assemble, validate, evidence outputs -->

# 预检产物协议

## 新运行：自动构建准备

生成工具链 lock 后，使用同一输出目录运行：

```text
python <skill-dir>/scripts/build_preparation.py --project-root <arkts_root> --toolchain-lock <out>/toolchain-lock.json --out-dir <out>
python <skill-dir>/scripts/fast_preflight.py validate --input <out>/preflight.json
```

准备器从现有 `build-profile.json5`、模块声明和已选签名读取构建命令及预期 signed HAP 路径，参数完整时写 `build-settings.json`。不新建签名、不读取或输出密钥文件内容，不将密码写入证据。无法唯一选择时保留原因；用户已有明确选择可用 `--product`、`--module`、`--module-target`、`--build-mode` 指定。未找到工具链 lock 文件时仅省略 `--toolchain-lock <out>/toolchain-lock.json`；已成功解析的配置仍保留在 `build-preparation.json` 的 `selected/known_build_settings` 中，不猜测构建命令。

缺依赖时仅恢复项目已有声明且 lock 中可解析的包，不新增包或调整版本。准备器使用现有工具链运行一次 `ohpm install --all --no-save`，禁用包管理器重试，默认超时 60 秒（`--dependency-timeout 1..120`）；超时终止安装进程树。用户禁止安装依赖/网络时传 `--no-install-deps`，按实际缺口降级。此开关不阻止 Hvigor tasks 写缓存；工程严格只读时跳过完整准备器和 discovery，使用下节允许的只读扫描与降级汇总，将未执行原因如实记录。Windows 优先使用 DevEco 自带 Node 的 OHPM 入口，避免环境中的 wrapper 递归。

安装前后对比源码、配置、声明和锁文件；意外变化会恢复原字节并保留阻塞原因，不能据安装退出码宣称 READY。仅恢复依赖缓存与入口，成功后重扫，再发现构建任务和汇总。安装失败、超时、未声明/未锁定的 import、真实缺签名均保留构建缺口，但不阻止源码审查。不得在其它运行正在写入的工程执行准备。

`dependency-recovery.json` 记录是否尝试、超时、退出码和耗时；不保存可能含认证 URL 的安装器原始输出。`build-preparation.json` 绑定恢复回执，`preflight.json` 再绑定准备证据及低层扫描/发现。已有 `preflight.json` 只校验返回；同一输出中的恢复回执（含中断/失败）不再启动第二次安装；同一运行不得通过删除回执或改输出目录重置次数，新准备仅用于用户已要求的新运行或明确追加第二轮的关联续跑。准备过程不增加 Detector Review 批次或编译修复次数，最终集中构建仍按原闭环执行。

## 低层接口与旧运行兼容

下面的 scan/discover/assemble/validate 保持可调用；新运行优先用准备器串起这些步骤，避免遗漏构建参数。旧封存预检不补写新字段、不改变结论。

`scan-dependencies` 与 `discover` 分别完整写入自己的输出，不合并已有 JSON。
为每类证据使用独立路径；已存在且属于另一类产物的输出会被拒绝覆盖。
`assemble` 读取证据、校验绑定、推导状态并原子写出最终预检；`validate`
只读校验最终预检，不生成或汇总文件。它们均不修改 `result.json`。

按以下顺序运行（工具链 lock 由 `resolve_hmos_toolchain.py` 的显式参数生成）：

```text
python <skill-dir>/scripts/fast_preflight.py scan-dependencies --project-root <arkts_root> --out <out>/dependency-scan.json
python <skill-dir>/scripts/fast_preflight.py discover --toolchain-lock <out>/toolchain-lock.json --product <product> --module <module> --build-mode <build_mode> --out <out>/task-discovery.json
python <skill-dir>/scripts/fast_preflight.py assemble --dependency-scan <out>/dependency-scan.json --toolchain-lock <out>/toolchain-lock.json --task-discovery <out>/task-discovery.json --build-settings <out>/build-settings.json --out <out>/preflight.json
python <skill-dir>/scripts/fast_preflight.py validate --input <out>/preflight.json
```

`build-settings.json` 只填写从当前项目配置和工具链确定的构建参数与非敏感签名定位信息：

```json
{
  "module": "<module>",
  "product": "<product>",
  "build_mode": "debug",
  "build_command": "<resolved hvigor command invoking assembleHap with selected product/module/buildMode>",
  "expected_signed_hap": "<absolute expected signed HAP path>",
  "signing_config": {
    "name": "<selected signing config>",
    "build_profile_path": "<absolute build-profile.json5 path>",
    "store_file": "<resolved absolute storeFile path>",
    "store_file_config_value": "<exact storeFile string inside the profile, retaining its escaping>"
  }
}
```

不复制密码、私钥或整个签名配置。签名文件不存在时仍可提供已知定位信息；
未能确定构建参数时省略 `--build-settings`，由脚本记录 `UNAVAILABLE`。
SDK/JBR/Hvigor 路径从 lock 提取；证据路径、SHA-256、attempts、发现的任务、
`signing_ready`、`build_readiness` 和状态由脚本生成，不填入 settings。

依赖缺失优先得到 `BLOCKED_PREEXISTING`；工具链/发现/构建参数缺失得到
`UNAVAILABLE`，均保留 `repair_ready=true`。无法运行 discovery 时省略其参数；
有效失败 lock/discovery 可以作为证据传入。坏 JSON、证据哈希不符、项目不一致
或输入输出重用属于输入错误，返回失败并保留已有最终文件，不能伪装成环境缺失。
源码/输出安全等硬前置仍由初始化和 source guard 负责，不能用 assemble 的通过替代。

汇总不会执行构建、连接设备或检查旧 HAP 来宣称本轮构建成功。
新汇总流程保留原 `setting-effect-preflight` 格式，既有合法预检仍能用 validate 校验。
