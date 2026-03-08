---
name: zueb-attendance-punch
description: 提交ZUEB员工打卡。当用户明确要求“帮我打卡”“现在打卡”“提交上班卡/下班卡”这类真实打卡操作时触发。该技能会执行实际提交，调用前必须先得到用户明确确认。
---

# ZUEB Attendance Punch

在执行真实打卡前，必须先确认两件事：

1. 用户明确要求现在执行真实打卡，而不是仅查询状态。
2. 用户已经明确确认可以提交。

未满足以上任一条件时，不要调用提交命令；先用自然语言再次确认。

## Run

自动判断应打上班卡还是下班卡：

```bash
.venv/bin/python bot/agent/helper.py attendance-punch --mode auto --confirm yes
```

显式提交上班卡：

```bash
.venv/bin/python bot/agent/helper.py attendance-punch --mode sbk --confirm yes
```

显式提交下班卡：

```bash
.venv/bin/python bot/agent/helper.py attendance-punch --mode xbk --confirm yes
```

如需覆盖默认坐标，可追加：

```bash
--xy "113.719755,34.615436"
```

## Presenting Results

- 先说明是否真的执行了提交：看 `executed`。
- 若 `executed` 为 `false`，直接解释原因，例如已打过卡、无需重复提交。
- 若 `executed` 为 `true`，展示 `mode_executed` 与 `message`。
- 可简要带上 `attendance_before` 里的上下班卡状态。
- 不要回显任何 token、签名或敏感字段。
