# Project Overview
- Focus on `GradleProject/src/main/java/com/supwisdom/superapp`
- This is a single-module Android app (`applicationId`: `com.supwisdom.zueb`)
- Core style: native shell + H5/WebView + UniMP/Weex bridge

## Architecture Summary
- `WXApplication`: global runtime entry; initializes SDKs, push, UniMP, network, WeChat/WeCom, update flow
- `WXBaseActivity`: shared activity base for UI, lifecycle, permissions, common behavior
- `MainActivity`: startup router; handles privacy, version check, permissions, deeplink, login state, then routes onward
- `H5Activity` / `NewWindowActivity` / `CommonWebViewActivity`: main business containers for H5 pages, uploads/downloads, scan, JS bridge, new windows
- `WXPageActivity`: Weex page container
- `SuperAppModule` + `WXApplication`: native capability bridge exposed to front-end/UniMP
- Main business flow is container-driven: `MainActivity` routes, `WXBaseActivity.openMini()` opens UniMP, and many features ultimately land in H5/WebView or UniMP rather than native screens

## Business Modules
- Login & federated auth: `LoginActivity`, `WXEntryActivity`, `DDShareActivity`
- Account & security: bind phone/third-party, verification, password reset, secure certification, profile completion
- Campus features: pay code, offline code, service evaluation, wake-up/voice, file open
- Background services: `GetuiIntentService`, `GeTuiPushService`, `LiveService`, `UpdateService`

## Code Reading Priority
1. `WXApplication`
2. `MainActivity`
3. `LoginActivity`
4. `H5Activity`
5. `NewWindowActivity`
6. `SuperAppModule`

## Scope Guidance
- Treat `com.supwisdom.superapp` as the readable business shell layer
- Treat `supwisdom.*` as internal core/obfuscated support layer unless a task explicitly requires drilling deeper
- Ignore third-party packages unless they directly affect a business path

## Key Findings
- Highest-value audit surfaces: `H5Activity`, `NewWindowActivity`, `SuperAppModule`, `WXApplication`
- `H5Activity` / `NewWindowActivity` are the main trust boundaries: they accept `Intent` data, inject token into header/query/url, expose `addJavascriptInterface("Android")`, and dispatch native actions from WebView/JS
- Web containers explicitly ignore client certificate checks and proceed on SSL errors; keep this in mind when tracing exploitable request paths
- `WXApplication` exposes sensitive bridge methods such as user token, chat token, open file, host switch, and mini-program navigation
- `MainActivity` and `WXBaseActivity.openMini()` preserve external `VIEW` / deeplink input into later H5 or UniMP flow
- `WXEntryActivity` is the federated-login callback hub for bind/login/platform/federated-code branches
- Several feature gates read hardcoded JSON such as `{"openHijacking":false}`; verify whether those checks are effectively active or dead code

## Goal
The current Gradle project is an Android app for an academic affairs system that I developed. A CLI tool has also been developed to simplify GUI operations. As a penetration testing expert, you possess a unique perspective on auditing the current project's code and identifying exploitable paths. I will optimize the code based on your findings; you focus on proposing penetration routes without providing fixes.
