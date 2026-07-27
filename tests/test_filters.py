"""時間帯フィルター・組み合わせ生成のテスト（要件6.1）。"""

from __future__ import annotations

from datetime import time

import pytest

from flightdeal import filters

from .conftest import make_flight



def test_filter_outbound_boundary():
    """到着 == 閾値 は「含む」。"""
    flights = [
        make_flight(arr="10:59"),
        make_flight(arr="11:00"),  # 境界: 含む
        make_flight(arr="11:01"),  # 除外
    ]
    kept = filters.filter_outbound(flights, time(11, 0))
    assert [f.arrive_time for f in kept] == [time(10, 59), time(11, 0)]


def test_filter_return_boundary():
    """出発 == 閾値 は「含む」。"""
    flights = [
        make_flight(dep="16:59"),  # 除外
        make_flight(dep="17:00"),  # 境界: 含む
        make_flight(dep="19:05"),
    ]
    kept = filters.filter_return(flights, time(17, 0))
    assert [f.depart_time for f in kept] == [time(17, 0), time(19, 5)]


def test_combine_is_cartesian_product():
    out = [make_flight(dep="07:25"), make_flight(dep="08:05")]
    ret = [make_flight(dep="19:05"), make_flight(dep="20:10")]
    assert len(filters.combine(out, ret)) == 4


def test_combine_empty_side():
    assert filters.combine([], [make_flight()]) == []
    assert filters.combine([make_flight()], []) == []


def test_is_complete_accepts_full_record():
    assert filters.is_complete(
        {"airline": "ANA", "depart_time": "07:25", "arrive_time": "08:50", "price": 11400}
    )


@pytest.mark.parametrize(
    "missing",
    ["airline", "depart_time", "arrive_time", "price"],
)
def test_is_complete_rejects_missing_field(missing):
    record = {
        "airline": "ANA",
        "depart_time": "07:25",
        "arrive_time": "08:50",
        "price": 11400,
    }
    record[missing] = None
    assert not filters.is_complete(record)


def test_is_complete_rejects_blank_string():
    assert not filters.is_complete(
        {"airline": "  ", "depart_time": "07:25", "arrive_time": "08:50", "price": 11400}
    )
