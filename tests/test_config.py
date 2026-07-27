"""設定読み込み・検証のテスト。

**重要**: ここでは「実際の config.json の中身」を固定値で検証しない。
config.json はユーザーが運用中に書き換えるファイルであり（要件4.5: 設定だけで
Phase 1→3 に移行できること）、中身を固定するとフェーズ移行のたびにCIが赤くなる。

  - 実 config.json に対しては「妥当であること」だけを検証する
  - 具体的な値の検証は、このファイル内で組み立てた設定辞書で行う
"""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path

import pytest

from flightdeal.config import _from_dict, load_config

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"

VALID_FETCHERS = {"stub", "fixture", "fast_flights", "playwright"}
VALID_NOTIFIERS = {"console", "line"}


def base_config(**overrides) -> dict:
    """テスト用の基準設定。実 config.json とは独立。"""
    data = {
        "origin": "HND",
        "destinations": [
            {"iata": "HIJ", "name": "広島", "market_price": 35000, "max_price": 30000,
             "enabled": True},
            {"iata": "MYJ", "name": "松山", "market_price": 33000, "max_price": 28000,
             "enabled": True},
            {"iata": "FUK", "name": "福岡", "market_price": 30000, "max_price": 26000,
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
    data.update(overrides)
    return data


# --- 実 config.json は「壊れていないこと」だけを検証する ---


def test_live_config_is_valid(cfg):
    """運用中の config.json が読めて検証を通ること。中身の値は固定しない。"""
    assert cfg.origin
    assert cfg.destinations
    assert cfg.enabled_destinations, "有効な路線が1つもありません"
    assert cfg.fetcher in VALID_FETCHERS
    assert cfg.notifier in VALID_NOTIFIERS


def test_live_config_respects_search_limit(cfg):
    """要件4.3: 有効路線数 × 週末数 × 2 が上限を超えないこと。"""
    planned = len(cfg.enabled_destinations) * cfg.weekends_ahead * 2
    assert planned <= cfg.search.max_searches_per_run


def test_live_config_is_utf8_json():
    """cp932 環境の pip / エディタで壊れないよう UTF-8 の正しいJSONであること。"""
    raw = CONFIG_PATH.read_bytes()
    json.loads(raw.decode("utf-8"))  # 例外が出なければOK


# --- 値の検証は独立した設定辞書で行う ---


def test_parses_fields():
    cfg = _from_dict(base_config())
    assert cfg.origin == "HND"
    assert [d.iata for d in cfg.enabled_destinations] == ["HIJ", "MYJ"]
    assert cfg.time_filter.outbound_arrive_by == time(11, 0)
    assert cfg.time_filter.return_depart_after == time(17, 0)
    assert cfg.baggage_surcharge_oneway == 3500
    assert cfg.notify_top_n_per_route == 3


def test_defaults_when_optional_keys_missing():
    data = base_config()
    data.pop("search")
    cfg = _from_dict(data)
    assert cfg.fetcher == "stub"
    assert cfg.notifier == "console"
    assert cfg.search.max_searches_per_run == 20
    assert cfg.search.retry_max == 2


def test_phase3_switch_without_code_change():
    """enabled と weekends_ahead だけで Phase 3 相当へ移行できること（要件4.5）。"""
    data = base_config(weekends_ahead=2)
    for d in data["destinations"]:
        d["enabled"] = True
    data["destinations"].extend([
        {"iata": "CTS", "name": "新千歳", "market_price": 32000, "max_price": 28000,
         "enabled": True},
        {"iata": "OKA", "name": "那覇", "market_price": 40000, "max_price": 34000,
         "enabled": True},
    ])
    cfg = _from_dict(data)
    assert len(cfg.enabled_destinations) == 5
    # 5路線 × 2週末 × 2方向 = 20 = 上限ちょうど（要件4.3）
    assert len(cfg.enabled_destinations) * cfg.weekends_ahead * 2 == 20


def test_search_limit_exceeded_raises():
    data = base_config(weekends_ahead=2)
    data["search"] = {"max_searches_per_run": 2}
    with pytest.raises(ValueError, match="検索回数"):
        _from_dict(data)


@pytest.mark.parametrize(
    "thresholds",
    [
        {"S": 0.90, "A": 0.85},   # S > A
        {"S": 0.70},              # A 欠落
        {"S": 0.0, "A": 0.85},    # 範囲外
        {"S": 0.70, "A": 1.0},    # 範囲外
    ],
)
def test_invalid_thresholds_raise(thresholds):
    with pytest.raises(ValueError, match="rank_thresholds"):
        _from_dict(base_config(rank_thresholds=thresholds))


def test_invalid_weekends_ahead_raises():
    with pytest.raises(ValueError, match="weekends_ahead"):
        _from_dict(base_config(weekends_ahead=3))


def test_negative_price_raises():
    data = base_config()
    data["destinations"][0]["market_price"] = 0
    with pytest.raises(ValueError, match="market_price"):
        _from_dict(data)


def test_airline_lists_must_not_overlap():
    data = base_config()
    data["lcc_airlines"] = ["Peach", "ANA"]  # ANA は FSC 側にもある
    with pytest.raises(ValueError, match="重複"):
        _from_dict(data)


def test_load_config_from_path(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(base_config(), ensure_ascii=False), encoding="utf-8")
    cfg = load_config(path)
    assert cfg.origin == "HND"
