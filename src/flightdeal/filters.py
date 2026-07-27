"""時間帯フィルターと組み合わせ生成（要件3.3 / 3.2.1）。

すべて純粋関数。外部I/Oを持ち込まないこと。
"""

from __future__ import annotations

from datetime import time
from typing import Any, Mapping

from .models import Flight

# 必須項目（要件3.2.2）。欠けている便は判定対象から除外する。
REQUIRED_FIELDS = ("airline", "depart_time", "arrive_time", "price")


def filter_outbound(flights: list[Flight], arrive_by: time) -> list[Flight]:
    """往路（土曜）: 現地到着時刻が arrive_by 以前の便のみを残す。

    境界値（到着 == arrive_by）は含む。
    """
    return [f for f in flights if f.arrive_time <= arrive_by]


def filter_return(flights: list[Flight], depart_after: time) -> list[Flight]:
    """復路（日曜）: 現地出発時刻が depart_after 以降の便のみを残す。

    境界値（出発 == depart_after）は含む。
    """
    return [f for f in flights if f.depart_time >= depart_after]


def combine(outbounds: list[Flight], inbounds: list[Flight]) -> list[tuple[Flight, Flight]]:
    """往路×復路の総当たり組み合わせを生成する（要件3.2.1）。

    同一路線・同一週末の便同士を組むため日付整合のチェックは不要。
    どちらかが空なら空リストを返す。

    件数は「時間帯フィルター後」の便数の積になる。フィルターを先に適用してから
    呼ぶこと（順序を逆にすると無駄な組み合わせが大量に生成される）。
    """
    if not outbounds or not inbounds:
        return []
    return [(o, i) for o in outbounds for i in inbounds]


def is_complete(flight_like: Mapping[str, Any]) -> bool:
    """取得結果に必須項目が揃っているか判定する（要件3.2.2「除外」）。

    False の場合、呼び出し側はその便を除外し、除外件数をログに記録する。
    """
    for key in REQUIRED_FIELDS:
        value = flight_like.get(key)
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
    return True
