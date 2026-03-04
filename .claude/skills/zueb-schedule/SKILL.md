---
name: zueb-schedule
description: 查询ZUEB课表。当用户问课表、课程安排、本周或下周有什么课时触发。
---

# ZUEB Schedule

Run the helper script to query the course schedule:

```bash
.venv/bin/python bot/agent/helper.py schedule [OPTIONS]
```

## Options

| Flag | Description |
|------|-------------|
| `--semester CODE` | Semester code, e.g. `20250` |
| `--year N` | Academic year start, e.g. `2025` |
| `--term 1\|2` | Term number (1 = first, 2 = second) |
| `--week N` | Week number |
| `--list` | List available semesters instead of schedule |

## Usage

- Default (no options): returns current week schedule.
- If the user asks about a specific week (e.g. "下周课表"), calculate the week number and pass `--week`.
- If the user asks to list semesters, use `--list`.
- `--year` and `--term` must be used together.

## JSON Fields

- `schedule`: 原始教务课表数据（兼容旧逻辑）。
- `schedule_with_staggered_time`: 增强后的课表数据。`week1-7` 中每个课程会新增：
  - `staggered_batch`: 错峰批次（1~4）
  - `staggered_batch_label`: 批次名称（如“第二批次”）
  - `staggered_location_keyword`: 匹配到的地点关键字
  - `staggered_period_times`: 节次明细时间数组
  - `staggered_time_range`: 该课程整体时间段（如 `10:10-11:50`）
  - `staggered_time_available`: 是否成功匹配

## Presenting Results

1. 优先使用 `schedule_with_staggered_time`，按天分组展示课程。
2. 每门课至少展示：课程名、地点、节次、具体上课时间（`staggered_time_range`）。
3. 若 `staggered_time_available=true`，同时可补充批次（`staggered_batch_label`）。
4. 若 `staggered_time_available=false`，说明“地点未匹配错峰表，暂无法给出精确时间”，并继续展示原节次。
5. 忽略无课日期。

## Location-To-Batch Rules

- 第一批次：`1#实验楼`、`2#教学楼`、`3#行政楼`、`4#实验楼`、`工程训练中心`
- 第二批次：`5#实验楼`、`6#教学楼`、`13#教学楼`
- 第三批次：`7#教学楼`、`8#教学楼`
- 第四批次：`10#教学楼`、`11#教学楼`、`12#教学楼`

说明：第 1/2/5/6/7/8/9/10 小节各批次时间一致；核心差异在第 3/4 小节，必须按批次使用增强字段中的精确时间。
