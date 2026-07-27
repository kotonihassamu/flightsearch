from __future__ import annotations

import sys
from datetime import date, time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flightdeal.config import load_config  # noqa: E402
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


@pytest.fixture
def cfg():
    return load_config(ROOT / "config.json")


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
