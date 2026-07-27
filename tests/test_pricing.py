"""手荷物補正・実質価格のテスト（要件6.1）。"""

from __future__ import annotations

import pytest

from flightdeal import pricing
from flightdeal.models import AirlineClass

from .conftest import make_flight



@pytest.mark.parametrize(
    "raw,expected",
    [("¥11,400", 11400), ("11400", 11400), ("￥ 9,800", 9800), (12600, 12600)],
)
def test_parse_price(raw, expected):
    assert pricing.parse_price(raw) == expected


def test_parse_price_invalid():
    with pytest.raises(ValueError):
        pricing.parse_price("価格未定")


@pytest.mark.parametrize(
    "airline,expected",
    [
        ("ANA", AirlineClass.FSC),
        ("Solaseed Air", AirlineClass.FSC),   # 設定値 "Solaseed" との表記ゆれ
        ("Peach", AirlineClass.LCC),
        ("Spring Japan", AirlineClass.LCC),
        ("Toki Air", AirlineClass.UNKNOWN),   # リスト外
    ],
)
def test_classify_airline(airline, expected, cfg):
    assert pricing.classify_airline(airline, cfg) is expected


def test_surcharge_unknown_is_provisional(cfg):
    amount, provisional = pricing.surcharge_for("Toki Air", cfg)
    assert amount == cfg.baggage_surcharge_oneway
    assert provisional is True


def test_effective_price_mixed_lcc_and_fsc(cfg):
    """往路LCC + 復路FSC の混在ケース（要件6.1）。"""
    out = make_flight(airline="Jetstar", price=6900)
    ret = make_flight(airline="JAL", price=13100)
    total, out_sc, in_sc, provisional = pricing.effective_price(out, ret, cfg)
    assert out_sc == 3500
    assert in_sc == 0
    assert total == 6900 + 3500 + 13100 + 0
    assert provisional is False
