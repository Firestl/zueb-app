# Frida 抓包脚本

包名：`com.supwisdom.zueb`
脚本：`GradleProject/frida/zueb_net_trace.js`

## 功能

- 绕过常见 TLS 校验与 pinning
- 记录 `okhttp3` / `dc.squareup.okhttp3` 请求与响应
- 记录 `WebView.loadUrl`、`postUrl`、`addJavascriptInterface`
- 记录 `CookieManager.setCookie`
- 记录 `URL.openConnection` 与请求头

默认忽略 `umeng.com`、`gepush.com`、`getui.com` 噪音流量。

## 启动

```bash
frida -U -f com.supwisdom.zueb -l GradleProject/frida/zueb_net_trace.js
```

已启动应用时可直接附加：

```bash
frida -U -n com.supwisdom.zueb -l GradleProject/frida/zueb_net_trace.js
```

## 重点事件

- `okhttp_request` / `okhttp_response`
- `webview_load` / `webview_post`
- `cookie_set`
- `urlconnection_open` / `urlconnection_header`
- `ssl_bypass`

## 常用过滤

只看请求 URL：

```bash
frida -U -f com.supwisdom.zueb -l GradleProject/frida/zueb_net_trace.js --no-pause | jq -r 'select(.event=="okhttp_request") | .payload.method + " " + .payload.url'
```

只看 WebView 跳转：

```bash
frida -U -f com.supwisdom.zueb -l GradleProject/frida/zueb_net_trace.js --no-pause | jq -r 'select(.event=="webview_load") | .payload.url'
```
