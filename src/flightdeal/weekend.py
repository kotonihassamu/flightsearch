"""週末日付の算出（要件3.1「対象日程」）。

純粋関数として実装し、pytest で境界値を検証する（要件6.1）。

仕様:
  - 実行日を基準に、次に到来する土曜日を「第1週末」とする
  - 実行日が土曜の場合は当日を含めず、翌週土曜を第1週末とする
  - 日曜は第1週末の土曜の翌日
  - 第2週末は第1週末の7日後
"""

from __future__ import annotations

from datetime import date, timedelta

from .models import WeekendDates

SATURDAY = 5  # date.weekday(): Mon=0 ... Sat=5, Sun=6


def next_saturday(today: date) -> date:
    """today を基準にした「第1週末」の土曜日を返す。

    土曜日に実行した場合は当日を含めず翌週の土曜日を返す（要件3.1）。
    日曜(6)の場合は6日後、月曜(0)の場合は5日後になる。
    """
    delta = (SATURDAY - today.weekday()) % 7
    if delta == 0:  # today が土曜 -> 当日は含めない
        delta = 7
    return today + timedelta(days=delta)


def target_weekends(today: date, weekends_ahead: int) -> list[WeekendDates]:
    """対象となる週末のリストを返す。

    Args:
        today: 基準日
        weekends_ahead: 対象とする週末の数（Phase 1 は 1、Phase 3 で 2）
    """
    if weekends_ahead < 1:
        return []

    first = next_saturday(today)
    weekends: list[WeekendDates] = []
    for i in range(weekends_ahead):
        saturday = first + timedelta(days=7 * i)
        weekends.append(
            WeekendDates(saturday=saturday, sunday=saturday + timedelta(days=1), index=i + 1)
        )
    return weekends
