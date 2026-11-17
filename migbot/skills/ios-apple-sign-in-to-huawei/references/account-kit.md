<!-- when: 已确认华为账号方案，需要实现或验收 Account Kit 接线 -->
<!-- topics: account-kit, account-linking, runtime-evidence -->
# 华为账号接线与验收

## 实施前读取

核对目标 Stage 模型、产品 bundleName、签名指纹、AppGallery Connect 应用与 Account Kit 开通配置，以及 compile/compatible SDK 实际声明。按应用自己的能力开通记录和配置文件处理；服务端密钥留在后端。确认服务端能够接受华为授权码并发行现有应用会话。如果服务端当前只接受 Apple token，保留对应集成依赖和已有恢复方式。

## 客户端

使用当前 SDK 的 `@kit.AccountKit`。有官方组件时，以 `LoginWithHuaweiIDButton` 和 `loginComponentManager.LoginType.ID` 展示华为账号登录入口。用 `LoginWithHuaweiIDButtonController.onClickLoginWithHuaweiIDButton` 取得授权结果，由 owner 把 `HuaweiIDCredential.authorizationCode` 传给已确认的应用服务端客户端。只有组件不适用且产品的交互方案允许时，按实际 SDK 选择 `authentication.HuaweiIDProvider.createLoginWithHuaweiIDRequest` 与 `authentication.AuthenticationController.executeRequest` 路径。在支持的产品与设备分支创建组件。由父级在创建前检查 `canIUse("SystemCapability.AuthenticationServices.HuaweiID.UIComponent")`，能力缺失时展示已配置的其他登录或恢复入口。手机号一键登录的 scope、额外授权和区域适用性属于另外的产品路径。

可复用 [华为账号按钮组件](HuaweiIdSignIn.ets)。父组件实现其回调，在发送授权码前同步置 `busy`，从已核验的会话客户端回调恢复状态，并消费错误码和缺授权码分支。组件保持现有登录页、会话和路由的责任边界。

请求期间避免重复发起。用户取消返回登录页或原绑定页，保留已有会话。授权码缺失、环境配置错误、网络错误和后端拒绝分别走已有错误处理。只有现有服务端确认后才保存应用会话、刷新用户态和跳转。遵循所选 SDK 的错误枚举或官方错误码。日志只记脱敏分支和诊断码。

## 服务端与旧用户

- 用华为授权码完成服务端交换，核验返回身份和当前应用、签发方及请求上下文。按华为规则选择适用的 UnionID 或 OpenID 作用域。凭据有效期和防重放由服务端处理。
- 将 Apple 与 Huawei 作为不同的身份提供方。各自保留已验证的作用域与 subject，关联到稳定的内部用户 ID。邮箱、昵称或手机号相同的情况进入已验证的登录/恢复或绑定流程。
- 已登录用户的绑定要求用户主动确认、验证新的华为凭据，并原子地检查唯一绑定。已有归属冲突、取消和后端拒绝保持原用户与数据关系。新注册仅沿已确认的产品策略执行。
- 保留 Apple Web 登录时，按 Apple 官方配置核对主 App ID、Services ID、回调和服务端校验。现有 Apple 用户能否登录同一个应用账号，使用已知测试账号核验实际映射与数据。
- 最小验收场景包括成功发业务会话、授权取消、重复点击、缺授权码、网络/后端失败、旧 Apple 用户恢复和显式绑定、重复/冲突绑定。将 SDK 回调、会话结果和同一内部账号的数据证据分别记录。

依据见 [Apple 原生登录](https://developer.apple.com/documentation/authenticationservices/implementing-user-authentication-with-sign-in-with-apple)、[Apple 身份凭据](https://developer.apple.com/documentation/signinwithapple/receiving-a-users-identity-token)、[Apple 跨平台配置](https://developer.apple.com/documentation/signinwithapple/configuring-your-environment-for-sign-in-with-apple)、[华为账号按钮与服务端接线](https://developer.huawei.com/consumer/en/doc/harmonyos-guides/account-unionid-login-button/) 和 [Account Kit API](https://developer.huawei.com/consumer/cn/doc/harmonyos-references/account-api-authentication/)。
