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


# --- 日本語の航空会社名・機内持ち込み無料（2026-11 修正） ------------------------

from dataclasses import replace  # noqa: E402
from pathlib import Path  # noqa: E402

from flightdeal.config import load_config  # noqa: E402

LIVE_CONFIG = Path(__file__).resolve().parents[1] / "config.json"


@pytest.fixture
def live_cfg():
    """本番の config.json。Google が返す日本語名で判定できるかを確認する。"""
    return load_config(LIVE_CONFIG)


@pytest.mark.parametrize(
    "airline,expected",
    [
        # Google Flights（language=ja）が実際に返す表記
        ("ANA", AirlineClass.FSC),
        ("JAL", AirlineClass.FSC),
        ("日本トランスオーシャン", AirlineClass.FSC),
        ("スカイマーク", AirlineClass.CARRY_ON),
        ("ソラシドエア", AirlineClass.CARRY_ON),
        ("スターフライヤー", AirlineClass.CARRY_ON),
        ("AIR DO", AirlineClass.CARRY_ON),
        ("エア・ドゥ", AirlineClass.CARRY_ON),
        ("ピーチ", AirlineClass.LCC),
        ("Peach", AirlineClass.LCC),
        ("ジェットスター・ジャパン", AirlineClass.LCC),
        ("スプリング・ジャパン", AirlineClass.LCC),
        ("トキエア", AirlineClass.UNKNOWN),
    ],
)
def test_classify_japanese_airline_names(airline, expected, live_cfg):
    assert pricing.classify_airline(airline, live_cfg) is expected


@pytest.mark.parametrize("airline", ["スカイマーク", "ソラシドエア", "スターフライヤー", "AIR DO"])
def test_carry_on_free_airlines_have_no_surcharge(airline, live_cfg):
    """機内持ち込み1個無料の航空会社は手荷物補正なし（仮扱いの注記も付けない）。"""
    assert pricing.surcharge_for(airline, live_cfg) == (0, False)


def test_carry_on_list_overrides_lcc_surcharge(cfg):
    """LCC区分の会社でも、機内持ち込み無料リストに入れれば補正しない。"""
    cfg = replace(
        cfg,
        lcc_airlines=["Jetstar", "Spring Japan"],
        carry_on_free_airlines=["Peach"],
    )
    assert pricing.surcharge_for("Peach", cfg) == (0, False)
    assert pricing.surcharge_for("Jetstar", cfg) == (cfg.baggage_surcharge_oneway, False)


def test_effective_price_lcc_and_carry_on(live_cfg):
    """往路LCC + 復路ソラシドエア: 往路だけ補正する。"""
    out = make_flight(airline="ピーチ", price=6900)
    ret = make_flight(airline="ソラシドエア", price=13100)
    total, out_sc, in_sc, provisional = pricing.effective_price(out, ret, live_cfg)
    assert (out_sc, in_sc) == (live_cfg.baggage_surcharge_oneway, 0)
    assert total == 6900 + live_cfg.baggage_surcharge_oneway + 13100
    assert provisional is False


# --- Google の運賃情報（機内持ち込み可否）を優先する ------------------------------


def test_carry_on_included_overrides_lcc_list(live_cfg):
    """LCCでも、その運賃に機内持ち込み手荷物が含まれるなら補正しない（例: Peach）。"""
    assert pricing.surcharge_for("Peach", live_cfg, carry_on_included=True) == (0, False)


def test_carry_on_excluded_adds_surcharge_even_for_listed_airline(live_cfg):
    """機内持ち込みが別料金の運賃なら、どのリストに入っていても補正する。"""
    amount = live_cfg.baggage_surcharge_oneway
    assert pricing.surcharge_for("ジェットスター", live_cfg, carry_on_included=False) == (
        amount, False,
    )
    assert pricing.surcharge_for("スカイマーク", live_cfg, carry_on_included=False) == (
        amount, False,
    )


def test_unknown_airline_with_carry_on_info_is_not_provisional(live_cfg):
    """リスト外の航空会社でも、運賃情報があれば「仮」扱いにしない。"""
    assert pricing.surcharge_for("トキエア", live_cfg, carry_on_included=True) == (0, False)


def test_falls_back_to_airline_lists_without_info(live_cfg):
    assert pricing.surcharge_for("Peach", live_cfg, carry_on_included=None) == (
        live_cfg.baggage_surcharge_oneway, False,
    )


def test_effective_price_uses_flight_carry_on_info(live_cfg):
    from dataclasses import replace as _replace

    out = _replace(make_flight(airline="Peach", price=6900), carry_on_included=True)
    ret = _replace(make_flight(airline="ジェットスター", price=7100), carry_on_included=False)
    total, out_sc, in_sc, provisional = pricing.effective_price(out, ret, live_cfg)
    assert (out_sc, in_sc) == (0, live_cfg.baggage_surcharge_oneway)
    assert total == 6900 + 7100 + live_cfg.baggage_surcharge_oneway
    assert provisional is False
