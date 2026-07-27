"""エントリポイント。

使い方:
    python -m flightdeal.main --status      実装状況（TODO一覧）を表示
    python -m flightdeal.main --dry-run     StubFetcher + コンソール通知で実行
    python -m flightdeal.main               config.json の設定どおりに実行

環境変数（要件4.4）:
    LINE_CHANNEL_ACCESS_TOKEN, LINE_TO_USER_ID
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from datetime import date

from .config import load_config
from .env import load_dotenv
from .fetchers import build_fetcher
from .logging_setup import setup_logging
from .notifiers import build_notifier

log = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="flightdeal", description="週末格安航空券 自動発見・通知")
    p.add_argument("--config", default=None, help="config.json のパス")
    p.add_argument("--dry-run", action="store_true", help="StubFetcher + コンソール通知で実行")
    p.add_argument("--today", default=None, help="基準日を上書き (YYYY-MM-DD)。週末算出のテスト用")
    p.add_argument("--status", action="store_true", help="実装状況（TODO一覧）を表示して終了")
    p.add_argument(
        "--fail-route",
        action="append",
        default=[],
        metavar="HND-HIJ",
        help="ドライラン時に指定区間を意図的に失敗させる（障害系の手動テスト用。複数指定可）",
    )
    p.add_argument(
        "--test-notify",
        action="store_true",
        help="検索せずテストメッセージだけ送る（LINE疎通確認用）",
    )
    p.add_argument("--verbose", action="store_true")
    return p


TEST_MESSAGE = (
    "【テスト送信】週末格安航空券システム\n"
    "この通知が届いていれば、LINEへの送信経路は正常です。\n"
    "（検索は実行していません）"
)


def send_test_notification(cfg, notifier_name: str) -> int:
    """通知経路だけを確認する（要件2 Phase 2 の 2-4 用）。"""
    notifier = build_notifier(notifier_name)
    try:
        notifier.send(TEST_MESSAGE)
    except Exception as e:
        log.error("test_notify_failed", extra={"notifier": notifier_name, "error": str(e)})
        print(f"\n送信に失敗しました: {e}")
        return 2

    log.info("test_notify_sent", extra={"notifier": notifier_name})
    print(f"\n{notifier_name} への送信に成功しました。")
    return 0


def print_status(config_path: str | None) -> int:
    """骨組みの実装状況を一覧表示する（開発の進捗確認用）。"""
    from . import status

    print(status.render(config_path))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(logging.DEBUG if args.verbose else logging.INFO)

    # .env があれば読み込む（既存の環境変数=GitHub Secrets が優先。要件4.4）
    load_dotenv()

    if args.status:
        return print_status(args.config)

    try:
        cfg = load_config(args.config)
    except (ValueError, KeyError, OSError) as e:
        # 設定ミスは検索を始める前に、読める形で止める（要件4.5）
        log.error("config_invalid", extra={"error": str(e)})
        print(f"\n設定ファイルに問題があります: {e}")
        print("config.json を確認してください（docs/テスト手順.md T4-4 参照）。")
        return 2

    fetcher_name = "stub" if args.dry_run else cfg.fetcher
    notifier_name = "console" if args.dry_run else cfg.notifier

    if args.test_notify:
        return send_test_notification(cfg, notifier_name)

    if args.fail_route and fetcher_name != "stub":
        print("--fail-route は --dry-run（StubFetcher）との併用時のみ有効です。")
        return 2

    if args.dry_run:
        # 外部サイトへ接続しないため、負荷抑制の待機は不要（要件4.3の対象外）
        cfg = replace(
            cfg, search=replace(cfg.search, sleep_between_searches=(0, 0), retry_wait_seconds=0)
        )

    today = date.fromisoformat(args.today) if args.today else date.today()

    log.info(
        "run_start",
        extra={
            "fetcher": fetcher_name,
            "notifier": notifier_name,
            "routes": [d.iata for d in cfg.enabled_destinations],
            "weekends_ahead": cfg.weekends_ahead,
            "today": today.isoformat(),
        },
    )

    from . import formatter, pipeline

    fetcher = build_fetcher(fetcher_name)
    if args.fail_route:
        fetcher.fail_routes = set(args.fail_route)  # StubFetcher のみ（上でガード済み）
        log.warning("failure_injected", extra={"segments": sorted(fetcher.fail_routes)})

    with fetcher:
        result = pipeline.run(fetcher, cfg, today=today)

    notifier = build_notifier(notifier_name)

    if result.all_failed:
        # 要件4.3: サイレント障害防止
        notifier.send(formatter.format_failure(result))
        log.error("run_all_failed", extra={"routes": len(result.results)})
        return 2

    body = formatter.format_run(result)
    if not body:
        log.info("run_no_deal", extra={"elapsed": result.elapsed_seconds})
        return 0

    notifier.send(body)
    log.info(
        "run_done",
        extra={"notified": len(result.notifiable), "elapsed": result.elapsed_seconds},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
