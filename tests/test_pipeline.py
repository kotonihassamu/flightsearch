"""パイプラインのテスト（要件4.3）。

外部サイトへは接続せず、StubFetcher と失敗注入で検証する（要件6.2）。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from flightdeal import formatter, pipeline
from flightdeal.fetchers import FetchError
from flightdeal.fetchers.stub import StubFetcher
from flightdeal.models import Flight, Rank
from flightdeal.notifiers.line import MAX_MESSAGES_PER_RUN

TODAY = date(2026, 7, 27)  # 月曜 -> 第1週末は 8/1(土)・8/2(日)


@pytest.fixture
def fast_cfg(cfg):
    """テストを高速化するため待機とリトライ待ちを 0 にした設定。"""
    search = replace(cfg.search, sleep_between_searches=(0, 0), retry_wait_seconds=0)
    return replace(cfg, search=search)


class FlakyFetcher(StubFetcher):
    """指定回数だけ失敗してから成功するフェッチャ。"""

    def __init__(self, fail_times: int) -> None:
        super().__init__()
        self.fail_times = fail_times
        self.calls = 0

    def fetch(self, origin, destination, flight_date):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise FetchError("一時的な失敗")
        return super().fetch(origin, destination, flight_date)


class AlwaysFailFetcher(StubFetcher):
    def fetch(self, origin, destination, flight_date):
        raise FetchError("常に失敗")


def test_fetch_with_retry_recovers(fast_cfg):
    """リトライ範囲内なら回復する（既定: 初回 + 2回 = 計3回）。"""
    fetcher = FlakyFetcher(fail_times=2)
    flights = pipeline.fetch_with_retry(fetcher, "HND", "HIJ", date(2026, 8, 1), fast_cfg)
    assert flights
    assert fetcher.calls == 3


def test_fetch_with_retry_gives_up(fast_cfg):
    fetcher = FlakyFetcher(fail_times=99)
    with pytest.raises(FetchError):
        pipeline.fetch_with_retry(fetcher, "HND", "HIJ", date(2026, 8, 1), fast_cfg)
    assert fetcher.calls == fast_cfg.search.retry_max + 1


def test_run_produces_notifiable_combinations(fast_cfg):
    result = pipeline.run(StubFetcher(), fast_cfg, today=TODAY)

    assert len(result.results) == 2  # 2路線 × 第1週末のみ
    assert not result.all_failed
    assert result.notifiable
    assert all(c.rank is not Rank.NONE for c in result.notifiable)


def test_run_applies_time_filter(fast_cfg):
    """往路は11:00以前着、復路は17:00以降発のみが採用される（要件3.3）。"""
    result = pipeline.run(StubFetcher(), fast_cfg, today=TODAY)

    for combo in result.notifiable:
        assert combo.outbound.arrive_time <= fast_cfg.time_filter.outbound_arrive_by
        assert combo.inbound.depart_time >= fast_cfg.time_filter.return_depart_after


def test_run_limits_top_n_per_route(fast_cfg):
    result = pipeline.run(StubFetcher(), fast_cfg, today=TODAY)
    for route_result in result.results:
        assert len(route_result.combinations) <= fast_cfg.notify_top_n_per_route


def test_route_failure_is_isolated(fast_cfg):
    """1路線の失敗が他路線を止めない（要件4.3 路線単位の隔離）。"""
    fetcher = StubFetcher(fail_routes={"HND-HIJ"})
    result = pipeline.run(fetcher, fast_cfg, today=TODAY)

    failed = [r for r in result.results if r.failed]
    ok = [r for r in result.results if not r.failed]

    assert [r.route.iata for r in failed] == ["HIJ"]
    assert [r.route.iata for r in ok] == ["MYJ"]
    assert not result.all_failed
    assert result.notifiable  # 松山の結果は生きている


def test_all_failed_is_detected(fast_cfg):
    """全路線失敗はサイレント障害防止のトリガー（要件4.3）。"""
    result = pipeline.run(AlwaysFailFetcher(), fast_cfg, today=TODAY)
    assert result.all_failed
    assert not result.notifiable


def test_run_respects_search_limit(cfg, fast_cfg):
    """検索回数の上限を超えない（要件4.3 負荷抑制）。"""
    search = replace(fast_cfg.search, max_searches_per_run=2)
    limited = replace(fast_cfg, search=search)
    result = pipeline.run(StubFetcher(), limited, today=TODAY)
    assert len(result.results) == 1  # 2検索で打ち切り


def test_pricing_applied_to_lcc(fast_cfg):
    """松山路線は Jetstar を含むため手荷物補正が乗る（要件3.4）。"""
    result = pipeline.run(StubFetcher(), fast_cfg, today=TODAY)
    myj = next(r for r in result.results if r.route.iata == "MYJ")

    for combo in myj.combinations:
        expected = (
            combo.outbound.price
            + combo.outbound_surcharge
            + combo.inbound.price
            + combo.inbound_surcharge
        )
        assert combo.total_price == expected
        if combo.outbound.airline == "Jetstar":
            assert combo.outbound_surcharge == fast_cfg.baggage_surcharge_oneway


def test_weekend_dates_are_saturday_and_sunday(fast_cfg):
    result = pipeline.run(StubFetcher(), fast_cfg, today=TODAY)
    for r in result.results:
        assert r.weekend.saturday == date(2026, 8, 1)
        assert r.weekend.sunday == date(2026, 8, 2)
        assert r.weekend.saturday.weekday() == 5
        assert r.weekend.sunday.weekday() == 6


def test_phase3_needs_no_code_change(fast_cfg):
    """全5路線・第2週末まで設定だけで動く（要件4.5 / Phase 3 完了条件）。"""
    phase3 = replace(
        fast_cfg,
        destinations=[replace(d, enabled=True) for d in fast_cfg.destinations],
        weekends_ahead=2,
    )
    result = pipeline.run(StubFetcher(), phase3, today=TODAY)

    assert len(result.results) == 10  # 5路線 × 2週末
    assert not any(r.failed for r in result.results)


def test_phase3_notification_fits_in_two_messages(fast_cfg):
    """Phase 3 の最大構成で notify_top_n_per_route=2 なら LINE 2通に収まる。

    往路/復路の2リンクを載せるため本文が長い。Phase 3（全5路線×2週末）では
    notify_top_n_per_route を 2 に下げる運用とする（要件3.6 / R6 無料枠 / 運用手順.md）。
    top_n=3 のままだと3通になり LineNotifier が末尾を切り捨てる。
    """
    phase3 = replace(
        fast_cfg,
        destinations=[replace(d, enabled=True) for d in fast_cfg.destinations],
        weekends_ahead=2,
        notify_top_n_per_route=2,
    )
    result = pipeline.run(StubFetcher(), phase3, today=TODAY)
    chunks = formatter.split_message(formatter.format_run(result))

    assert len(chunks) <= MAX_MESSAGES_PER_RUN, (
        f"通知が{len(chunks)}通に分割されます。notify_top_n_per_route を見直してください。"
    )


class ExcludingFetcher(StubFetcher):
    """取得項目の欠損で便を除外したことを報告するフェッチャ。"""

    def __init__(self, excluded_per_call: int) -> None:
        super().__init__()
        self.excluded_per_call = excluded_per_call

    def fetch(self, origin, destination, flight_date):
        flights = super().fetch(origin, destination, flight_date)
        self.last_excluded = self.excluded_per_call
        return flights


def test_excluded_count_is_recorded(fast_cfg):
    """除外件数を記録する（要件3.2.2）。パーサ故障の早期検知に使う。"""
    result = pipeline.run(ExcludingFetcher(excluded_per_call=2), fast_cfg, today=TODAY)

    for route_result in result.results:
        # 1路線あたり往路・復路の2回取得 -> 2件 × 2回 = 4件
        assert route_result.excluded_count == 4


def test_excluded_count_defaults_to_zero_for_plain_fetcher(fast_cfg):
    """last_excluded を持たないフェッチャでも落ちない。"""
    result = pipeline.run(StubFetcher(), fast_cfg, today=TODAY)
    assert all(r.excluded_count == 0 for r in result.results)


def test_cheapest_total_recorded_even_when_nothing_notifiable(fast_cfg):
    """0件通知でも最安値は記録する（相場調整の材料。要件Phase1-17）。"""
    strict = replace(
        fast_cfg,
        destinations=[
            replace(d, market_price=1000, max_price=900) for d in fast_cfg.destinations
        ],
    )
    result = pipeline.run(StubFetcher(), strict, today=TODAY)

    assert not result.notifiable
    for route_result in result.results:
        assert route_result.cheapest_total is not None
        assert route_result.cheapest_total > 0


def test_phase1_notification_fits_in_one_message(fast_cfg):
    """Phase 1（2路線・第1週末）は余裕で1通に収まる。"""
    result = pipeline.run(StubFetcher(), fast_cfg, today=TODAY)
    chunks = formatter.split_message(formatter.format_run(result))
    assert len(chunks) == 1


def test_flights_are_immutable():
    """Flight は frozen dataclass（純粋関数側で書き換えが起きないことの保証）。"""
    f = Flight(
        origin="HND", destination="HIJ", flight_date=date(2026, 8, 1),
        airline="ANA", depart_time=__import__("datetime").time(7, 25),
        arrive_time=__import__("datetime").time(8, 50), price=11400,
    )
    with pytest.raises(Exception):
        f.price = 1  # type: ignore[misc]
