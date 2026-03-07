---
name: wol
description: 远程唤醒台式电脑（Wake-on-LAN）。当用户说开机、唤醒电脑、开电脑、远程开机、WOL、打开台式机、启动电脑时触发。通过SSH连接路由器发送魔术包。
---

# WOL (Wake-on-LAN)

通过 SSH 连接 OpenWrt 路由器，发送 WOL 魔术包唤醒台式电脑。

```bash
.venv/bin/python bot/agent/helper.py wol
```

## Presenting Results

- Parse the JSON output.
- Success: tell user the wake packet has been sent, desktop should boot in ~30 seconds.
- Failure: show the error message and suggest checking router connectivity.
- Note: WOL only sends the magic packet — it cannot confirm the PC actually powered on.
