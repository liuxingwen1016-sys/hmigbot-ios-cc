# MigBot User Experience Improvement Plan

The MigBot (迁移精灵) Team (hereinafter "the Team" or "the Operator"), as the operator of the MigBot (迁移精灵) software (hereinafter "the Product"), hereby presents this User Experience Improvement Plan to you (hereinafter "you" or "the User"). This Plan aims to continuously improve AI migration effectiveness and product quality by collecting work-process artifacts generated during migration, providing you with a more stable and efficient experience.

Please read this Plan carefully and in its entirety before deciding whether to participate. Upon consenting to participate, you shall be deemed to have read, understood, and accepted all terms of this Plan. You have the right to withdraw at any time (withdrawing disables the Product's migration functionality); the methods are set forth in **Article 6, Clause 2**.

> **Important: participation in this Plan is a precondition for using the Product (binary).**
> - **Participate** (`telemetry_consent: "granted"`): the Product is **usable** and uploads all of categories (i)–(v) in Article 2.
> - **Decline** (any other state, including `/a2h-privacy deny`, `/a2h-privacy off`, `A2H_TELEMETRY_OFF=1`): the Product's **migration pipeline is disabled** (it refuses to run from `/a2h-spec` onward) and **nothing is uploaded**.
>
> In other words, **declining disables the Product**. Participation is your choice, but if you decline, the Product's migration functionality is unavailable and no data is collected or uploaded. The upload content, purpose, and de-identification are governed by this Plan.

---

**Article 1  Operator and Contact Information**

1.1 Operating entity: The MigBot (迁移精灵) Team

1.2 UX-dedicated email: migbot_uxfeedback@163.com

---

**Article 2  What Participation Involves**

2.1 This Plan does not actively collect personal information. Please note, however, that the category (v) migration-session slices of Article 2 may contain content you yourself enter during a session — **please avoid entering personal or sensitive information in the session**.

The Product collects and uploads **only while you participate** (`granted`); if you decline, the Product is disabled and collects nothing. When you participate, what is uploaded and when:

-  (i) **lines-of-code statistics** + application names: the Android-side line counts and app name are uploaded when you complete project initialization via `/a2h-init`; the HarmonyOS side is completed at the `a2h-verify` stage together with the migration-completion signal.
-  (ii) **stage progress marks** and the **precise token-usage snapshot**: uploaded per stage as each migration stage (`a2h-init` / `a2h-build` / `a2h-spec` / `a2h-plan` / `a2h-execute` / `a2h-verify` / `a2h-retrospect`) completes.
-  (iii) **migration reports**: uploaded as the `a2h-retrospect` stage (retrospect report) and each incremental-migration phase (increment report) completes.
-  (iv) **migration-session slices**: uploaded incrementally and continuously while a migration session is in progress.

To support the above and to let you request deletion later, the Product generates an install identifier (`migbot_session_id`) at `/a2h-init` and sends it with every upload; it serves as a deletion handle and for activity de-duplication. The Product performs no collection or upload beyond the scope listed in this Article.

2.2 Work-Process Artifacts Uploaded Upon Participation

The data uploaded by the Product comprises the following five categories and is **strictly limited** to these five categories:

(i) Lines-of-code statistics (`code-lines.json`): lines of code grouped by file extension for the Android and HarmonyOS sides; project name and application name;

(ii) Stage progress marks (`stage-marks`): start / completion timestamps of each pipeline stage, used for stage attribution and migration-completion determination;

(iii) Migration reports (`docs/retrospect-report-*.md`, `docs/increment-report-phase-*.md`, bundled with the upload): the migration-quality retrospect report produced by the `a2h-retrospect` stage and the incremental-migration phase reports — skill coverage, compile-error patterns, API corrections, confidence accuracy and other migration-process statistics and reflections; the report files themselves contain **no** source code or migration intermediate artifacts;

(iv) Precise token-usage snapshot (`usage-v2/<session>.json`): per-skill and per-sub-agent token counts (input / output / cache), broken down by model, for a migration session — the snapshot file contains skill and sub-agent names and token counts **only**. It is captured **locally only** by the hooks at the end of each session turn, and uploaded **per stage** as each migration stage completes;

(v) Migration-session slices (`session-slice`): You can interact with the Product in a variety of formats, including but not limited to conversational instructions, coding, and agentic sessions in which the AI coding assistant performs multi-step migration tasks on your behalf. The content you submit to the Product through these interactions constitutes your "Inputs"; Inputs generate responses and actions ("Outputs"), such as creating or modifying project files or running build commands on your behalf. Inputs and Outputs are uploaded as incremental slices. If you include personal information or reference external content in your Inputs, we will collect that information, and it may be reproduced in your Outputs.

When you provide Inputs — including by uploading files, granting the Product permission to access third-party services, or instructing the Product to retrieve information or take actions based on information — you are responsible for ensuring that you have the necessary rights, permissions, or authorizations to do so.

All five categories are **work-process artifacts** — files and statistics automatically generated or recorded during the migration pipeline. Category (v) may contain your project's source code and session content; please make sure you understand this before deciding to participate.

---

**Article 3  Purpose of Work-Process Artifact Use**

The Team collects the work-process artifacts set forth in Article 2 **solely** for the following purposes:

(i) Evaluating and improving AI migration effectiveness, identifying frequently failing code patterns, and expanding the skill knowledge base;

(ii) Reproducing and fixing product defects (bugs) reported by users;

(iii) Monitoring product health, including error rates and performance bottlenecks.

---

**Article 4  De-identification**

4.1 For categories (i)–(iv), the Product sanitises data twice: once before it leaves your machine, and once before persistence on the server side. Category (v) migration-session slices are uploaded **verbatim** without client-side sanitisation; their storage and access control are governed by Article 5.

4.2 Client-side sanitisation (applies to categories (i)–(iv)): local absolute paths (e.g. `/Users/<your-username>/`, `C:\Users\<your-username>\`) are stripped and replaced with `~`; git committer emails are stripped; no identity fields are collected.

4.3 Server-side handling: business statistics use only project-level identifiers (project name, application name); the source IP is used for risk control (rate limiting and blocklisting), per-user data isolation, and activity statistics, and is not used to identify you as a natural person.

4.4 The Team does not use the above data to identify or link to any specific natural person. Category (v) migration-session slices may contain information you actively enter during a session; access to them is strictly governed by the access control and auditing of Article 5, Clause 3.

---

**Article 5  Data Storage and Security**

5.1 Storage Location

All work-process artifacts collected by the Product are stored on servers physically located within the mainland of the People's Republic of China. Data is encrypted end-to-end (SSL/TLS) during transit; the server side likewise applies corresponding security encryption and storage-protection measures, with SHA-256 integrity verification on every file.

5.2 Encryption and Anti-leak Measures

(i) Data transport uses HTTPS, with TLS terminated at the Nginx front door;

(ii) All operations actions (data export, deletion, blocklist changes) are recorded in an audit log.

5.3 Access Control

Only **operators and core engineering staff** of the Team may access raw data. All access actions are recorded in the audit log and are fully traceable.

5.4 Retention Periods

(i) Raw data (including the migration retrospect report and detailed metrics): retained for **no longer than 12 months**; purged or anonymously aggregated by background tasks upon expiry;

(ii) Anonymised aggregated statistics (weekly/monthly aggregates of lines of code, token consumption trends, etc., containing no original text): may be retained long-term, used solely for product trend analysis, containing no fields linkable to a specific project;

(iii) Upon your withdrawal from this Plan: the Team shall delete, within **30 business days** of receipt of your withdrawal, all raw data linkable to your local project (matched by project name); anonymised aggregated statistics already produced are not subject to deletion as they cannot be reverse-attributed.

5.5 Should you require a shorter retention period or expedited deletion, please contact the Team via the methods set forth in **Article 8**.

---

**Article 6  Your Rights**

6.1 Right of Access and Copy

Your local `.migbot/metrics/` directory retains local copies of uploaded artifacts. You may inspect them at any time:

```
ls .migbot/metrics/
ls .migbot/metrics/usage-v2/                     # per-session token snapshots and .stage-marks.json
ls .migbot/metrics/<run_id>/facts/               # structured statistics (incl. stage marks)
tar -tzf .migbot/metrics/<project>/spec-*.tar.gz # migration report bundle (only if an upload was triggered)
```

Category (v) migration-session slices are taken from the session-record files (`.jsonl`) that the AI coding assistant keeps on your machine — what is uploaded are byte ranges of those files. You may inspect the files directly on your machine, and query your participation state via `/a2h-privacy status`.

If the Team has deployed the MigBot (迁移精灵) data dashboard service, you may log in to inspect all upload records related to your projects and export the raw data.

6.2 Right to Withdraw

You may withdraw at any time. **Withdrawing disables the Product's migration functionality** and uploads nothing thereafter:

(i) Execute `/a2h-privacy deny` (or `/a2h-privacy off`), or manually change `"telemetry_consent"` in `.migbot/config.json` to `"denied"` (or `"off"`). The change takes effect immediately upon save.

(ii) **One-shot withdrawal**: before running a command, set the environment variable `A2H_TELEMETRY_OFF=1` (effective only for the current process; does not modify persistent configuration).

To use the Product again after withdrawing, re-participate per Article 6, Clause 4.

6.3 Right of Deletion

The preceding methods only stop future uploads. To request deletion of historical data already uploaded to the server, please submit a deletion request to the Team via the contact methods in **Article 8**. The Team shall process such requests within 7 business days of receipt.

6.4 Right to Re-participate

You may re-join this Plan at any time by executing `/a2h-privacy accept` or by reverting the `telemetry_consent` field in the configuration to `"granted"`.

6.5 Right to Query Status

You may query the current participation state and the timestamp of the last change via `/a2h-privacy status`.

---

**Article 7  Plan Changes**

7.1 This Plan takes **effect** on 5 June 2026.

7.2 This Plan ships with each MigBot (迁移精灵) client release. The currently effective version always resides at `.migbot/policies/user-experience-improvement-plan.en.md` within the installed client.

7.3 When this Plan undergoes a **material change** (including but not limited to: new work-process artifact categories collected, changed collection purposes, changed storage location, changed operating entity), the new client version shall **re-request** your consent during the `/a2h-init` flow; your prior consent shall automatically become void.

7.4 Non-material changes (including but not limited to: wording revisions, typo fixes, formatting adjustments) shall not trigger re-consent.

---

**Article 8  Contact Information and Dispute Resolution**

8.1 Contact Information

UX-dedicated email: migbot_uxfeedback@163.com

The Team shall respond within 7 business days of receipt of your feedback.

8.2 Dispute Resolution

Any dispute arising from or in connection with this Plan shall first be resolved through friendly negotiation between the parties; if negotiation fails, either party may bring suit in a competent People's Court.

The conclusion, validity, interpretation, performance, and dispute resolution of this Plan shall be governed by the laws of the People's Republic of China.

---

**Article 9  Supplementary Provisions**

9.1 Your participation is entirely voluntary. However, note that **participation in this Plan is a precondition for using MigBot (迁移精灵)'s migration functionality** — if you decline or withdraw, the Product's migration pipeline (from `/a2h-spec` onward) is disabled and no data is collected or uploaded. You may re-participate at any time via `/a2h-privacy accept` to enable the Product.

9.2 This Plan becomes effective for you upon your explicit expression of consent in the `/a2h-init` flow.

9.3 The Chinese and English versions of this Plan have equal effect; in case of discrepancy, the Chinese version shall prevail.

9.4 If any portion of any clause of this Plan is deemed invalid or unenforceable, the validity of the remaining portions shall not be affected.

9.5 Matters not covered herein shall be handled in accordance with the Personal Information Protection Law of the People's Republic of China, the Data Security Law of the People's Republic of China, the Cybersecurity Law of the People's Republic of China, and other relevant laws and regulations.

---

Version: v2.1.1

Effective: 5 June 2026