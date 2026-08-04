"""日付指定検索（search.py）のテスト。外部接続なし。"""

from __future__ import annotations

import sys
from datetime import date, time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import search  # noqa: E402
from flightdeal.fetchers.stub import StubFetcher  # noqa: E402
from flightdeal.models import Rank  # noqa: E402

from .conftest import HIJ  # noqa: E402

OUT = date(2026, 9, 19)
BACK = date(2026, 9, 22)


def test_trip_dates_holds_arbitrary_pair():
    """週末でなくても日付ペアとして扱える。"""
    w = search.trip_dates(OUT, BACK)
    assert w.saturday == OUT
    assert w.sunday == BACK


def test_parse_hhmm():
    assert search.parse_hhmm("14:30") == time(14, 30)


def test_search_route_without_time_filter(cfg):
    """時間帯フィルタなしなら全便が組み合わせ対象になる。"""
    r = search.search_route(StubFetcher(), HIJ, OUT, BACK, cfg, (None, None), top_n=10)

    assert not r.failed
    assert r.outbound_count == 3 and r.inbound_count == 3
    assert r.combinations
    assert len(r.combinations) == 9  # 3 x 3 の総当たり


def test_search_route_applies_time_filter(cfg):
    """時間帯フィルタを渡すと絞られる。"""
    r = search.search_route(
        StubFetcher(), HIJ, OUT, BACK, cfg,
        (cfg.time_filter.outbound_arrive_by, cfg.time_filter.return_depart_after),
        top_n=10,
    )
    assert r.after_filter_out < r.outbound_count
    assert all(c.outbound.arrive_time <= cfg.time_filter.outbound_arrive_by
               for c in r.combinations)


def test_search_route_sorted_cheapest_first(cfg):
    r = search.search_route(StubFetcher(), HIJ, OUT, BACK, cfg, (None, None), top_n=5)
    prices = [c.total_price for c in r.combinations]
    assert prices == sorted(prices)
    assert r.best.total_price == min(prices)


def test_search_route_shows_results_regardless_of_rank(cfg):
    """ランク外でも候補として表示する（絞り込みではなく選択肢の提示）。"""
    from dataclasses import replace
    strict = replace(cfg, destinations=[replace(d, market_price=1000, max_price=900)
                                        for d in cfg.destinations])
    route = strict.destinations[0]
    r = search.search_route(StubFetcher(), route, OUT, BACK, strict, (None, None))

    assert r.combinations, "ランク外でも候補は返す"
    assert all(c.rank is Rank.NONE for c in r.combinations)


def test_search_route_isolates_failure(cfg):
    fetcher = StubFetcher(fail_routes={"HND-HIJ"})
    r = search.search_route(fetcher, HIJ, OUT, BACK, cfg, (None, None))
    assert r.failed
    assert r.best is None


def test_report_contains_dates_and_prices(cfg):
    r = search.search_route(StubFetcher(), HIJ, OUT, BACK, cfg, (None, None))
    report = search.build_report([r], OUT, BACK, cfg, (None, None))

    assert "2026/09/19" in report
    assert "2026/09/22" in report
    assert "3泊4日" in report
    assert "広島" in report
    assert "指定なし（全便）" in report


def test_report_handles_no_results(cfg):
    r = search.RouteSearch(route=HIJ, error="取得失敗")
    report = search.build_report([r], OUT, BACK, cfg, (None, None))
    assert "取得失敗" in report
    assert "見つかりませんでした" in report


def test_line_message_is_compact(cfg):
    r = search.search_route(StubFetcher(), HIJ, OUT, BACK, cfg, (None, None))
    msg = search.build_line_message([r], OUT, BACK, cfg)
    assert "【検索結果】" in msg
    assert "09/19" in msg
    assert len(msg) < 5000
