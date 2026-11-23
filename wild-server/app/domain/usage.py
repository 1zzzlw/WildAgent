"""每日使用额度的业务定义，按北京时间零点更新。"""

from datetime import datetime, time, timedelta, timezone

DEFAULT_DAILY_LIMITS = {"operations": 20, "ai": 5}
USAGE_LABELS = {"operations": "手工操作", "ai": "AI 使用"}
QUOTA_TIMEZONE = timezone(timedelta(hours=8))


def next_reset_at(timestamp_ms: int) -> int:
    current = datetime.fromtimestamp(timestamp_ms / 1000, tz=QUOTA_TIMEZONE)
    tomorrow = current.date() + timedelta(days=1)
    midnight = datetime.combine(tomorrow, time.min, tzinfo=QUOTA_TIMEZONE)
    return int(midnight.timestamp() * 1000)
