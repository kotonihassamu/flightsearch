"""通しテスト（smoke_test.py）のメッセージ組み立ての検証。

外部接続・LINE送信はしない。build_message の分岐だけを確認する。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import smoke_test  # noqa: E402
from flightdeal.models import RouteResult, RunResult  # noqa: E402

from .conftest import AUG1, HIJ, MYJ, make_combination  # noqa: E402


def _result_with(*route_results) -> RunResult:
    r = RunResult()
    r.results.extend(route_results)
    return r


def test_message_reports_prices_when_no_deals():
    rr = RouteResult(route=HIJ, weekend=AUG1)
    rr.outbound_count = 12
    rr.inbound_count = 10
    rr.cheapest_total = 43270
    result = _result_with(rr)

    msg = smoke_test.build_message(result, 18.0, "実検索")

    assert "通しテスト" in msg
    assert "広島" in msg
    assert "往路12/復路10便" in msg
    assert "￥43,270" in msg
    assert "0件" in msg
    assert "全て正常です" in msg


def test_message_lists_deals():
    rr = RouteResult(route=HIJ, weekend=AUG1)
    rr.cheapest_total = 22000
    rr.combinations = [make_combination(total=22000)]
    result = _result_with(rr)

    msg = smoke_test.build_message(result, 5.0, "実検索")
    assert "お得な便（ランク入り）: 1件" in msg
    assert "￥22,000" in msg


def test_message_when_all_failed():
    rr = RouteResult(route=HIJ, weekend=AUG1)
    rr.error = "Bot判定/アクセス制限を検知"
    result = _result_with(rr)

    msg = smoke_test.build_message(result, 9.0, "実検索")
    assert "全路線で取得失敗" in msg
    # 全滅時に「相場より高いだけ」の誤解を招く行を出さない
    assert "相場設定より高いだけ" not in msg
    # 通知経路が正常な証拠であることは伝える
    assert "通知経路が正常" in msg


def test_message_partial_failure():
    ok = RouteResult(route=HIJ, weekend=AUG1)
    ok.outbound_count = 5
    ok.inbound_count = 5
    ok.cheapest_total = 40000
    ng = RouteResult(route=MYJ, weekend=AUG1)
    ng.error = "取得失敗"
    result = _result_with(ok, ng)

    msg = smoke_test.build_message(result, 12.0, "実検索")
    assert "✗ 松山" in msg
    assert "広島" in msg
    assert "全て正常です" in msg  # 一部失敗は「全滅」ではない
