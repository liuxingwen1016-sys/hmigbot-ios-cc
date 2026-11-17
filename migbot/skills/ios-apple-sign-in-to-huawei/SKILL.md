---
name: ios-apple-sign-in-to-huawei
description: 迁移 iOS 的 Sign in with Apple 到 HarmonyOS。识别 SwiftUI、UIKit 或 Objective-C 的 Apple 登录入口与业务会话，在鸿蒙按已确认方案接入华为账号 Account Kit，保留旧用户登录或显式绑定路径。适用于 Apple ID 登录在转换中漏迁、需要华为账号替代或保留跨端账号的任务。不要用于通用微信、短信或其他第三方登录，使用对应的通用登录技能。
metadata:
  type: domain
  domain: migration
  source_platform: ios
  origin: hmigbot-ios
  tags: [ios, sign-in-with-apple, account-kit, identity, account-linking]
---

# Apple 登录迁移到鸿蒙

1. 核对源入口及所选 target。沿 SwiftUI `SignInWithAppleButton`、UIKit `ASAuthorizationAppleIDButton`、`ASAuthorizationAppleIDProvider` 或已配置 Apple OAuth 的实际调用追到回调、服务端请求、会话保存、绑定及取消/失败。识别结果带源码行和 AC。单独的 `AuthenticationServices` import、通用 OAuth、entitlement 和文案只用于定位。机器 `service` 信号仍需人工核对符号归属、可达性及登录或绑账号的用途。
2. 在已有 Spec/API 清单和功能任务中写明入口、用户可见状态、现有账号恢复路径、目标服务端契约和未决依赖。Plan 将本 Skill 写入对应任务的 `suggested_skills` 或 `suggested_skills+`。登录 UI、服务/会话与共享模块各由现有 owner 负责。
3. 当产品方案采用华为账号，使用 Account Kit 的**账号标识登录**。沿用现有应用会话入口。用服务端核验的华为身份登录或绑定同一个内部账号。已有 Apple 用户通过已配置的 Apple Web 登录、已验证的应用登录/恢复方式，或在已登录会话中显式绑定华为账号。产品应明确所选连续性方案。Apple 与华为凭据各自送到对应服务端契约，账号对应关系由服务端在完成验证后建立。
4. 按 [Account Kit 接线和验收](references/account-kit.md) 核对真实 SDK、应用配置、服务端和可执行测试。授权回调与应用会话成功分开。缺真实后端或旧用户恢复方式时，在原决策和发现记录保留该登录义务以及受影响的 AC。其他登录方式继续原有流程。

发布证据分别记录入口已实现、实际 HAP 编译、Account Kit 授权、应用会话和旧用户数据连续性。取消、重复点击、无授权码、服务端拒绝、绑定冲突均保持原会话边界和可用恢复入口。
