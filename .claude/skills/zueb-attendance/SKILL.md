---
name: zueb-attendance
description: 查询今日打卡考勤状态。当用户问“打卡了吗”“今天是否已打卡”“查询考勤”“上班卡/下班卡状态”这类只读问题时触发。仅用于查询，不执行真实打卡提交。
---

# ZUEB Attendance

Run the helper script to check today's attendance:

```bash
.venv/bin/python bot/agent/helper.py attendance
```

## Presenting Results

Parse the JSON output. The attendance data contains:
- `sbk_time`: clock-in time (e.g. `08:30`) or empty if not punched
- `xbk_time`: clock-out time (e.g. `17:30`) or empty if not punched
- `sbk_done`: true if clocked in
- `xbk_done`: true if clocked out
- `all_done`: true if both done

Present clearly:
- If not clocked in yet, remind the user.
- If clocked in but not out, show clock-in time and remind about clock-out.
- If both done, confirm with times.
- If the user actually wants you to execute a real punch, switch to `zueb-attendance-punch` instead of using this skill.
