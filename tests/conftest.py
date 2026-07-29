from __future__ import annotations

import sys
from datetime import date, time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flightdeal.config import _from_dict  # noqa: E402
from flightdeal.models import (  # noqa: E402
    Combination,
    Flight,
    Rank,
    RouteConfig,
    WeekendDates,
)

HIJ = RouteConfig(iata="HIJ", name="広島", market_price=35000, max_price=30000, enabled=True)
MYJ = RouteConfig(iata="MYJ", name="松山", market_price=33000, max_price=28000, enabled=True)
AUG1 = WeekendDates(saturday=date(2026, 8, 1), sunday=date(2026, 8, 2), index=1)
AUG8 = WeekendDates(saturday=date(2026, 8, 8), sunday=date(2026, 8, 9), index=2)


# テスト用の固定設定。実 config.json（運用中に変わる）には依存しない。
# 実 config.json 自体の妥当性は test_config.py が別途チェックする。
def test_config_dict() -> dict:
    return {
        "origin": "HND",
        "destinations": [
            {"iata": "HIJ", "name": "広島", "market_price": 35000, "max_price": 30000,
             "enabled": True},
            {"iata": "MYJ", "name": "松山", "market_price": 33000, "max_price": 28000,
             "enabled": True},
            {"iata": "FUK", "name": "福岡", "market_price": 30000, "max_price": 26000,
             "enabled": False},
            {"iata": "CTS", "name": "新千歳", "market_price": 32000, "max_price": 28000,
             "enabled": False},
            {"iata": "OKA", "name": "那覇", "market_price": 40000, "max_price": 34000,
             "enabled": False},
        ],
        "weekends_ahead": 1,
        "time_filter": {"outbound_arrive_by": "11:00", "return_depart_after": "17:00"},
        "baggage_surcharge_oneway": 3500,
        "lcc_airlines": ["Peach", "Jetstar", "Spring Japan"],
        "fsc_airlines": ["ANA", "JAL", "Skymark", "Solaseed", "AIRDO", "StarFlyer"],
        "rank_thresholds": {"S": 0.70, "A": 0.85},
        "notify_top_n_per_route": 3,
        "search": {"max_searches_per_run": 20},
    }


# main() を --config 無しで呼ぶテストが実 config.json（20空港・運用中に変わる）を
# 拾わないよう、テスト用の固定 config を書き出して FLIGHTDEAL_CONFIG で既定にする。
# 実 config.json を読むのは test_config.py の live テストのみ（明示パスで読む）。
import json as _json  # noqa: E402
import os as _os  # noqa: E402
import tempfile  # noqa: E402

_TEST_CONFIG_PATH = Path(tempfile.gettempdir()) / "flightdeal_test_config.json"
_TEST_CONFIG_PATH.write_text(
    _json.dumps(test_config_dict(), ensure_ascii=False), encoding="utf-8"
)
_os.environ["FLIGHTDEAL_CONFIG"] = str(_TEST_CONFIG_PATH)


@pytest.fixture
def cfg():
    return _from_dict(test_config_dict())


@pytest.fixture
def route_hij():
    return HIJ


@pytest.fixture
def weekend_aug1():
    return AUG1


def _t(hhmm: str) -> time:
    hh, mm = hhmm.split(":")
    return time(int(hh), int(mm))


def make_flight(
    airline="ANA",
    dep="07:25",
    arr="08:50",
    price=11400,
    origin="HND",
    destination="HIJ",
    flight_date=date(2026, 8, 1),
    number=None,
):
    return Flight(
        origin=origin,
        destination=destination,
        flight_date=flight_date,
        airline=airline,
        depart_time=_t(dep),
        arrive_time=_t(arr),
        price=price,
        flight_number=number,
    )


def make_combination(
    total=22800,
    rank=Rank.S,
    route=HIJ,
    weekend=AUG1,
    outbound=None,
    inbound=None,
    out_sc=0,
    in_sc=0,
    provisional=False,
):
    return Combination(
        route=route,
        weekend=weekend,
        outbound=outbound or make_flight(),
        inbound=inbound
        or make_flight(dep="19:05", arr="20:30", origin="HIJ", destination="HND"),
        outbound_surcharge=out_sc,
        inbound_surcharge=in_sc,
        total_price=total,
        rank=rank,
        provisional_surcharge=provisional,
    )
