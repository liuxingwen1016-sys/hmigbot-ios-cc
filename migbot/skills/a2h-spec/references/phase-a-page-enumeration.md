<!-- when: Step A1 提取页面清单时加载——四类枚举源的完整扫描规则与处置判据 -->
<!-- topics: manifest activity 枚举, Fragment 发现, DialogFragment 子类扫描, SDK 壳页, 死码处置, page_NNNN 命名约束 -->

# Step A1 页面枚举：四类源的完整规则

页面清单的完整性决定整条流水线的上界——**这里漏一页，后面所有覆盖率审计都不会再提它**
（漏页不在分母里，任何比率都不会因此下降）。四类枚举源缺一即漏，逐类规则如下。

---

## 第 1 类：全部模块 manifest 的 `<activity>`

`$ANDROID_SRC/*/src/main/AndroidManifest.xml` **glob 枚举，不是只读 `app/` 的那份**。
子模块 manifest 在构建期合并进最终 APK——只扫 `app/` 会把 `basic` / `pay` / `push` 等模块
声明的 Activity 整个漏掉，且不留任何记录。

> 实证：漏过 `basic` 模块的 `VideoPlayActivity`（全功能视频播放页），未进任何
> feature / page / skip-list。

对每份 manifest 提取所有 `<activity>` 声明，记录：

- Activity 全限定类名（`.` 开头的相对名用该 manifest 的 `package` 补全；`$Portrait` 类
  内部类归并到外部类；`${applicationId}` 占位视为构建期壳）
- **所属模块**（进 ui-manifest 页面清单表新增一列）
- `android:label`
- `intent-filter`（判断是否为 launcher Activity）
- `android:theme`

> ⚠️ manifest 里含 "Dialog" 字样的条目**不等于业务弹窗**：实证 32 条 `<activity>` 中 4 处
> 含该字样，全是主题名（`authsdk_activity_dialog`）与 SDK 内部页，业务弹窗一个都不在
> manifest 里——这正是第 3 类必须独立存在的原因。

## 第 2 类：Fragment

经 Step A2b 的加载关系发现：`FragmentTransaction.replace/add` / ViewPager +
FragmentPagerAdapter / Navigation Component 的 nav_graph。规则见
[phase-a-scan-strategies.md](./phase-a-scan-strategies.md)。

## 第 3 类：Dialog/Panel inventory（独立分母，不等于页面）

不在 manifest 且常通过 `show()` 呈现，必须运行确定性
`android-ui-graph-builder/scripts/dialog_inventory.py`，不得由 Agent 手列：

1. 扫全量 Java/Kotlin 继承边，再从 Dialog roots 求传递闭包；
2. 扫 builder subclass、具构造证据且暴露非 private `show\w*/open\w*/create\w*` 的 helper；
3. 扫匿名子类实例，每个 call site 独立记账；
4. Host 取 `show/showNow` 的外部调用方，factory 内构造不产生 self-host；
5. `show(beginTransaction(), tag)` 仍是 Dialog；只有 `add/replace(instance)` 是嵌入页面；仅嵌入的类
   标 `embedded_only=true`、`page_type=sub_component`，不生成 Dialog snapshot/closure 行；
6. layout owner 独立计算，结构快照落 `dialog-snapshots/`。

抽象类不能因 `abstract=true` 自动消失：存在匿名实例，或 reachable 且没有命名 concrete 后代时，
其 named definition 仍为 required；每个匿名实例另以稳定 instance key 一对一记账。

**命中项处置**：写 ui-manifest 固定 Dialog index；正文写单宿主页或一个共享 owner 宿主页；
具体子类差异进 Variants；只有 manifest Activity 仍作为 page。普通 Dialog 禁止新建 page spec。

> `prepare_dialog_artifacts.py` 按唯一 layout owner 调用 meta/view 合成脚本。Dialog snapshot 与
> page-list 解耦，Variant 复用祖先 snapshot，layout-less helper 明确写 `none`。
>
> 实证：某项目 20 个业务弹窗全是 `BaseDialogFragment` 子类，因缺本条**整层丢失**——
> 20/20 未进页面清单，且三道下游审计全部放行。

## 第 4 类：无源码 SDK 壳页 / 仓内 0 调用死码

定位每个候选的 Java/Kotlin 源码文件，三类处置：

- **仓内有源码** → 正常进页面清单
- **仓内无源码**（SDK 内部页，如阿里一键登录的 `com.mobile.auth.*`）→ 页面清单登记为
  `sdk-shell`，由承接该 SDK 的 feature 规约回调 / 页面形态，不产分页 spec
- **有源码但仓内 0 处调用**（疑似死码）→ **不静默丢弃**：出决策卡（迁移 / stub + 死码标记 /
  skip-list 登记 + 决策引用；决策 ID 用本项目 decision-ledger 实际条目，不同项目编号不同）

经 skip 关闭的条目会在每次 lint 运行和 Gate C 摘要的「跳过登记披露」中逐条点名——
**跳过是决策，沉默是事故**。

---

## 命名硬约束：一律 `page_NNNN_<ClassName>.md`

NNNN 全局唯一递增，跨四类源共用一个号池。**禁止** `frag_` / `dialog_` / `sheet_` 等
按类型区分的变体前缀。

理由不是美观，是**可见性**：下游三处审计都按 `page_*` glob 与 `page_(\d+)_(\w+)` 正则
枚举分页 spec。变体前缀的文件既不匹配 glob 也不匹配正则，于是——

- 不进覆盖率分母（分母变小，比率反而更好看）
- 不报缺失（它压根不在清单里）
- 没有任何一处会提示「有文件没被统计」

**结果是该页对所有审计静默隐形，且没有任何告警。**

> 实证：某次运行产出 23 个 `page_*` + 14 个 `frag_*`，审计分母 = 23，报告显示
> 「L4 主页 全量 23」并判 ✅ PASS——14 个 Fragment 分页 spec 对审计完全不存在。
