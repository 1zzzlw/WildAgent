from datetime import datetime

import pytest

from app.domain.usage import next_reset_at


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        ("2026-11-16T15:59:59.999+00:00", "2026-11-16T16:00:00+00:00"),
        ("2026-11-16T16:00:00+00:00", "2026-11-17T16:00:00+00:00"),
        ("2026-11-30T16:00:00+00:00", "2026-12-01T16:00:00+00:00"),
        ("2026-12-31T16:00:00+00:00", "2027-01-01T16:00:00+00:00"),
    ],
)
def test_daily_quota_uses_beijing_midnight(current, expected):
    timestamp = int(datetime.fromisoformat(current).timestamp() * 1000)
    assert next_reset_at(timestamp) == int(datetime.fromisoformat(expected).timestamp() * 1000)
