"""実行パイプライン（要件3.2.1 / 4.3）。

処理の流れ:
    週末算出
      └ 路線ごと（try-except で隔離）
          ├ 往路検索（HND -> 目的地, 土曜）  ※リトライ最大2回・検索間ランダム待機
          ├ 復路検索（目的地 -> HND, 日曜）
          ├ 時間帯フィルター
          ├ 総当たり組み合わせ
          ├ 手荷物補正 + 実質価格
          └ ランク判定 → 上位N件
    集約 → 通知判断

「壊れやすい取得」と「壊れない計算」をつなぐ層。リトライ・待機・例外の隔離は
すべてここに集約し、純粋関数側には持ち込まない（docs/アーキテクチャ.md 参照）。
"""

from __future__ import annotations

import logging
import random
import time as time_mod
from datetime import date

from . import filters, pricing, ranking, weekend as weekend_mod
from .config import Config
from .fetchers import FetchError, FlightFetcher
from .models import (
    Combination,
    Direction,
    Flight,
    RouteConfig,
    RouteResult,
    RunResult,
    WeekendDates,
)

log = logging.getLogger(__name__)


def fetch_with_retry(
    fetcher: FlightFetcher,
    origin: str,
    destination: str,
    flight_date: date,
    cfg: Config,
    direction: Direction = Direction.OUTBOUND,
) -> list[Flight]:
    """リトライ付きで1検索を実行する（要件4.3）。

    Raises:
        FetchError: 全試行が失敗した場合
    """
    attempts = cfg.search.retry_max + 1  # 初回 + リトライ回数
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        started = time_mod.monotonic()
        try:
            flights = fetcher.fetch(origin, destination, flight_date)
        except Exception as e:  # 取得層の想定外例外もここで吸収する
            last_error = e
            log.warning(
                "fetch_failed",
                extra={
                    "segment": f"{origin}-{destination}",
                    "date": flight_date.isoformat(),
                    "direction": direction.value,
                    "attempt": attempt,
                    "of": attempts,
                    "error": f"{type(e).__name__}: {e}",
                },
            )
            if attempt < attempts:
                time_mod.sleep(cfg.search.retry_wait_seconds)
            continue

        log.info(
            "fetch_ok",
            extra={
                "segment": f"{origin}-{destination}",
                "date": flight_date.isoformat(),
                "direction": direction.value,
                "attempt": attempt,
                "count": len(flights),
                "elapsed": round(time_mod.monotonic() - started, 2),
            },
        )
        return flights

    raise FetchError(
        f"{origin}-{destination} {flight_date} の取得に{attempts}回失敗しました: {last_error}"
    )


def sleep_between_searches(cfg: Config) -> None:
    """検索間のランダム待機（要件4.3 負荷抑制）。"""
    lo, hi = cfg.search.sleep_between_searches
    if hi <= 0:
        return
    wait = random.uniform(lo, hi)
    log.info("sleep_between_searches", extra={"seconds": round(wait, 1)})
    time_mod.sleep(wait)


def process_route(
    fetcher: FlightFetcher,
    route: RouteConfig,
    weekend: WeekendDates,
    cfg: Config,
) -> RouteResult:
    """1路線・1週末を処理する。例外はここで捕まえ RouteResult.error に格納する。"""
    result = RouteResult(route=route, weekend=weekend)
    started = time_mod.monotonic()

    try:
        outbounds = fetch_with_retry(
            fetcher, cfg.origin, route.iata, weekend.saturday, cfg, Direction.OUTBOUND
        )
        # 取得項目の欠損で除外された便数を記録する（要件3.2.2）。
        # 除外率が急に上がったらパーサ故障のサイン（docs/アーキテクチャ.md）。
        result.excluded_count += getattr(fetcher, "last_excluded", 0)

        sleep_between_searches(cfg)
        inbounds = fetch_with_retry(
            fetcher, route.iata, cfg.origin, weekend.sunday, cfg, Direction.RETURN
        )
        result.excluded_count += getattr(fetcher, "last_excluded", 0)
    except FetchError as e:
        result.error = str(e)
        log.error(
            "route_failed",
            extra={"route": route.iata, "weekend": weekend.index, "error": str(e)},
        )
        return result

    result.outbound_count = len(outbounds)
    result.inbound_count = len(inbounds)

    filtered_out = filters.filter_outbound(outbounds, cfg.time_filter.outbound_arrive_by)
    filtered_in = filters.filter_return(inbounds, cfg.time_filter.return_depart_after)

    combos: list[Combination] = []
    for out, ret in filters.combine(filtered_out, filtered_in):
        total, out_sc, in_sc, provisional = pricing.effective_price(out, ret, cfg)
        combos.append(
            Combination(
                route=route,
                weekend=weekend,
                outbound=out,
                inbound=ret,
                outbound_surcharge=out_sc,
                inbound_surcharge=in_sc,
                total_price=total,
                rank=ranking.judge_rank(total, route, cfg),
                provisional_surcharge=provisional,
            )
        )

    result.combinations = ranking.top_n_per_route(combos, cfg.notify_top_n_per_route)
    result.cheapest_total = min((c.total_price for c in combos), default=None)

    log.info(
        "route_done",
        extra={
            "route": route.iata,
            "weekend": weekend.index,
            "fetched": {"outbound": len(outbounds), "inbound": len(inbounds)},
            "excluded": result.excluded_count,
            "after_time_filter": {"outbound": len(filtered_out), "inbound": len(filtered_in)},
            "combinations": len(combos),
            "cheapest_total": result.cheapest_total,  # 相場調整の材料（要件Phase1-17）
            "market_price": route.market_price,
            "notifiable": len(result.combinations),
            "elapsed": round(time_mod.monotonic() - started, 2),
        },
    )
    return result


def run(fetcher: FlightFetcher, cfg: Config, today: date | None = None) -> RunResult:
    """1実行分のパイプラインを回す。"""
    started = time_mod.monotonic()
    base_date = today or date.today()
    weekends = weekend_mod.target_weekends(base_date, cfg.weekends_ahead)
    routes = cfg.enabled_destinations

    run_result = RunResult()
    searches_used = 0

    for route in routes:
        for wknd in weekends:
            # 1路線1週末あたり2検索（往路・復路）。上限を超えるなら打ち切る（要件4.3）。
            if searches_used + 2 > cfg.search.max_searches_per_run:
                log.warning(
                    "search_limit_reached",
                    extra={"used": searches_used, "limit": cfg.search.max_searches_per_run},
                )
                break

            if run_result.results:
                sleep_between_searches(cfg)

            run_result.results.append(process_route(fetcher, route, wknd, cfg))
            searches_used += 2
        else:
            continue
        break

    run_result.elapsed_seconds = round(time_mod.monotonic() - started, 2)
    log.info(
        "pipeline_done",
        extra={
            "routes": len(routes),
            "weekends": len(weekends),
            "searches": searches_used,
            "failed": sum(1 for r in run_result.results if r.failed),
            "notifiable": len(run_result.notifiable),
            "elapsed": run_result.elapsed_seconds,
        },
    )
    return run_result
