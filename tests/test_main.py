"""CLI のテスト。外部接続は行わない（すべて --dry-run 経路）。"""

from __future__ import annotations

import json

from flightdeal.main import main

from .conftest import test_config_dict


def _write_cfg(tmp_path, **overrides):
    raw = test_config_dict()
    raw.update(overrides)
    path = tmp_path / "c.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return str(path)


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
    cfg = _write_cfg(tmp_path, fetcher="fast_flights")
    assert main(["--config", cfg, "--fail-route", "HND-HIJ"]) == 2


def test_invalid_config_exits_two(tmp_path):
    """設定ミスは検索前に読める形で止まる（要件4.5）。"""
    cfg = _write_cfg(tmp_path, rank_thresholds={"S": 0.90, "A": 0.85})
    assert main(["--dry-run", "--config", cfg]) == 2


def test_no_deal_exits_zero(tmp_path):
    """該当便0件は正常終了（通知しないのが仕様。要件3.6）。"""
    raw = test_config_dict()
    for d in raw["destinations"]:
        d["market_price"] = 1000  # どの便も相場を超える
        d["max_price"] = 900
    path = tmp_path / "nodeal.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    assert main(["--dry-run", "--today", "2026-07-27", "--config", str(path)]) == 0
