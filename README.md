# iOS MigBot

`hmigbot-ios` is an iOS → HarmonyOS (ArkTS) migration toolkit for Claude Code. It is a platform adaptation of [`../hmigbot-1.8.0`](../hmigbot-1.8.0), whose original workflow targets Android → HarmonyOS migration.

The project keeps the original pipeline shape while replacing Android-specific inputs with iOS inputs such as Xcode projects, Swift/SwiftUI/UIKit source, Info.plist, Assets.xcassets and iOS API usage.

## Current status

The repository contains the five i2h pipeline skills, iOS reference skills, templates, scripts and a Cuike pilot history. The design and most documentation work is present, but the repository is not yet proven as a production-ready end-to-end tool. The current gaps and reproducible evidence are tracked in [`docs/IMPLEMENTATION_AUDIT.md`](docs/IMPLEMENTATION_AUDIT.md).

The often-cited Cuike figure of “90.8% automatic conversion” is a historical prototype estimate. It is not a compiler pass rate, behavior-equivalence result or acceptance criterion for arbitrary projects.

## Pipeline

```text
iOS project
  ↓
i2h-spec       scan source and produce UI / feature specifications
  ↓
i2h-plan       produce indexed-v1 UI, Base and Slice plans
  ↓
i2h-execute   generate ArkTS, wire features, run gates and build loops
  ↓
i2h-verify     run static, identity and selected device checks
  ↓
i2h-retrospect collect measured results and delivery evidence
```

The intended execution model is LLM-led semantic analysis plus deterministic scripts for scanning, validation, writeback and reporting. Parallel work follows the original single-writer discipline: workers own their files, closers own shared wiring and ledgers, and findings close only after the owning check is rerun.

## Install

```bash
cd /path/to/hmigbot-ios
./install.sh --project /path/to/HarmonyOSProject --ios /path/to/iOSApp
```

Prerequisites are Python 3.8+, Claude Code, an iOS project containing an `.xcodeproj` or `Package.swift`, and a HarmonyOS project prepared for DevEco Studio. Device checks additionally require Xcode tools, `hdc`, and the relevant device or simulator.

After installation, `/i2h-init` and `/i2h-run` are the intended workflow entry points. The `/i2h-build` command currently references runtime executables that are not installed by this repository; see the audit before relying on it.

## Repository layout

```text
hmigbot-ios/
├── README.md / README_CN.md       current entry documentation
├── CHANGELOG.md                   iOS-oriented change history
├── HANDOVER.md                    current handover and next actions
├── QUICK_REFERENCE.md             current navigation and evidence policy
├── PROJECT_STATUS.md              current status snapshot
├── docs/
│   ├── METHODOLOGY.md             extracted migration method
│   ├── IMPLEMENTATION_AUDIT.md    evidence-based issue list and fixes
│   ├── ARCHIVE_INDEX.md            document map
│   ├── current/                   durable design notes
│   └── archive/                   phase reports and session history
├── migbot/                        installable commands, agents and skills
└── references/                    imported iOS expertise and source material
```

The historical reports intentionally remain available in `docs/archive/`; they are evidence of the evolution of the adaptation, not current status.

## Reference relationship

`hmigbot-1.8.0` is the Android baseline. Its architecture, gates, artifact contracts and concurrency rules are useful references, but Android assumptions must be translated before reuse. iOS-specific behavior belongs in the i2h skills and in the iOS reference skills under `migbot/skills/ios-*`.

See:

- [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) for the extracted process and design principles.
- [`docs/ORIGINAL_VS_IOS_ANALYSIS.md`](docs/ORIGINAL_VS_IOS_ANALYSIS.md) for the original UI/resource/performance mechanisms and the iOS gap analysis.
- [`docs/IMPLEMENTATION_AUDIT.md`](docs/IMPLEMENTATION_AUDIT.md) for current defects and concrete repair plans.
- [`docs/current/UNDERSTANDING.md`](docs/current/UNDERSTANDING.md) for the original architecture rationale.
- [`docs/current/TECHNICAL_DECISION.md`](docs/current/TECHNICAL_DECISION.md) for Swift parsing decisions.
