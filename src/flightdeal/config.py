"""config.json の読み込みと検証（要件4.5）。

設定は「コード変更なしでフェーズ移行できる」ことが目的。
enabled フラグと weekends_ahead を触るだけで Phase 1 -> 3 に移行できる状態を保つ。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path

from .models import RouteConfig

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.json"


@dataclass(frozen=True)
class TimeFilter:
    outbound_arrive_by: time
    return_depart_after: time


@dataclass(frozen=True)
class SearchPolicy:
    max_searches_per_run: int
    retry_max: int
    retry_wait_seconds: int
    sleep_between_searches: tuple[int, int]


@dataclass(frozen=True)
class Config:
    origin: str
    destinations: list[RouteConfig]
    weekends_ahead: int
    time_filter: TimeFilter
    baggage_surcharge_oneway: int
    lcc_airlines: list[str]
    fsc_airlines: list[str]
    rank_thresholds: dict[str, float]
    notify_top_n_per_route: int
    fetcher: str
    notifier: str
    search: SearchPolicy

    @property
    def enabled_destinations(self) -> list[RouteConfig]:
        return [d for d in self.destinations if d.enabled]


def _parse_hhmm(value: str) -> time:
    """'11:00' -> time(11, 0)。"""
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def load_config(path: str | Path | None = None) -> Config:
    """config.json を読み込んで Config を返す。

    環境変数 FLIGHTDEAL_CONFIG が指定されていればそれを優先する。
    """
    resolved = Path(path or os.environ.get("FLIGHTDEAL_CONFIG") or DEFAULT_CONFIG_PATH)
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    return _from_dict(raw)


def _from_dict(raw: dict) -> Config:
    tf = raw["time_filter"]
    search = raw.get("search", {})
    sleep = search.get("sleep_between_searches", [5, 15])

    cfg = Config(
        origin=raw["origin"],
        destinations=[RouteConfig(**d) for d in raw["destinations"]],
        weekends_ahead=int(raw["weekends_ahead"]),
        time_filter=TimeFilter(
            outbound_arrive_by=_parse_hhmm(tf["outbound_arrive_by"]),
            return_depart_after=_parse_hhmm(tf["return_depart_after"]),
        ),
        baggage_surcharge_oneway=int(raw["baggage_surcharge_oneway"]),
        lcc_airlines=list(raw["lcc_airlines"]),
        fsc_airlines=list(raw["fsc_airlines"]),
        rank_thresholds={k: float(v) for k, v in raw["rank_thresholds"].items()},
        notify_top_n_per_route=int(raw["notify_top_n_per_route"]),
        fetcher=raw.get("fetcher", "stub"),
        notifier=raw.get("notifier", "console"),
        search=SearchPolicy(
            max_searches_per_run=int(search.get("max_searches_per_run", 20)),
            retry_max=int(search.get("retry_max", 2)),
            retry_wait_seconds=int(search.get("retry_wait_seconds", 10)),
            sleep_between_searches=(int(sleep[0]), int(sleep[1])),
        ),
    )
    validate_config(cfg)
    return cfg


def validate_config(cfg: Config) -> None:
    """設定の整合性チェック。異常時は ValueError を送出する。

    設定プラミングは骨組み段階でも動く必要があるため、ここは実装済み。
    """
    s = cfg.rank_thresholds.get("S")
    a = cfg.rank_thresholds.get("A")
    if s is None or a is None:
        raise ValueError("rank_thresholds には 'S' と 'A' が必要です")
    if not (0 < s < a < 1):
        raise ValueError(f"rank_thresholds は 0 < S < A < 1 である必要があります (S={s}, A={a})")

    if cfg.weekends_ahead not in (1, 2):
        raise ValueError("weekends_ahead は 1 または 2 です")

    for d in cfg.destinations:
        if d.market_price <= 0 or d.max_price <= 0:
            raise ValueError(f"{d.iata}: market_price / max_price は正の整数である必要があります")

    overlap = set(cfg.lcc_airlines) & set(cfg.fsc_airlines)
    if overlap:
        raise ValueError(f"lcc_airlines と fsc_airlines が重複しています: {sorted(overlap)}")

    planned = len(cfg.enabled_destinations) * cfg.weekends_ahead * 2
    if planned > cfg.search.max_searches_per_run:
        raise ValueError(
            f"検索回数が上限を超えます: {planned} > {cfg.search.max_searches_per_run}"
            "（要件4.3 負荷抑制）"
        )
