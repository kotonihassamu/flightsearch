"""週末日付算出のテスト（要件6.1）。"""

from __future__ import annotations

from datetime import date

import pytest

from flightdeal import weekend



@pytest.mark.parametrize(
    "today,expected",
    [
        (date(2026, 7, 31), date(2026, 8, 1)),   # 金曜 -> 翌日
        (date(2026, 8, 1), date(2026, 8, 8)),    # 土曜 -> 当日を含めず翌週
        (date(2026, 8, 2), date(2026, 8, 8)),    # 日曜 -> 6日後
        (date(2026, 7, 27), date(2026, 8, 1)),   # 月曜
    ],
)
def test_next_saturday(today, expected):
    assert weekend.next_saturday(today) == expected


def test_target_weekends_phase1():
    ws = weekend.target_weekends(date(2026, 7, 27), weekends_ahead=1)
    assert len(ws) == 1
    assert ws[0].saturday == date(2026, 8, 1)
    assert ws[0].sunday == date(2026, 8, 2)
    assert ws[0].index == 1


def test_target_weekends_phase3():
    ws = weekend.target_weekends(date(2026, 7, 27), weekends_ahead=2)
    assert [w.saturday for w in ws] == [date(2026, 8, 1), date(2026, 8, 8)]
    assert [w.index for w in ws] == [1, 2]
