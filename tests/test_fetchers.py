"""取得層のテスト。

外部サイトへ接続するテストは書かない（要件6.2: CIの合否条件に含めない）。
実取得の検証は Phase 0 で手元PCの scripts/phase0_check.py により行う。
"""

from __future__ import annotations

from datetime import date, time

import pytest

from flightdeal.fetchers import FetchError, build_fetcher
from types import SimpleNamespace

from flightdeal.fetchers.fast_flights_fetcher import (
    FastFlightsFetcher,
    flights_to_flight,
    to_time,
)
from flightdeal.fetchers.stub import FixtureFetcher, StubFetcher


def test_build_fetcher_stub():
    assert isinstance(build_fetcher("stub"), StubFetcher)


def test_build_fetcher_unknown():
    with pytest.raises(ValueError):
        build_fetcher("nope")


def test_build_fetcher_playwright_not_implemented():
    with pytest.raises(NotImplementedError):
        build_fetcher("playwright")


def test_stub_returns_flights():
    flights = StubFetcher().fetch("HND", "HIJ", date(2026, 8, 1))
    assert len(flights) == 3
    assert all(f.price > 0 for f in flights)
    assert all(f.origin == "HND" and f.destination == "HIJ" for f in flights)


def test_stub_route_isolation():
    """意図的失敗を注入できること（要件4.3 の動作確認用）。"""
    fetcher = StubFetcher(fail_routes={"HND-HIJ"})
    with pytest.raises(FetchError):
        fetcher.fetch("HND", "HIJ", date(2026, 8, 1))
    # 別路線は影響を受けない
    assert fetcher.fetch("HND", "MYJ", date(2026, 8, 1))


def test_fixture_fetcher_missing_file(tmp_path):
    with pytest.raises(FetchError):
        FixtureFetcher(fixture_dir=tmp_path).fetch("HND", "HIJ", date(2026, 8, 1))


def test_fixture_fetcher_reads_saved_response():
    """Phase 0 で保存した実レスポンスのパース回帰テスト（要件6.2）。"""
    flights = FixtureFetcher().fetch("HND", "HIJ", date(2026, 8, 1))
    assert flights
    assert flights[0].airline


# --- fast-flights 3.x のパース部（外部接続なし） ---
# fast-flights の SingleFlight / Flights を模した最小の互換オブジェクトで検証する。
# 実データ構造（Phase 0 2026-07 実測）:
#   Flights(price=int, airlines=['ANA'], type='NH', flights=[SingleFlight(...)])
#   SingleFlight.departure.time = [時, 分]（分=0のとき [時]）


def _seg(dep, arr, frm="HND", to="HIJ"):
    return SimpleNamespace(
        departure=SimpleNamespace(time=dep, date=[2026, 8, 1]),
        arrival=SimpleNamespace(time=arr, date=[2026, 8, 1]),
        from_airport=SimpleNamespace(code=frm),
        to_airport=SimpleNamespace(code=to),
    )


def _parsed(price=20590, airlines=("ANA",), segments=None, type_="NH"):
    return SimpleNamespace(
        price=price,
        airlines=list(airlines),
        type=type_,
        flights=segments if segments is not None else [_seg([8, 45], [10, 5])],
    )


@pytest.mark.parametrize(
    "parts,expected",
    [
        ([18, 10], time(18, 10)),
        ([8, 45], time(8, 45)),
        ([21], time(21, 0)),      # 分=0 は1要素
        ([13], time(13, 0)),
        ([0, 5], time(0, 5)),
    ],
)
def test_to_time(parts, expected):
    assert to_time(parts) == expected


@pytest.mark.parametrize("bad", [[], None, "18:10", [25, 0], [12, 70]])
def test_to_time_invalid(bad):
    with pytest.raises(ValueError):
        to_time(bad)


def test_flights_to_flight_maps_fields():
    parsed = _parsed(price=20590, airlines=("ANA",), segments=[_seg([18, 10], [19, 35])])
    flight = flights_to_flight(parsed, "HND", "HIJ", date(2026, 8, 1))

    assert flight is not None
    assert flight.airline == "ANA"
    assert flight.depart_time == time(18, 10)
    assert flight.arrive_time == time(19, 35)
    assert flight.price == 20590
    assert flight.flight_number is None


def test_flights_to_flight_handles_zero_minute():
    parsed = _parsed(segments=[_seg([19, 40], [21])])  # 21:00 が [21]
    flight = flights_to_flight(parsed, "HND", "HIJ", date(2026, 8, 1))
    assert flight.arrive_time == time(21, 0)


def test_flights_to_flight_excludes_connecting():
    """2区間（乗り継ぎ）は直行便でないので除外（要件3.1）。"""
    parsed = _parsed(segments=[_seg([7, 25], [9, 0]), _seg([9, 40], [11, 50])])
    assert flights_to_flight(parsed, "HND", "HIJ", date(2026, 8, 1)) is None


def test_flights_to_flight_excludes_missing_price():
    parsed = _parsed(price=None, segments=[_seg([8, 45], [10, 5])])
    assert flights_to_flight(parsed, "HND", "HIJ", date(2026, 8, 1)) is None


def test_flights_to_flight_falls_back_to_type_when_no_airline_name():
    parsed = _parsed(airlines=(), type_="NH", segments=[_seg([8, 45], [10, 5])])
    flight = flights_to_flight(parsed, "HND", "HIJ", date(2026, 8, 1))
    assert flight is not None
    assert flight.airline == "NH"


def test_import_failure_message_includes_real_cause():
    """「未インストール」と決めつけず、実際の例外内容を出すこと。

    ImportError を握りつぶして固定文言にすると、
    「古い版が入っている」「依存の初期化に失敗」といった別原因を追えなくなる。
    """
    from flightdeal.fetchers.fast_flights_fetcher import import_failure_message

    msg = import_failure_message(ImportError("cannot import name 'FlightQuery'"))

    assert "ImportError" in msg
    assert "cannot import name 'FlightQuery'" in msg  # 本当の原因が残る
    assert "3.x" in msg                                # 対処のヒント
