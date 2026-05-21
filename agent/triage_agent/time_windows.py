from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .models import RegressionStatus, TimeRules, TimeWindow


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":", maxsplit=1)
    return time(hour=int(hour), minute=int(minute))


def cit_morning_window(report_date: date, rules: TimeRules) -> TimeWindow:
    tz = ZoneInfo(rules.timezone)
    start_time = _parse_hhmm(rules.cit.start_time)
    end_time = _parse_hhmm(rules.cit.end_time)

    start_day = report_date - timedelta(days=1)
    start = datetime.combine(start_day, start_time, tzinfo=tz)
    end = datetime.combine(report_date, end_time, tzinfo=tz)

    return TimeWindow(
        name=f"CIT morning {report_date.isoformat()}",
        start=start,
        end=end,
        display_label=f"{start:%Y-%m-%d %H:%M} ~ {end:%Y-%m-%d %H:%M}",
    )


def _fb_number(fb_code: str) -> int:
    normalized = fb_code.strip().upper()
    if not normalized.startswith("FB"):
        raise ValueError(f"Invalid FB code: {fb_code}")
    return int(normalized.removeprefix("FB"))


def fb_window(fb_code: str, rules: TimeRules) -> TimeWindow:
    tz = ZoneInfo(rules.timezone)
    target_fb = _fb_number(fb_code)
    anchor_fb = _fb_number(rules.crt.anchor_fb)
    anchor_start = date.fromisoformat(rules.crt.anchor_start_date)

    offset_days = (target_fb - anchor_fb) * rules.crt.duration_days
    start_day = anchor_start + timedelta(days=offset_days)
    end_exclusive_day = start_day + timedelta(days=rules.crt.duration_days)
    end_display_day = end_exclusive_day - timedelta(days=1)

    return TimeWindow(
        name=fb_code.upper(),
        start=datetime.combine(start_day, time.min, tzinfo=tz),
        end=datetime.combine(end_exclusive_day, time.min, tzinfo=tz),
        display_label=f"{fb_code.upper()} ({start_day.isoformat()} ~ {end_display_day.isoformat()})",
    )


def current_fb_for_date(day: date, rules: TimeRules) -> str:
    anchor_fb = _fb_number(rules.crt.anchor_fb)
    anchor_start = date.fromisoformat(rules.crt.anchor_start_date)
    delta_days = (day - anchor_start).days

    # Python floor division handles dates before the anchor correctly.
    fb_offset = delta_days // rules.crt.duration_days
    return f"FB{anchor_fb + fb_offset}"


def scope_window(
    regression_status: RegressionStatus,
    report_date: date,
    rules: TimeRules,
) -> TimeWindow:
    if regression_status is RegressionStatus.CIT:
        return cit_morning_window(report_date=report_date, rules=rules)

    current_fb = current_fb_for_date(day=report_date, rules=rules)
    return fb_window(fb_code=current_fb, rules=rules)
