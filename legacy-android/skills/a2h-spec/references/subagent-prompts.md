<!-- when: a2h-spec 派发 subagent 时加载（§3.0 选项 A / Step 3.0c3 / Step B-probe / Step B2 分页扇出 / Step C4 feature 扇出）-->
<!-- topics: a2h-android-analyzer, android-api-inventory, auth-chain-probe, b2-page-worker, c4-feature-worker, batch-plan 扇出, 写权围栏, 回执 -->

# a2h-spec 派发的 subagent prompt

a2h-spec 主线程在五处派发 subagent：三条**后台并行轨**（analyzer / api-inventory / auth-probe）
与两处**按 batch-plan 的批次扇出**（Step B2 分页 spec / Step C4 feature spec）。完整派发 prompt 在此。

> **扇出不是可选项**：实测 V2 一个 worker 都没派、主线扛全量 58 页 + 18 feature 时，input token
> 达 V1 的 1.68×，模型随即自述「context constraints」并写脚本套模板批量产出分页 spec——
> 唯一 AC 从 545 塌到 134、addenda 从 35 塌到 0，而全部既有门禁**照常判 PASS**。

## 派发纪律（五处共用）

- **派满不轮询**：批次一次全部派出；异步宿主派完即结束回轮等通知，**不 sleep、不忙轮询、不追问进度**；
  同步宿主一条消息组织一波、整波返回再派下一波。
- **空回执 = 中断**：agent 返回但无 summary / 无约定回执（b2 / c4 = `spec/.a2h/worker-receipts/{batch_id}.json`
  缺失；三条后台轨 = 约定产物目录为空）→ 视为未执行，重派同一 prompt；连续 2 次空回执 → 降一档并发再派。
- **卡死回收**（同 a2h-execute §3a 规则 ⑦）：观察点 = 每次回轮或宿主等待工具的有界超时（**120 秒**）。
  只有新工具结果、该单位写权文件有变更（page_*.md / F*.md / api-inventory 目录 / probe 产物）、回执落盘才算进展，
  「正在处理」/ running 标签 / 时间戳变化不算。某单位连续 **300 秒**无可观察进展 → 查其已落盘产物并**催询一次**
  （要它回：已落盘文件 / 未完成项 / 正在跑的工具）；再 **240 秒**仍无实质进展 → 请求取消，确认其写进程已停后
  重派（已落盘的页 / feature 可接续则 prompt 附产物清单只续剩余，不重做）。明确 token / context 耗尽、限流、断连 →
  立即查产物，不等阈值。同一单位连续两次重派仍同因停滞 → 停自动重试，带产物报告，不拖住其他批次。

## a2h-android-analyzer（§3.0 选项 A：自动生成参考文档）

用户在 3.0 前置选「自动生成参考文档」时派发：

```
Agent(
  subagent_type: "hmigbot:a2h-android-analyzer",
  prompt: "分析 Android 项目并生成参考文档。
    android_source_dir: $ANDROID_SRC
    output_dir: spec/ref/
    project_name: {从 AndroidManifest 提取的 package 短名}"
)
```

等待完成后，记录 `$REF_SPEC` 和 `$REF_DESIGN` 路径，继续 Phase A。

## android-api-inventory（Step 3.0c3 预派发；Step B0 兜底）

**3.0c2 一结束（Step 3.0c3）即派发**后台子 agent——它只需 `$ANDROID_SRC`（+ 此刻已定的两个可选
文件参数），不依赖 Phase 0/A/B 任何产物，是全管线最长单体子任务，提前起跑可把墙钟完全藏进
Phase 0/A + B-UI。若 3.0c3 被跳过，Step B0 兜底补派发（prompt 相同）：

```
Agent(
  subagent_type: "hmigbot:a2h-migration-worker",
  run_in_background: true,
  model: "sonnet",            # 机械 API 枚举（endpoints / services / base_urls 结构化抽取，低创造性），无需强模型；抽取完整性由下游 feature-coverage L3 覆盖脚本反查兜底。不用 haiku：API 漏抽对漏迁影响大，sonnet 完整性/成本最佳。语义判定（a2h-android-analyzer / grill D-decision / ring contract）仍保留强模型。
  prompt: "执行 android-api-inventory skill，对 Android 源码做外部 API 清单提取。
    platform: android           # 显式固定为 android（a2h-spec 永远以此模式调用本 skill，详见 android-api-inventory 契约段）
    android_source_dir: $ANDROID_SRC
    输出目录: spec/baseline/api-inventory/
    hmos_references_file: $HMOS_REFS_FILE  # 仅当 Step 3.0c 产出 spec/ref/hmos-references.md 时传入；为 null 则忽略（此时 Phase 2.5 整段跳过）
    backend_facts_file: $BACKEND_FACTS_FILE  # v1.3：仅当 Step 3.0c2 产出 spec/ref/backend-facts.md 时传入；为 null 则忽略（uncertainties 全部以 open 状态产出，不预销账）
    当前 spec/baseline/features/ 与 feature-index.md 均未生成 → Phase 4 走【分支 C — 输入源模式】。
    完成后返回 summary（5 个字段）：
      - services_count: number
      - endpoints_count: number
      - feature_candidates_count: number
      - coverage_mode: 'audit' | 'incremental' | 'candidate' | 'degraded'
      - hmos_hint_section_present: boolean  # Phase 2.5 等价物提示段是否落到 api-inventory.md（hmos_references_file 为空或文件不存在时为 false）"
)
```

记录子 agent 句柄为 `$API_INVENTORY_JOB`，主线继续 B-UI 轨（Step B1）。

> **降级**：若环境不支持后台子 agent，退化为「B-UI 轨全部完成后、Step B-join 处前台串行调用一次 android-api-inventory」——丢失并行收益但功能等价。

## auth-chain-probe（Step B-probe：登录链路活性探针并行轨）

B-join 确认 `data-chains/chain-auth.md` 落盘 + `spec/baseline/dev_info.json` 就位后即派发，与 Gate B 审批 + Phase C 的 C1–C4 并行；**前置齐即跑，不询问用户是否要跑**（前置缺才建 `U-ENV`/`U-ACCOUNT` 留给 grill，见 `grill-1-decision-gates.md` §C4.7b）：

```
Agent(
  subagent_type: "hmigbot:a2h-migration-worker",
  run_in_background: true,
  prompt: "执行 arkts-network-troubleshoot 场景 E（auth-chain 活性探针），验证登录链路能否真打通。
    MUST 读: references/probe-runbook.md（循环骨架 + 错误三分类 + 候选来源约定 + 上限 N=10 跳过）
           + references/probe-error-remediation.md（错误→修法知识库）
    只读输入: spec/baseline/api-inventory/data-chains/chain-auth.md（靶点 + 公参字段的值来源）
             spec/baseline/dev_info.json（测试 base_url + 业务成功码 + 测试账号）
             scripts/verify-sign.js（复用项目已复现的签名实现）

    【并行安全约束 —— 你与 Phase C 的 spec 生成并行运行，违反即产生读写竞态】
    1. 循环期全程只读：禁写任何 spec 产物（chain-auth / uncertainties / golden 一律不落盘）。
    2. 发现缓冲在返回值：结论、试出的真值、golden 请求响应、待补 KB 条目，全部作为返回值带回。
    3. 落盘由主线程在 C4.7b join 后统一执行；你不执行任何写操作。

    完成后返回 summary：
      - verdict: 'PASS' | 'BLOCKED' | 'EXHAUSTED' | 'UNKNOWN'
      - endpoint: 命中的靶点
      - resolved_values: 循环试出的能通值（版本 / baseType / 渠道 / 指纹等）
      - golden: 成功那次的 请求/响应/签名输入串（PASS 时必填，供主线程落 chain-auth.golden.json）
      - blockers: 后端侧 / 人输(MISSING-TRUTH) 类断点（供冒泡 grill）
      - tried_candidates: 试过的候选（EXHAUSTED 时必填）
      - new_kb_entries: 本轮撞到的新『错误→修法』模式（供追加知识库）"
)
```

记录句柄为 `$AUTH_PROBE_JOB`，主线继续 Gate B → Phase C；Step C4.7b `join` 后由**主线程**一次性落盘（存 golden + 回填真值 + `uncertainties[]` append + RED→GREEN 重投影）。

> **降级**：不支持后台子 agent → 不在此派发，由 Step C4.7b 前台串行跑同一循环（串行路径无并发写，上述只读约束不适用）。**非登录项目**（无 auth 链 / 无 chain-auth）不派发。

---

## b2-page-worker（Step B2：分页 spec 并行撰写）

派发数量 = `spec/.a2h/batch-plan.json` 的 `b2_batches` 条数，一批一个 worker，全部并行派出、
主线在 B2-join 等待汇合。agent 类型：`a2h-migration-worker`。

```
Agent(
  subagent_type: "hmigbot:a2h-migration-worker",
  prompt: "撰写本批分页 UI Spec。
    批次: {batch_id}
    ui_facts_policy: $UI_FACTS_POLICY  # 默认 legacy；其余 static-v1-shadow/static-v1
    页面清单: {pages}        # 取自 batch-plan.json，**不要自行增删**
    MUST 先 Read: a2h-spec/templates/page-spec-template.md（整文件，「必填字段」段不得删减）

    逐页读 spec/baseline/ui-snapshots/{page_id}/{meta.json, view.xml}，按模板产出
    spec/baseline/ui/{page_id}.md。「沉浸式 + 安全区」节按 meta.json 的 page_type 条件注入
    （规则见 page-spec-template.md §沉浸式条件注入）。

    仅 static-v1：读 a2h-spec/references/static-ui-facts.md，以及本页 visual.json、
    fixture.json、templates/。按事实解释动态行为，不能修改已解析的标量。
    disposition/绘制 interpretation 写本批 spec/.a2h/ui-facts-decisions/{batch_id}.json。
    主线程合并决策及 render；worker 不写生成的视觉事实块。

    同时读 spec/.a2h/spec-run/dialog-index.json：对当前 page spec，机械筛选 body_spec_location 或
    instance_spec_locations 文件部分命中本页的 rows。Body owner 读取 row.snapshot_ref 的
    meta.json/view.xml + Android layout，写唯一七字段正文/Variants；consumer 只写本页入口、参数、
    结果/刷新和 body 引用，但保留本页直接引用所需 android_source_anchors。禁止新增 Dialog page。

    【深度要求·硬性】`## 页面结构` 段非空行 ≥ 5（view.xml 存在时）；模板 6 个必填段每段
    均须有实质内容——**填两行占位视同未完成**。项目级塌陷由 C4.6f 的
    SPEC.PAGE_DEPTH_COLLAPSE 确定性判定（中位 <3 行或薄页占比 >40% 即阻断）。

    【写权围栏】只写本批 page_*.md；禁写 ui-manifest.md（主线单写者）、禁碰他批页面、
    禁碰 features/、ui-snapshots/ 与 dialog-snapshots/。

    【回执·返回前必写】spec/.a2h/worker-receipts/{batch_id}.json：
      {batch_id, agent, started_at, finished_at, produced:[...], self_check:{rounds, residual_findings}}
    并在每份产出的 frontmatter 写一行 `generated_by: {batch_id}`。

    返回 summary（≤30 行）：本批页数 / 每页行数 / view.xml 缺失页清单 / 存疑项",
)
```

## c4-feature-worker（Step C4：feature spec 并行撰写）

派发数量 = `batch-plan.json` 的 `c4_batches` 条数，一批一个 worker，全部并行、主线在
C4-join 汇合后再进 C4.5。agent 类型：`a2h-migration-worker`。

```
Agent(
  subagent_type: "hmigbot:a2h-migration-worker",
  prompt: "撰写本批 feature spec。
    批次: {batch_id}
    feature 清单: {features}      # 取自 batch-plan.json，不要自行增删
    期望 AC 区间: {est_ac_range}  # anchored_LOC 回归（n=17, r=0.84）；**提示值，非门禁**
    MUST 先 Read: a2h-spec/templates/feature-spec-template.md（整文件）
                + a2h-spec/references/c4-pre-complexity-and-budget.md（anchor 规则 + 义务判定）

    C4-pre：按 9 类 role 命名 glob 自动填充 anchors 并逐路径校验存在性。
    AC 格式：稳定 ID F{nnn}-AC{seq}（序号纯数字，禁字母后缀）+ `源:→标:` + `判:` + `真:src:<路径>:<行号>`。
    多个源符号时重复写 `源:` 锚，不要连写。
    **字段级格式以 feature-spec-template「机器契约」为准；生成 worker 不读 a2h-spec/scripts/
    下的检查器实现，也不跑 lint 的 `--help`**——模板解释不了的 finding 原样带回 summary，
    交主线或专门的诊断任务处理（linter 维护任务不受此限）。
    **只在本批已核实的范围内下结论**：写「全仓无调用点」「永不发生」「不存在该入口」这类
    跨范围断言，前提是本批任务真的扫过那个范围；扫不到就只描述本批看得见的部分，
    不影响当前实现的未知内容**直接省略**——省略与断言不存在是两回事，后者会把别的 feature
    的真实行为否掉（实测：壳 feature 断言「全仓无 X 调用点」，而购物车 feature 正确引了
    两处真实调用，两条 AC 直接互相否定）。拥有消费侧接口的 feature 只规约消费侧，
    生产者留给所属 feature。
    **平台 API 映射不现场遍历 SDK**：先查 feature-base「跨栈映射基线」、项目已有的
    HarmonyOS reference 与 verifier 既有结论；仍缺失则在 summary 记明所缺 API，由主线
    定点查证一次后下发，不要多个 worker 各自翻 SDK。
    **addenda**：profile 的 `required_addenda` 非空即须有对应专项材料——**写成主文件里的同名章节
    （有实质内容）即可兑现，与 sibling 文件等价**；只有主文件过长需要拆分时才产 sibling，
    **不得以「本功能不需要」为由省略**——义务由证据触发，只能兑现或在 Gate C 记为不适用；
    但兑现形态可选（项目级比例由 SPEC.ADDENDA_COLLAPSE 按义务数阻断，不数文件）。

    【生成即自检】每份写完（含 addenda）后必跑，至多自修 2 轮，残余 findings 原样进 summary：
      python3 <A2H_SPEC_SKILL_ROOT>/scripts/lint_coverage.py \
        --src $ANDROID_SRC --project-root $PROJECT_ROOT --only-feature F00x-xxx.md

    【写权围栏】只写本批 features/F*.md 及其 addenda；**禁写** decision-ledger.md
    （PD 清单随 summary 返回、主线统一落盘）、feature-index.md、feature-base.md。

    【回执·返回前必写】spec/.a2h/worker-receipts/{batch_id}.json（schema 同 b2-page-worker），
    并在每份产出的 frontmatter 写一行 `generated_by: {batch_id}`。

    返回 summary（≤50 行）：每 feature 的 AC 数 / addenda 清单 / PD 清单 / 残余 findings",
)
```

> **降级**：环境不支持并行派发 → 主线串行撰写，产物 frontmatter 填 `generated_by: main-inline`，
> 并落 `spec/.a2h/fanout-degraded.md` 交代原因与环境证据。**深度门禁不因降级放宽。**
