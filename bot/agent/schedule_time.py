"""Schedule staggered-time mapping helpers for Claude Skills.

根据课程地点映射错峰批次，再根据节次给出具体上课时间。
该模块仅做数据增强，不修改原始课表字段语义。
"""

from __future__ import annotations

import re
from typing import Any

_WEEK_KEYS = tuple(f"week{i}" for i in range(1, 8))

_BATCH_LABELS = {
    1: "第一批次",
    2: "第二批次",
    3: "第三批次",
    4: "第四批次",
}

_BATCH_LOCATION_KEYWORDS = {
    1: (
        "1#实验楼",
        "1号实验楼",
        "2#教学楼",
        "2号教学楼",
        "3#行政楼",
        "3号行政楼",
        "4#实验楼",
        "4号实验楼",
        "工程训练中心",
    ),
    2: (
        "5#实验楼",
        "5号实验楼",
        "6#教学楼",
        "6号教学楼",
        "13#教学楼",
        "13号教学楼",
    ),
    3: (
        "7#教学楼",
        "7号教学楼",
        "8#教学楼",
        "8号教学楼",
    ),
    4: (
        "10#教学楼",
        "10号教学楼",
        "11#教学楼",
        "11号教学楼",
        "12#教学楼",
        "12号教学楼",
    ),
}

# 节次 -> (开始, 结束)，除第3/4小节外各批次一致。
_BASE_PERIOD_TIME = {
    1: ("08:00", "08:45"),
    2: ("08:55", "09:40"),
    5: ("14:00", "14:45"),
    6: ("14:55", "15:40"),
    7: ("16:00", "16:45"),
    8: ("16:55", "17:40"),
    9: ("18:20", "19:05"),
    10: ("19:15", "20:00"),
    11: ("12:20", "13:05"),  # 部分系统可能用 11/12 表示中午两节
    12: ("13:05", "13:50"),
    101: ("12:20", "13:05"),  # 中午第一小节
    102: ("13:05", "13:50"),  # 中午第二小节
}

_PERIOD_TIME_BY_BATCH = {
    1: {
        **_BASE_PERIOD_TIME,
        3: ("10:00", "10:45"),
        4: ("10:55", "11:40"),
    },
    2: {
        **_BASE_PERIOD_TIME,
        3: ("10:10", "10:55"),
        4: ("11:05", "11:50"),
    },
    3: {
        **_BASE_PERIOD_TIME,
        3: ("10:20", "11:05"),
        4: ("11:15", "12:00"),
    },
    4: {
        **_BASE_PERIOD_TIME,
        3: ("10:30", "11:15"),
        4: ("11:25", "12:10"),
    },
}


def _normalize_text(text: str) -> str:
    return (
        (text or "")
        .replace("＃", "#")
        .replace("：", ":")
        .replace("－", "-")
        .replace("—", "-")
        .replace("–", "-")
        .replace("到", "-")
        .replace("~", "-")
    )


def _normalize_location(text: str) -> str:
    normalized = _normalize_text(text)
    normalized = re.sub(r"(\d+)\s*号", r"\1#", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def _detect_batch_from_location(location: str) -> tuple[int | None, str]:
    normalized = _normalize_location(location)
    if not normalized:
        return None, ""

    for batch, keywords in _BATCH_LOCATION_KEYWORDS.items():
        for keyword in keywords:
            marker = _normalize_location(keyword)
            if marker and marker in normalized:
                return batch, keyword
    return None, ""


def _append_unique(target: list[int], value: int) -> None:
    if value not in target:
        target.append(value)


def _parse_period_codes(jcxx: str) -> list[int]:
    text = _normalize_text(jcxx)
    if not text:
        return []

    period_codes: list[int] = []

    # 兼容“中午第一/第二小节”文字标记。
    if "中午第一" in text:
        _append_unique(period_codes, 101)
    if "中午第二" in text:
        _append_unique(period_codes, 102)

    segments = re.split(r"[，,、;；/ ]+", text)
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        range_match = re.search(r"(\d+)\s*-\s*(\d+)", segment)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            if start <= end:
                for value in range(start, end + 1):
                    _append_unique(period_codes, value)
            else:
                for value in range(end, start + 1):
                    _append_unique(period_codes, value)
            continue

        for match in re.finditer(r"\d+", segment):
            _append_unique(period_codes, int(match.group(0)))

    return sorted(period_codes)


def _period_label(period_code: int) -> str:
    if period_code in {11, 101}:
        return "中午第一小节"
    if period_code in {12, 102}:
        return "中午第二小节"
    return f"第{period_code}小节"


def _resolve_period_times(period_codes: list[int], batch: int | None) -> list[dict[str, Any]]:
    if batch is None:
        return []

    table = _PERIOD_TIME_BY_BATCH.get(batch, {})
    resolved: list[dict[str, Any]] = []
    for period_code in period_codes:
        timerange = table.get(period_code)
        if not timerange:
            continue
        start, end = timerange
        resolved.append(
            {
                "period_code": period_code,
                "period_label": _period_label(period_code),
                "start_time": start,
                "end_time": end,
                "time_range": f"{start}-{end}",
            }
        )
    return resolved


def _build_course_time_info(course: dict[str, Any]) -> dict[str, Any]:
    location = str(course.get("skdd") or "")
    periods_text = str(course.get("jcxx") or "")
    batch, matched_location = _detect_batch_from_location(location)
    period_codes = _parse_period_codes(periods_text)
    period_times = _resolve_period_times(period_codes, batch)

    time_range = ""
    if period_times:
        time_range = f"{period_times[0]['start_time']}-{period_times[-1]['end_time']}"

    return {
        "staggered_batch": batch,
        "staggered_batch_label": _BATCH_LABELS.get(batch, ""),
        "staggered_location_keyword": matched_location,
        "staggered_period_codes": period_codes,
        "staggered_period_times": period_times,
        "staggered_time_range": time_range,
        "staggered_time_available": bool(period_times),
    }


def enrich_schedule_with_staggered_times(schedule: dict[str, Any]) -> dict[str, Any]:
    """Return a schedule copy with staggered-time fields appended per course item."""
    if not isinstance(schedule, dict):
        return {}

    enriched = dict(schedule)
    for week_key in _WEEK_KEYS:
        courses = schedule.get(week_key)
        if not isinstance(courses, list):
            continue

        enriched_courses: list[Any] = []
        for item in courses:
            if not isinstance(item, dict):
                enriched_courses.append(item)
                continue

            course = dict(item)
            course.update(_build_course_time_info(course))
            enriched_courses.append(course)

        enriched[week_key] = enriched_courses

    return enriched
