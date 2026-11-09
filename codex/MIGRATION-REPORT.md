# Codex 迁移报告（机械层转换产物）

由 `codex-adapter/scripts/convert.py`（`$codex-adapter` skill）生成。机械层 + 可确定性语义改写已自动完成；仍需理解才能改的列在「待人工 / LLM 处理」段。

## Skills（91 个）

| skill | type | 隐式路由 | desc 长度 | 备注 |
|---|---|---|---|---|
| app-relationship-tree | domain | off | 544 |  |
| arkts-accessibility | domain | off | 276 |  |
| arkts-animation-builder | domain | off | 286 |  |
| arkts-animation-migrate | domain | off | 869 |  |
| arkts-app-identity | domain | off | 346 |  |
| arkts-architecture-refactor | (无) | ON | 1136 |  |
| arkts-behavior-verify | (无) | ON | 194 | frontmatter 字段 `metadata` 已移除，需人工转为 body 指引 |
| arkts-codebase-config | codebase | ON | 400 |  |
| arkts-codebase-debug | codebase | ON | 549 |  |
| arkts-codebase-explainer | codebase | ON | 450 |  |
| arkts-codebase-locator | codebase | ON | 522 |  |
| arkts-codebase-modifier | codebase | ON | 512 |  |
| arkts-component-builder | domain | off | 302 |  |
| arkts-customer-service | domain | off | 427 |  |
| arkts-dark-mode | domain | off | 315 |  |
| arkts-data-layer | domain | off | 290 |  |
| arkts-design-tokens-extractor | domain | off | 469 |  |
| arkts-download-manager | domain | off | 198 |  |
| arkts-dt-verifier | domain | off | 488 | 内嵌 prompt 模板 step1-unit-test-agent.md → references/agent-prompts/; 内嵌 prompt 模板 step2-test-data-agent.md → references/agent-prompts/; 内嵌 prompt 模板 step2b-id-injector-agent.md → references/agent-prompts/; 内嵌 prompt 模板 step3-ui-test-agent.md → references/agent-prompts/; 内嵌 prompt 模板 step4-infra-compile-agent.md → references/agent-prompts/ |
| arkts-feature-coverage-auditor | domain | off | 517 |  |
| arkts-i18n | domain | off | 168 |  |
| arkts-icon-sizing | domain | off | 457 |  |
| arkts-immersive-safearea | domain | off | 318 |  |
| arkts-knowledge-verifier | domain | off | 241 |  |
| arkts-large-font | domain | off | 242 |  |
| arkts-library-migration | domain | off | 192 |  |
| arkts-login | domain | off | 769 |  |
| arkts-media-playback | domain | off | 257 |  |
| arkts-multi-device | domain | off | 380 |  |
| arkts-multi-window | domain | off | 366 |  |
| arkts-navigation-builder | domain | off | 265 |  |
| arkts-network-troubleshoot | domain | off | 843 |  |
| arkts-pattern-library | domain | off | 273 |  |
| arkts-payment | domain | off | 523 |  |
| arkts-project-scaffolder | domain | off | 349 |  |
| arkts-router-verify | (无) | ON | 514 |  |
| arkts-scenario-runner | (无) | ON | 473 |  |
| arkts-spec-evolver | domain | off | 178 |  |
| arkts-state-manager | domain | off | 252 |  |
| arkts-structural-closure | domain | off | 312 |  |
| arkts-system-capabilities | domain | off | 269 |  |
| arkts-text-truncation | domain | off | 428 |  |
| arkts-truncation-fix | domain | off | 463 |  |
| arkts-ui-alignment | domain | off | 213 |  |
| arkts-ui-coverage-auditor | domain | off | 438 |  |
| arkts-ui-verifier | domain | off | 233 | 内嵌 agent arkts-ui-fixer.md → codex/agents/arkts-ui-fixer.toml + references/agent-prompts/; 内嵌 agent step1-design-agent.md → codex/agents/arkts-ui-test-designer.toml + references/agent-prompts/; 内嵌 agent step2-generate-agent.md → codex/agents/arkts-ui-test-generator.toml + references/agent-prompts/; 内嵌 agent step3-execute-agent.md → codex/agents/arkts-ui-test-executor.toml + references/agent-prompts/ |
| arkts-ut-verifier | domain | off | 350 | 内嵌 agent arkts-ut-fixer.md → codex/agents/arkts-ut-fixer.toml + references/agent-prompts/; 内嵌 prompt 模板 step0-oracle-agent.md → references/agent-prompts/; 内嵌 prompt 模板 step1-design-agent.md → references/agent-prompts/; 内嵌 prompt 模板 step2-generate-agent.md → references/agent-prompts/; 内嵌 prompt 模板 step3-execute-agent.md → references/agent-prompts/ |
| arkts-video-playback | domain | off | 253 |  |
| arkts-visual-verify | (无) | ON | 214 |  |
| arkts-webview | domain | off | 323 |  |
| arkts-webview-manager | domain | off | 513 |  |
| claude-session-stats | util | ON | 194 |  |
| commit | tool | ON | 131 |  |
| dfr-fmea-general | (无) | ON | 104 |  |
| grill-with-docs | tool | ON | 278 |  |
| hmos-env-doctor | tool | ON | 215 |  |
| hmos-fix-build-errors | tool | ON | 516 | frontmatter 字段 `argument-hint` 已移除，需人工转为 body 指引; frontmatter 字段 `allowed-tools` 已移除，需人工转为 body 指引 |
| i2h-build | command | ON | 68 | Claude command → Codex skill 入口 |
| i2h-build-zh | command | ON | 34 | Claude command → Codex skill 入口 |
| i2h-execute | pipeline | ON | 80 |  |
| i2h-init | command | ON | 73 | Claude command → Codex skill 入口 |
| i2h-init-zh | command | ON | 25 | Claude command → Codex skill 入口 |
| i2h-plan | pipeline | ON | 214 |  |
| i2h-retrospect | pipeline | ON | 41 |  |
| i2h-run | command | ON | 81 | Claude command → Codex skill 入口 |
| i2h-run-zh | command | ON | 72 | Claude command → Codex skill 入口 |
| i2h-spec | pipeline | ON | 94 |  |
| i2h-verify | pipeline | ON | 161 |  |
| ios-api-inventory | domain | off | 361 |  |
| ios-fact-tree | domain | off | 360 |  |
| ios-ui-graph-builder | domain | off | 595 |  |
| ios-ui-graph-query | domain | off | 376 |  |
| ios2hmos_resources_convert | domain | off | 697 |  |
| ios_fast_traverse | domain | off | 331 |  |
| migbot-increment-applying | (无) | ON | 159 | frontmatter 字段 `compatible` 已移除，需人工转为 body 指引 |
| migbot-increment-archiving | (无) | ON | 156 | frontmatter 字段 `compatible` 已移除，需人工转为 body 指引 |
| migbot-increment-implementing | (无) | ON | 174 | frontmatter 字段 `compatible` 已移除，需人工转为 body 指引 |
| migbot-increment-init | (无) | ON | 195 | frontmatter 字段 `compatible` 已移除，需人工转为 body 指引 |
| migbot-increment-planning | (无) | ON | 273 | frontmatter 字段 `compatible` 已移除，需人工转为 body 指引 |
| migbot-increment-reviewing | (无) | ON | 133 |  |
| mod-design | (无) | ON | 209 |  |
| prd-generator | (无) | ON | 322 |  |
| rq-clarify | (无) | ON | 90 |  |
| rq-codebase | (无) | ON | 69 |  |
| rq-parse | (无) | ON | 147 |  |
| skill-checker | tool | ON | 412 |  |
| swiftui-to-arkui | domain | off | 344 |  |
| tdd-enforcer | (无) | ON | 133 | frontmatter 字段 `compatible` 已移除，需人工转为 body 指引 |
| tool-optimization | reference | ON | 47 |  |
| toolkit-fact-indexer | (无) | ON | 469 |  |
| visual-verify-speed | (无) | ON | 394 |  |

隐式路由 ON 共 43 个，description 总长约 10727 字符（Codex 预算：上下文 2% 或 8000 字符）。

## Agents（11 个 TOML）

| agent | 来源 | 处理 |
|---|---|---|
| arkts-ui-fixer | skills/arkts-ui-verifier/agents/arkts-ui-fixer.md | model: opus → 注释保留; color: orange → 丢弃; tools 白名单 → developer_instructions 行为约束 |
| arkts-ui-test-designer | skills/arkts-ui-verifier/agents/step1-design-agent.md | tools 白名单 → developer_instructions 行为约束 |
| arkts-ui-test-executor | skills/arkts-ui-verifier/agents/step3-execute-agent.md | tools 白名单 → developer_instructions 行为约束 |
| arkts-ui-test-generator | skills/arkts-ui-verifier/agents/step2-generate-agent.md | tools 白名单 → developer_instructions 行为约束 |
| arkts-ut-fixer | skills/arkts-ut-verifier/agents/arkts-ut-fixer.md | model: opus → 注释保留; color: orange → 丢弃; tools 白名单 → developer_instructions 行为约束 |
| hmos-builder | migbot/agents/hmos-builder.md | color: blue → 丢弃; skills 预加载(1) → developer_instructions 指引; tools 白名单 → developer_instructions 行为约束 |
| i2h-closer | migbot/agents/i2h-closer.md | model: opus → 注释保留; color: cyan → 丢弃; skills 预加载(2) → developer_instructions 指引; tools 白名单 → developer_instructions 行为约束 |
| i2h-fixer | migbot/agents/i2h-fixer.md | model: opus → 注释保留; color: orange → 丢弃; tools 白名单 → developer_instructions 行为约束 |
| i2h-ios-analyzer | migbot/agents/i2h-ios-analyzer.md | model: opus → 注释保留; color: yellow → 丢弃; tools 白名单 → developer_instructions 行为约束 |
| i2h-migration-worker | migbot/agents/i2h-migration-worker.md | model: opus → 注释保留; color: green → 丢弃; skills 预加载(11) → developer_instructions 指引; tools 白名单 → developer_instructions 行为约束 |
| i2h-view-converter | migbot/agents/i2h-view-converter.md | model: opus → 注释保留; color: cyan → 丢弃; skills 预加载(3) → developer_instructions 指引; tools 白名单 → developer_instructions 行为约束 |

## 丢弃的 frontmatter 字段（需人工转 body 指引）

- `skills/arkts-behavior-verify/SKILL.md` → `metadata`: {'type': 'codebase', 'domain': 'migration', 'tags': ['setting', 'interaction', '
- `skills/hmos_fix_build_errors/SKILL.md` → `argument-hint`: <harmonyos-project-path> <deveco-studio-path> [--signed] [--build-only]
- `skills/hmos_fix_build_errors/SKILL.md` → `allowed-tools`: Agent, Read, Write, Edit, Glob, Grep, Bash
- `skills/migbot-increment-applying/SKILL.md` → `compatible`: ['{项目名}-main']
- `skills/migbot-increment-archiving/SKILL.md` → `compatible`: ['{项目名}-main']
- `skills/migbot-increment-implementing/SKILL.md` → `compatible`: ['{项目名}-main']
- `skills/migbot-increment-init/SKILL.md` → `compatible`: ['{项目名}-main']
- `skills/migbot-increment-planning/SKILL.md` → `compatible`: ['{项目名}-main']
- `skills/tdd-enforcer/SKILL.md` → `compatible`: ['{项目名}-main']
- `commands/i2h-build-zh.md` → `allowed-tools`: Bash(.migbot/bin/i2h-tool *), Bash(.migbot/bin/i2h *)
- `commands/i2h-build.md` → `allowed-tools`: Bash(.migbot/bin/i2h-tool *), Bash(.migbot/bin/i2h *)
- `commands/i2h-init-zh.md` → `allowed-tools`: Bash, Read, Edit, Write
- `commands/i2h-init.md` → `allowed-tools`: Bash, Read, Edit, Write

## 位置迁移（skill 内嵌 agents）

- `skills/arkts-dt-verifier/agents/step1-unit-test-agent.md` → `skills/arkts-dt-verifier/references/agent-prompts/step1-unit-test-agent.md`
- `skills/arkts-dt-verifier/agents/step2-test-data-agent.md` → `skills/arkts-dt-verifier/references/agent-prompts/step2-test-data-agent.md`
- `skills/arkts-dt-verifier/agents/step2b-id-injector-agent.md` → `skills/arkts-dt-verifier/references/agent-prompts/step2b-id-injector-agent.md`
- `skills/arkts-dt-verifier/agents/step3-ui-test-agent.md` → `skills/arkts-dt-verifier/references/agent-prompts/step3-ui-test-agent.md`
- `skills/arkts-dt-verifier/agents/step4-infra-compile-agent.md` → `skills/arkts-dt-verifier/references/agent-prompts/step4-infra-compile-agent.md`
- `skills/arkts-ui-verifier/agents/arkts-ui-fixer.md` → `skills/arkts-ui-verifier/references/agent-prompts/arkts-ui-fixer.md`
- `skills/arkts-ui-verifier/agents/step1-design-agent.md` → `skills/arkts-ui-verifier/references/agent-prompts/step1-design-agent.md`
- `skills/arkts-ui-verifier/agents/step2-generate-agent.md` → `skills/arkts-ui-verifier/references/agent-prompts/step2-generate-agent.md`
- `skills/arkts-ui-verifier/agents/step3-execute-agent.md` → `skills/arkts-ui-verifier/references/agent-prompts/step3-execute-agent.md`
- `skills/arkts-ut-verifier/agents/arkts-ut-fixer.md` → `skills/arkts-ut-verifier/references/agent-prompts/arkts-ut-fixer.md`
- `skills/arkts-ut-verifier/agents/step0-oracle-agent.md` → `skills/arkts-ut-verifier/references/agent-prompts/step0-oracle-agent.md`
- `skills/arkts-ut-verifier/agents/step1-design-agent.md` → `skills/arkts-ut-verifier/references/agent-prompts/step1-design-agent.md`
- `skills/arkts-ut-verifier/agents/step2-generate-agent.md` → `skills/arkts-ut-verifier/references/agent-prompts/step2-generate-agent.md`
- `skills/arkts-ut-verifier/agents/step3-execute-agent.md` → `skills/arkts-ut-verifier/references/agent-prompts/step3-execute-agent.md`
- `skills/hmos_fix_build_errors/` → `skills/hmos-fix-build-errors/（目录名对齐 frontmatter name）`

## 语义层自动改写（rewrite.py）

族：`rewrite` = 形态翻译（措辞/路径/调用语法）；`divergence` = 平台能力分歧（两边工具或流程真的不同，见 R10）。

| 规则 | 族 | 命中次数 |
|---|---|---|
| R1-brand-bare | rewrite | 42 |
| D2-i2h-slash-command | divergence | 39 |
| R1-skill-rename | rewrite | 38 |
| R1-brand-cc | rewrite | 34 |
| R1-skills-dir | rewrite | 33 |
| R5-agent-prompt-path | rewrite | 23 |
| R1-dot-claude-home | rewrite | 21 |
| R2-paren-backticked | rewrite | 21 |
| R1-dot-claude | rewrite | 18 |
| R2-paren-bare | rewrite | 18 |
| R3-agent-call-fallback | rewrite | 15 |
| R3-agent-tool | rewrite | 13 |
| block-skill-fenced | rewrite | 11 |
| R3-subagent-type-field | rewrite | 9 |
| R3-agent-call-field | rewrite | 9 |
| R3-subagent-type-fallback | rewrite | 9 |
| R1-agents-dir | rewrite | 9 |
| R3-dispatch-noun | rewrite | 8 |
| D2-codex-plugin-root | divergence | 8 |
| D2-plugin-root-var | divergence | 7 |
| R1-claude-md | rewrite | 6 |
| R2-python-call-no-args | rewrite | 6 |
| R3-subagent-prose-general-q | rewrite | 5 |
| R3-agent-tool-tick | rewrite | 5 |
| R3-general-purpose | rewrite | 3 |
| D3-task-tool-context | divergence | 3 |
| block-agent-pseudo-general | rewrite | 3 |
| R2-inline-with-args | rewrite | 3 |
| block-agent-fenced | rewrite | 3 |
| R1-skills-dir-home | rewrite | 2 |
| D3-task-tool-dispatch-md | divergence | 2 |
| R2-tool-phrasing | rewrite | 2 |
| file-protected | rewrite | 2 |
| R2-python-call-with-args | rewrite | 2 |
| R3-dispatch-named-paren | rewrite | 1 |
| R3-dispatch-named-bare | rewrite | 1 |
| R3-plural-all | rewrite | 1 |
| R2-call-with-args | rewrite | 1 |
| R3-subagent-prose-general | rewrite | 1 |

保护区跳过 13 行（规则会误伤的语境，登记在 `exceptions.yaml`）。

- `skills/arkts-structural-closure/SKILL.md` L91: `- 跨 Slice **orphan VM 检测**（候选 = `viewmodels/` / `store/` / `repository/` / `service/` 下所有导出类）+ **组件孤儿检测（E1）**（候选 = `comp`
- `skills/arkts-visual-verify/CHANGELOG.md` L35: `本目录（Claude Code 源）由该 codex 版逆向得到：逆向后与按差异块合入的源侧逐块核对一致，只差平台写法。`
- `skills/arkts-visual-verify/CHANGELOG.md` L38: `- 14 行讲双平台事实的注释 / docstring（`check_dimension_prereqs.py` 与两个 `_tests`）末尾加 `codex-keep`，转换时原样保留，`
- `skills/arkts-visual-verify/CHANGELOG.md` L65: `探针端到端（codex 形状 `.agents/skills`+`.codex/agents/*.toml` ✅、claude 形状 ✅、显式模式不打「另查过」）、**静态闸**：业务脚本不得再拼 `.claude/.codex/.agen`
- `skills/arkts-visual-verify/CHANGELOG.md` L211: ``$android-fact-tree` ↔ `Skill(android-fact-tree)`、`~/.agents/skills` ↔ `~/.claude/skills`、`
- `skills/arkts-visual-verify/scripts/_tests/test_env_neutral_0916.py` L4: `C1：前置探针按 ~/.claude/agents/<a>.md 找 agent，codex 线 agent 在 .codex/agents/<a>.toml → 恒「未注册」→ UNIT 级 ABORT，整条 codex 线挡死。  co`
- `skills/arkts-visual-verify/scripts/_tests/test_env_neutral_0916.py` L9: `② agent_registered：.claude/agents/*.md、.codex/agents/*.toml、插件缓存兄弟 agents/ 三种布局  codex-keep`
- `skills/arkts-visual-verify/scripts/_tests/test_env_neutral_0916.py` L142: `assert "hmos_fix_build_errors 已安装" in out or "hmos-fix-build-errors 已安装" in out, out   # 连字符目录名也认  codex-keep`
- `skills/arkts-visual-verify/scripts/_tests/test_plugin_form_0915.py` L4: `① check_dimension_prereqs 的 skills 根 / agent 目录解析认插件缓存布局（此前只认 ~/.claude/skills 与 ~/.claude/agents）  codex-keep`
- `skills/arkts-visual-verify/scripts/_tests/test_plugin_form_0915.py` L41: `"""~/.claude/plugins/cache/<marketplace>/<plugin>/<ver>/{skills,agents} codex-keep"""`
- `skills/arkts-visual-verify/scripts/_tests/test_plugin_form_0915.py` L47: `if with_fixbuild:                                   # 源侧目录名 hmos_fix_build_errors，codex 产物改成了短横线名；两种都摆  codex-keep`
- `skills/arkts-visual-verify/scripts/_tests/test_plugin_form_0915.py` L48: `_w(root / "skills" / "hmos_fix_build_errors" / "SKILL.md")  # codex-keep`
- `skills/arkts-visual-verify/scripts/_tests/test_plugin_form_0915.py` L100: `"""用户级安装（~/.claude/skills + ~/.claude/agents）：老路径照旧 ✅，无插件提示行。 codex-keep"""`

## 平台能力分歧补丁（overlay.py）

行规则做不了的那部分分歧：删整行 / 换整节 / 插 banner。登记在 `codex-adapter/scripts/overlays.yaml`，正文在 `codex-adapter/overlays/`。

| overlay | 目标 | 命中 | 被覆盖内容 digest |
|---|---|---|---|
| D-dispatch-banner | `skills/i2h-spec/SKILL.md` | 1 | — |
| D-dispatch-banner | `skills/i2h-execute/SKILL.md` | 1 | — |

## 产物结构校验

✓ 全部通过：agent TOML 可解析、SKILL.md frontmatter 完整、目录名与 name 一致、openai.yaml 可解析、R8 禁用词残留 0、转换未引入断链。

> ⚠ 隐式路由 ON 43 个，description 总长 10727 > 预算 8000（超 2727）。超出部分会被截断，排在后面的 skill 将静默失去自动触发能力。其中 26 个源侧缺 type 字段而默认 ON：arkts-architecture-refactor, arkts-behavior-verify, arkts-router-verify, arkts-scenario-runner, arkts-visual-verify…

## 待人工 / LLM 处理（机械层处理不了）

无。

## 机械扫描全景（宽口径，含已自动改写的）

共 94 处命中，涉及 44 个文件。

### agents/arkts-ui-fixer.toml
- L3 [claude-brand] `# 原 Claude Code 配置 model: opus（Codex 无 Claude 模型 pin，继承会话模型）`
- L6 [claude-brand] `## 工具边界（原 Claude Code 工具白名单，作为行为约束遵守，非硬性权限）`

### agents/arkts-ui-test-designer.toml
- L5 [claude-brand] `## 工具边界（原 Claude Code 工具白名单，作为行为约束遵守，非硬性权限）`

### agents/arkts-ui-test-executor.toml
- L5 [claude-brand] `## 工具边界（原 Claude Code 工具白名单，作为行为约束遵守，非硬性权限）`

### agents/arkts-ui-test-generator.toml
- L5 [claude-brand] `## 工具边界（原 Claude Code 工具白名单，作为行为约束遵守，非硬性权限）`

### agents/arkts-ut-fixer.toml
- L3 [claude-brand] `# 原 Claude Code 配置 model: opus（Codex 无 Claude 模型 pin，继承会话模型）`
- L6 [claude-brand] `## 工具边界（原 Claude Code 工具白名单，作为行为约束遵守，非硬性权限）`

### agents/hmos-builder.toml
- L5 [claude-brand] `## 前置 Skills（原 Claude Code spawn 时预加载，Codex 下改为执行前显式加载）`
- L9 [claude-brand] `## 工具边界（原 Claude Code 工具白名单，作为行为约束遵守，非硬性权限）`

### agents/i2h-closer.toml
- L3 [claude-brand] `# 原 Claude Code 配置 model: opus（Codex 无 Claude 模型 pin，继承会话模型）`
- L6 [claude-brand] `## 前置 Skills（原 Claude Code spawn 时预加载，Codex 下改为执行前显式加载）`
- L11 [claude-brand] `## 工具边界（原 Claude Code 工具白名单，作为行为约束遵守，非硬性权限）`

### agents/i2h-fixer.toml
- L3 [claude-brand] `# 原 Claude Code 配置 model: opus（Codex 无 Claude 模型 pin，继承会话模型）`
- L6 [claude-brand] `## 工具边界（原 Claude Code 工具白名单，作为行为约束遵守，非硬性权限）`

### agents/i2h-ios-analyzer.toml
- L3 [claude-brand] `# 原 Claude Code 配置 model: opus（Codex 无 Claude 模型 pin，继承会话模型）`
- L6 [claude-brand] `## 工具边界（原 Claude Code 工具白名单，作为行为约束遵守，非硬性权限）`

### agents/i2h-migration-worker.toml
- L3 [claude-brand] `# 原 Claude Code 配置 model: opus（Codex 无 Claude 模型 pin，继承会话模型）`
- L6 [claude-brand] `## 前置 Skills（原 Claude Code spawn 时预加载，Codex 下改为执行前显式加载）`
- L20 [claude-brand] `## 工具边界（原 Claude Code 工具白名单，作为行为约束遵守，非硬性权限）`

### agents/i2h-view-converter.toml
- L3 [claude-brand] `# 原 Claude Code 配置 model: opus（Codex 无 Claude 模型 pin，继承会话模型）`
- L6 [claude-brand] `## 前置 Skills（原 Claude Code spawn 时预加载，Codex 下改为执行前显式加载）`
- L12 [claude-brand] `## 工具边界（原 Claude Code 工具白名单，作为行为约束遵守，非硬性权限）`

### bin/scripts/scheduler/intelligent_scheduler.py
- L170 [agent-dispatch] `scheduler.add_task(Task("page_001", 10))`
- L171 [agent-dispatch] `scheduler.add_task(Task("page_002", 5))`
- L172 [agent-dispatch] `scheduler.add_task(Task("page_003", 15))`
- L173 [agent-dispatch] `scheduler.add_task(Task("page_004", 8))`
- L174 [agent-dispatch] `scheduler.add_task(Task("page_005", 12))`
- L175 [agent-dispatch] `scheduler.add_task(Task("page_006", 3))`
- L178 [agent-dispatch] `scheduler.add_task(Task("feat_001", 60, dependencies=[]))`
- L179 [agent-dispatch] `scheduler.add_task(Task("feat_002", 30, dependencies=["feat_001"]))`

### bin/scripts/scheduler/test_intelligent_scheduler.py
- L9 [agent-dispatch] `scheduler.add_task(Task("a", 20, host="claude"))`
- L10 [agent-dispatch] `scheduler.add_task(Task("b", 5, host="claude"))`
- L11 [agent-dispatch] `scheduler.add_task(Task("c", 5, dependencies=["a"], host="codex"))`
- L12 [agent-dispatch] `scheduler.add_task(Task("d", 5, host="codex"))`
- L19 [agent-dispatch] `scheduler.add_task(Task("slow", 60))`
- L20 [agent-dispatch] `scheduler.add_task(Task("independent", 5))`
- L21 [agent-dispatch] `scheduler.add_task(Task("dependent", 5, dependencies=["slow"]))`
- L31 [agent-dispatch] `scheduler.add_task(Task("a", 1, dependencies=["missing"]))`
- L35 [agent-dispatch] `scheduler.add_task(Task("a", 1, dependencies=["b"]))`
- L36 [agent-dispatch] `scheduler.add_task(Task("b", 1, dependencies=["a"]))`

### commands/i2h-build-zh.md
- L5 [claude-brand] `## 调用参数与工具边界（原 Claude Code frontmatter 迁移）`

### commands/i2h-build.md
- L5 [claude-brand] `## 调用参数与工具边界（原 Claude Code frontmatter 迁移）`

### commands/i2h-init-zh.md
- L5 [claude-brand] `## 调用参数与工具边界（原 Claude Code frontmatter 迁移）`

### commands/i2h-init.md
- L5 [claude-brand] `## 调用参数与工具边界（原 Claude Code frontmatter 迁移）`

### commands/i2h-run-zh.md
- L5 [arguments-var] ``$ARGUMENTS` 被忽略。`
- L53 [skill-call] `2. 调用 skill：`Skill(skill="<skill-name>")``

### commands/i2h-run.md
- L5 [arguments-var] ``$ARGUMENTS` is ignored.`
- L60 [skill-call] `2. Invoke skill: `Skill(skill="<skill-name>")``

### skills/arkts-media-playback/SKILL.md
- L164 [agent-dispatch] `- [ ] **代码**：`wantAgent.getWantAgent(info)` 创建通知栏返回意图`
- L196 [agent-dispatch] `const agent = await wantAgent.getWantAgent(wantAgentInfo);`

### skills/arkts-media-playback/references/background-playback.md
- L92 [agent-dispatch] `const agent = await wantAgent.getWantAgent(wantAgentInfo);`

### skills/arkts-payment/SKILL.md
- L157 [agent-dispatch] `1. **UA 伪装**：`Web.userAgent(PAYMENT_USER_AGENT)`（标准 Android Chrome UA）`

### skills/arkts-payment/references/04-h5-container.md
- L17 [agent-dispatch] `Web({ src, controller }).userAgent(PAYMENT_USER_AGENT)`
- L245 [agent-dispatch] `.userAgent(PAYMENT_USER_AGENT)`

### skills/arkts-structural-closure/SKILL.md
- L101 [dot-claude-path] `- 跨 Slice **orphan VM 检测**（候选 = `viewmodels/` / `store/` / `repository/` / `service/` 下所有导出类）+ **组件孤儿检测（E1）**（候选 = `components/` / `views/` / `widgets/` / `dial`

### skills/arkts-system-capabilities/references/avplayer-guide.md
- L132 [agent-dispatch] `const agent = await wantAgent.getWantAgent(info);`

### skills/arkts-system-capabilities/references/background-tasks.md
- L89 [agent-dispatch] `const wantAgentObj = await wantAgent.getWantAgent(wantAgentInfo)`
- L214 [agent-dispatch] `const agent = await wantAgent.getWantAgent(wantAgentInfo);`

### skills/arkts-visual-verify/CHANGELOG.md
- L35 [claude-brand] `本目录（Claude Code 源）由该 codex 版逆向得到：逆向后与按差异块合入的源侧逐块核对一致，只差平台写法。`
- L65 [dot-claude-path] `探针端到端（codex 形状 `.agents/skills`+`.codex/agents/*.toml` ✅、claude 形状 ✅、显式模式不打「另查过」）、**静态闸**：业务脚本不得再拼 `.claude/.codex/.agents``
- L211 [dot-claude-path] ``$android-fact-tree` ↔ `Skill(android-fact-tree)`、`~/.agents/skills` ↔ `~/.claude/skills`、`

### skills/arkts-visual-verify/scripts/_tests/test_env_neutral_0916.py
- L4 [dot-claude-path] `C1：前置探针按 ~/.claude/agents/<a>.md 找 agent，codex 线 agent 在 .codex/agents/<a>.toml → 恒「未注册」→ UNIT 级 ABORT，整条 codex 线挡死。  codex-keep`
- L9 [dot-claude-path] `② agent_registered：.claude/agents/*.md、.codex/agents/*.toml、插件缓存兄弟 agents/ 三种布局  codex-keep`

### skills/arkts-visual-verify/scripts/_tests/test_plugin_form_0915.py
- L4 [dot-claude-path] `① check_dimension_prereqs 的 skills 根 / agent 目录解析认插件缓存布局（此前只认 ~/.claude/skills 与 ~/.claude/agents）  codex-keep`
- L41 [dot-claude-path] `"""~/.claude/plugins/cache/<marketplace>/<plugin>/<ver>/{skills,agents} codex-keep"""`
- L100 [dot-claude-path] `"""用户级安装（~/.claude/skills + ~/.claude/agents）：老路径照旧 ✅，无插件提示行。 codex-keep"""`

### skills/arkts-webview-manager/references/webview-controller.md
- L219 [agent-dispatch] `this.webController.setCustomUserAgent(uaString);`

### skills/arkts-webview-manager/references/webview-page-modes.md
- L18 [agent-dispatch] `this.webController.setCustomUserAgent(this.isDesktopMode ? desktopUA : mobileUA);`

### skills/arkts-webview/references/webview-controller.md
- L219 [agent-dispatch] `this.webController.setCustomUserAgent(uaString);`

### skills/arkts-webview/references/webview-page-modes.md
- L18 [agent-dispatch] `this.webController.setCustomUserAgent(this.isDesktopMode ? desktopUA : mobileUA);`

### skills/hmos-fix-build-errors/SKILL.md
- L10 [claude-brand] `## 调用参数与工具边界（原 Claude Code frontmatter 迁移）`
- L20 [arguments-var] `- **HarmonyOS Project**: `$ARGUMENTS[0]` (the HarmonyOS project root, e.g. `D:/MyHmosApp`)`
- L21 [arguments-var] `- **DevEco Studio Path**: `$ARGUMENTS[1]` (DevEco Studio installation root, e.g. Windows `D:/DevEco Studio`; macOS `/Applications/DevEco-Studio.app/Contents`)`
- L22 [arguments-var] `- **--signed** (optional): `$ARGUMENTS[2]` — if set to `--signed`, the build produces a **signed HAP**. If omitted, the build produces an **unsigned HAP** (defa`
- L34 [arguments-var] `1. **Verify project exists** — Check that `$ARGUMENTS[0]` contains a valid HarmonyOS project (look for `build-profile.json5`, `entry/src` directory, `oh-package`
- L37 [arguments-var] `- **Windows** → check `$ARGUMENTS[1]` contains:`
- L42 [arguments-var] `- **macOS / Linux** → check `$ARGUMENTS[1]` (macOS DevEco root is typically `/Applications/DevEco-Studio.app/Contents`) contains:`
- L70 [arguments-var] `5. **Determine Build Mode** — Check if `$ARGUMENTS[2]` equals `--signed`:`

### skills/i2h-build-zh/SKILL.md
- L5 [claude-brand] `## 调用参数与工具边界（原 Claude Code frontmatter 迁移）`

### skills/i2h-build/SKILL.md
- L5 [claude-brand] `## 调用参数与工具边界（原 Claude Code frontmatter 迁移）`

### skills/i2h-execute/SKILL.md
- L14 [agent-dispatch] `> **Codex subagent dispatch convention.** This skill dispatches subagents. In Codex, spawn them with the `spawn_agent` tool and pass `agent_type` = the role nam`

### skills/i2h-init-zh/SKILL.md
- L5 [claude-brand] `## 调用参数与工具边界（原 Claude Code frontmatter 迁移）`

### skills/i2h-init/SKILL.md
- L5 [claude-brand] `## 调用参数与工具边界（原 Claude Code frontmatter 迁移）`

### skills/i2h-run-zh/SKILL.md
- L5 [arguments-var] ``$ARGUMENTS` 被忽略。`
- L53 [skill-call] `2. 调用 skill：`Skill(skill="<skill-name>")``

### skills/i2h-run/SKILL.md
- L5 [arguments-var] ``$ARGUMENTS` is ignored.`
- L60 [skill-call] `2. Invoke skill: `Skill(skill="<skill-name>")``

### skills/i2h-spec/SKILL.md
- L12 [agent-dispatch] `> **Codex subagent dispatch convention.** This skill dispatches subagents. In Codex, spawn them with the `spawn_agent` tool and pass `agent_type` = the role nam`

### skills/skill-checker/references/skill-hub-guide.md
- L11 [claude-brand] `arkts-skills/                    ← Claude Code 平台 skills`
- L127 [claude-brand] `platform: claude-code`
- L137 [claude-brand] `| platform | 是 | 所属平台（claude-code / opencode） |`
- L188 [claude-brand] `platform: claude-code`
- L332 [claude-brand] `### Q: 同一个 Skill 在 claude-code 和 opencode 都有，Hub 怎么处理？`

### skills/skill-checker/references/skill-taxonomy.yaml
- L26 [claude-brand] `claude-code: "Claude Code"`
