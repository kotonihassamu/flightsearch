#!/usr/bin/env python3
"""通しテスト（検索 → 判定 → LINE通知）を好きな時に実行する。

通常の日次実行は「お得な便がある時だけ」通知するので、
「今、全部つながっているか」を確認したいときに使えない。
このスクリプトは **お得な便が0件でも必ずLINEに1通送る**。
届いたメッセージ本文に検索結果の要約が入るので、
  検索できているか / 判定できているか / LINEに届くか
を1発で確認できる。

デフォルトは速度重視で「先頭2路線 × 次の1週末」だけ検索する（約30秒）。

使い方:
    python scripts/smoke_test.py                 # 先頭2路線を実検索してLINE送信
    python scripts/smoke_test.py --routes 5      # 先頭5路線
    python scripts/smoke_test.py --dest HIJ FUK  # 路線を指定
    python scripts/smoke_test.py --dry-run       # 実検索せず(Stub)・コンソールのみ
    python scripts/smoke_test.py --console        # 実検索するがLINEに送らずコンソール表示

終了コード: 0=成功 / 2=検索が全滅 / 3=LINE送信失敗
"""

from __future__ import annotations

import argparse
import sys
import time as time_mod
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flightdeal import pipeline  # noqa: E402
from flightdeal.config import load_config  # noqa: E402
from flightdeal.env import load_dotenv  # noqa: E402
from flightdeal.fetchers import build_fetcher  # noqa: E402
from flightdeal.logging_setup import setup_logging  # noqa: E402
from flightdeal.models import Rank, RunResult  # noqa: E402
from flightdeal.notifiers import build_notifier  # noqa: E402


def yen(v) -> str:
    return "—" if v is None else f"￥{v:,}"


def build_message(result: RunResult, elapsed: float, note: str) -> str:
    """通しテストの結果を1通のメッセージにまとめる（0件でも中身のある本文にする）。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "【通しテスト】週末格安便システム",
        f"実行 {now} / 所要 {elapsed:.0f}秒 / {note}",
        "",
    ]

    searched = len(result.results)
    failed = [r for r in result.results if r.failed]
    lines.append(f"検索: {searched}路線（失敗 {len(failed)}）")

    for r in result.results:
        if r.failed:
            lines.append(f"  ✗ {r.route.name}: 取得失敗")
            continue
        lines.append(
            f"  {r.route.name}: 往路{r.outbound_count}/復路{r.inbound_count}便"
            f" 最安 {yen(r.cheapest_total)}（相場 {yen(r.route.market_price)}）"
        )

    all_failed = bool(result.results) and len(failed) == searched

    lines.append("")
    deals = result.notifiable
    if deals:
        lines.append(f"お得な便（ランク入り）: {len(deals)}件")
        for c in sorted(deals, key=lambda x: x.total_price)[:5]:
            lines.append(
                f"  【{c.rank.value}】{c.route.name} "
                f"{c.weekend.saturday:%m/%d}-{c.weekend.sunday:%m/%d} {yen(c.total_price)}"
            )
    elif not all_failed:
        lines.append("お得な便（ランク入り）: 0件")
        lines.append("（相場設定より高いだけ。検索・判定は正常に動いています）")

    lines.append("")
    if all_failed:
        lines.append("⚠ 全路線で取得失敗しました。")
        lines.append("Bot判定/ネットワーク/依存関係を確認してください。")
        lines.append("（このLINE通知が届いていること自体は、通知経路が正常な証拠です）")
    else:
        lines.append("このメッセージが届いていれば、検索→判定→LINE通知まで全て正常です。")

    return "\n".join(lines)


def main() -> int:
    setup_logging()
    load_dotenv()

    p = argparse.ArgumentParser(description="検索〜LINE通知の通しテスト")
    p.add_argument("--config", default=None)
    p.add_argument("--routes", type=int, default=2,
                   help="先頭から何路線を検索するか（速度優先。既定2）")
    p.add_argument("--dest", nargs="*", default=None,
                   help="路線をIATAで指定（指定時は --routes より優先）")
    p.add_argument("--weeks", type=int, default=1, help="対象週末数（既定1）")
    p.add_argument("--dry-run", action="store_true",
                   help="実検索せずStubで通す（オフラインでチェーン確認）")
    p.add_argument("--console", action="store_true",
                   help="実検索するがLINEに送らずコンソール表示")
    args = p.parse_args()

    cfg = load_config(args.config)

    # 対象路線を絞る（速度優先）
    if args.dest:
        wanted = {d.upper() for d in args.dest}
        chosen = [d for d in cfg.destinations if d.iata in wanted]
    else:
        chosen = cfg.enabled_destinations[: max(1, args.routes)]

    if not chosen:
        print("対象路線がありません。")
        return 1

    # 対象路線だけ有効化した設定を作る（本番 config は変更しない）
    chosen_iatas = {d.iata for d in chosen}
    test_cfg = replace(
        cfg,
        destinations=[replace(d, enabled=(d.iata in chosen_iatas)) for d in cfg.destinations],
        weekends_ahead=max(1, min(args.weeks, 2)),
        # 通しテストは全件送るので通知上限は外す
        notify_max_total=0,
        notify_top_n_per_route=max(cfg.notify_top_n_per_route, 3),
    )

    fetcher_name = "stub" if args.dry_run else test_cfg.fetcher
    notifier_name = "console" if (args.dry_run or args.console) else test_cfg.notifier

    if args.dry_run:
        test_cfg = replace(
            test_cfg,
            search=replace(test_cfg.search, sleep_between_searches=(0, 0), retry_wait_seconds=0),
        )

    print("=" * 56)
    print("通しテスト（検索 → 判定 → 通知）")
    print("=" * 56)
    print(f"対象路線 : {', '.join(d.name for d in chosen)}")
    print(f"週末数   : {test_cfg.weekends_ahead}")
    print(f"取得     : {fetcher_name}")
    print(f"通知先   : {notifier_name}")
    print("=" * 56)
    print()

    started = time_mod.monotonic()
    fetcher = build_fetcher(fetcher_name)
    with fetcher:
        result = pipeline.run(fetcher, test_cfg, today=date.today())
    elapsed = time_mod.monotonic() - started

    note = "DRY-RUN" if args.dry_run else "実検索"
    message = build_message(result, elapsed, note)

    print("--- 送信する本文 ---")
    print(message)
    print("--------------------\n")

    notifier = build_notifier(notifier_name)
    try:
        notifier.send(message)
    except Exception as e:
        print(f"通知の送信に失敗しました: {e}")
        return 3

    if notifier_name == "line":
        print("LINEに送信しました。スマホで届いているか確認してください。")

    return 2 if result.all_failed else 0


if __name__ == "__main__":
    sys.exit(main())
