---
name: zueb-schedule
description: 查询ZUEB课表和课程安排。当用户问课表、上课时间、第几节课、教室在哪、本周或下周有什么课时触发。需要按地点批次和节次给出具体上课时间。
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

## Input JSON Fields

- `week1-7`: Monday to Sunday course arrays.
- Each course item usually includes:
  - `kcmc`: course name
  - `skdd`: location
  - `rkjs`: teacher
  - `jcxx`: period text (e.g. `3-4节`)
  - `skzs`: teaching week range
- `zc`: current week number, `xn`: year, `xq`: term.

## Staggered-Time Rules (Skill-side Only)

You must infer concrete class time from `skdd` (location) and `jcxx` (periods). See [TIME_TABLE.md](TIME_TABLE.md) for batch-location mapping and period-time matrix.

## Presenting Results

- Group by weekday and omit empty days.
- For each course, include at least: course name, location, `jcxx`, inferred concrete time.
- Keep response concise for Telegram.
- If no classes, explicitly say that week/day has no classes.
