"""CLI のテスト。外部接続は行わない（すべて --dry-run 経路）。"""

from __future__ import annotations

import json

from flightdeal.main import main

ROOT_CONFIG = str(__import__("pathlib").Path(__file__).resolve().parents[1] / "config.json")


def test_status_exits_zero():
    assert main(["--status"]) == 0


def test_dry_run_exits_zero():
    assert main(["--dry-run", "--today", "2026-07-27"]) == 0


def test_test_notify_via_console():
    assert main(["--dry-run", "--test-notify"]) == 0


def test_fail_route_isolated_still_succeeds():
    """1路線だけ失敗しても全体は成功扱い（要件4.3）。"""
    assert main(["--dry-run", "--today", "2026-07-27", "--fail-route", "HND-HIJ"]) == 0


def test_all_routes_failed_exits_two():
    """全路線失敗は異常終了。CIを赤くする（要件4.3）。"""
    code = main(
        [
            "--dry-run",
            "--today",
            "2026-07-27",
            "--fail-route",
            "HND-HIJ",
            "--fail-route",
            "HND-MYJ",
        ]
    )
    assert code == 2


def test_fail_route_rejected_for_real_fetcher(tmp_path):
    """実取得フェッチャには失敗注入できない（StubFetcher 専用の機能）。"""
    raw = json.loads(open(ROOT_CONFIG, encoding="utf-8").read())
    raw["fetcher"] = "fast_flights"
    cfg = tmp_path / "real.json"
    cfg.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    assert main(["--config", str(cfg), "--fail-route", "HND-HIJ"]) == 2


def test_invalid_config_exits_two(tmp_path):
    """設定ミスは検索前に読める形で止まる（要件4.5）。"""
    raw = json.loads(open(ROOT_CONFIG, encoding="utf-8").read())
    raw["rank_thresholds"] = {"S": 0.90, "A": 0.85}
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    assert main(["--dry-run", "--config", str(bad)]) == 2


def test_no_deal_exits_zero(tmp_path):
    """該当便0件は正常終了（通知しないのが仕様。要件3.6）。"""
    raw = json.loads(open(ROOT_CONFIG, encoding="utf-8").read())
    for d in raw["destinations"]:
        d["market_price"] = 1000  # どの便も相場を超える
        d["max_price"] = 900
    cfg = tmp_path / "nodeal.json"
    cfg.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    assert main(["--dry-run", "--today", "2026-07-27", "--config", str(cfg)]) == 0
