"""通知本文の組み立てのテスト（要件3.6）。"""

from __future__ import annotations

from datetime import date

from flightdeal import formatter
from flightdeal.models import Rank, RouteConfig, RouteResult, RunResult

from .conftest import AUG1, AUG8, HIJ, MYJ, make_combination, make_flight


def test_format_date_range():
    assert formatter.format_date_range(date(2026, 8, 1), date(2026, 8, 2)) == "8/1(土)〜8/2(日)"


def test_oneway_url_points_to_google_flights():
    from flightdeal.search_link import oneway_url

    url = oneway_url("HND", "HIJ", date(2026, 8, 1))
    assert url.startswith("https://www.google.com/travel/flights?")
    # fast-flights があれば tfs、無ければ自然言語クエリにフォールバック。両対応。
    assert ("tfs=" in url) or ("HND" in url and "HIJ" in url and "2026-08-01" in url)


def test_format_combination_has_all_required_fields():
    """要件3.6: リンクが切れても本文だけで予約行動に移れる情報量。"""
    combo = make_combination(
        total=22800,
        rank=Rank.S,
        outbound=make_flight(airline="ANA", dep="07:25", arr="08:50", price=11400),
        inbound=make_flight(
            airline="ANA", dep="19:05", arr="20:30", price=11400,
            origin="HIJ", destination="HND",
        ),
    )
    text = formatter.format_combination(combo)

    assert "【S】羽田⇔広島 8/1(土)〜8/2(日)" in text
    assert "実質 ￥22,800" in text
    assert "相場 ￥35,000" in text
    assert "▲35%" in text
    assert "往路 8/1: ANA 07:25発 → 08:50着（片道 ￥11,400）" in text
    assert "復路 8/2: ANA 19:05発 → 20:30着（片道 ￥11,400）" in text
    assert "補正: なし（FSC）" in text
    assert "往路検索: https://www.google.com/travel/flights?" in text
    assert "復路検索: https://www.google.com/travel/flights?" in text


def test_format_combination_notes_provisional_surcharge():
    """判定不能な航空会社を含む場合は「補正額は仮」と明記する（要件3.4）。"""
    combo = make_combination(
        total=30000,
        rank=Rank.B,
        outbound=make_flight(airline="Toki Air", price=9000),
        out_sc=3500,
        provisional=True,
    )
    text = formatter.format_combination(combo)
    assert "往路+￥3,500" in text
    assert "仮" in text


def test_format_run_empty_returns_empty_string():
    assert formatter.format_run(RunResult()) == ""


def test_format_run_aggregates_and_appends_footer():
    result = RunResult()
    rr = RouteResult(route=HIJ, weekend=AUG1)
    rr.combinations = [
        make_combination(total=26000, rank=Rank.A),
        make_combination(total=22800, rank=Rank.S),
    ]
    result.results.append(rr)

    text = formatter.format_run(result)
    assert "2件" in text
    # 安い順に並ぶ
    assert text.index("￥22,800") < text.index("￥26,000")
    assert text.rstrip().endswith("確認してください。")


def test_format_failure_lists_routes_and_next_action():
    result = RunResult()
    rr = RouteResult(route=HIJ, weekend=AUG1)
    rr.error = "HND-HIJ 2026-08-01 の取得に3回失敗しました: timeout"
    result.results.append(rr)

    text = formatter.format_failure(result)
    assert "広島" in text
    assert "3日連続" in text
    assert "ローカル実行" in text


def test_split_message_no_split_when_within_limit():
    assert formatter.split_message("abc", 100) == ["abc"]


def test_split_message_keeps_blocks_intact():
    blocks = [f"ブロック{i}\n" + "x" * 40 for i in range(10)]
    text = formatter.BLOCK_SEPARATOR.join(blocks)
    chunks = formatter.split_message(text, 150)

    assert len(chunks) > 1
    assert all(len(c) <= 150 for c in chunks)
    # 分割してもブロックは途中で切れない
    rejoined = formatter.BLOCK_SEPARATOR.join(chunks)
    assert rejoined == text


def test_split_message_hard_splits_oversized_block():
    text = "y" * 250
    chunks = formatter.split_message(text, 100)
    assert [len(c) for c in chunks] == [100, 100, 50]


def test_format_run_respects_max_total_and_says_omitted():
    """上限で省略したら「他N件」と明記する（黙って捨てない）。"""
    result = RunResult()
    rr = RouteResult(route=HIJ, weekend=AUG1)
    rr.combinations = [make_combination(total=t, rank=Rank.A) for t in (30000, 22000, 26000)]
    result.results.append(rr)

    text = formatter.format_run(result, max_total=2)
    assert "他 1件" in text
    assert "￥22,000" in text
    assert "￥30,000" not in text  # 上限で外れた分は載らない


def test_format_run_sorted_cheapest_first():
    result = RunResult()
    rr = RouteResult(route=HIJ, weekend=AUG1)
    rr.combinations = [make_combination(total=t, rank=Rank.A) for t in (30000, 22000)]
    result.results.append(rr)

    text = formatter.format_run(result)
    assert text.index("￥22,000") < text.index("￥30,000")


def _no_deal_result(*specs):
    """(route, weekend, cheapest, error) から RunResult を作る。"""
    result = RunResult()
    for route, weekend, cheapest, error in specs:
        rr = RouteResult(route=route, weekend=weekend)
        rr.cheapest_total = cheapest
        rr.error = error
        result.results.append(rr)
    return result


def test_no_deal_message_states_search_succeeded():
    """0件でも「検索は正常」と伝える（止まっているのと区別できるように）。"""
    result = _no_deal_result((HIJ, AUG1, 43270, None), (MYJ, AUG1, 66570, None))
    msg = formatter.format_no_deal(result)

    assert "【該当なし】" in msg
    assert "検索は正常に完了" in msg
    assert "2件すべて成功" in msg
    assert "8/1(土)〜8/2(日)" in msg


def test_no_deal_lists_closest_routes_with_gap():
    """相場との差が分かる（あと少しなのか、かけ離れているのか）。"""
    result = _no_deal_result((HIJ, AUG1, 43270, None), (MYJ, AUG1, 66570, None))
    msg = formatter.format_no_deal(result)

    assert "￥43,270" in msg
    assert "￥35,000" in msg
    assert "+24%" in msg          # 43270/35000 → 約+24%
    # 相場に近い順（広島のほうが近い）
    assert msg.index("広島") < msg.index("松山")


def test_no_deal_dedupes_by_route():
    """同じ路線が週末ぶん重複しない（最良の1件だけ）。"""
    result = _no_deal_result(
        (HIJ, AUG1, 50000, None),
        (HIJ, AUG8, 43270, None),   # こちらのほうが相場に近い
    )
    msg = formatter.format_no_deal(result)

    assert msg.count("広島") == 1
    assert "￥43,270" in msg
    assert "￥50,000" not in msg


def test_no_deal_reports_partial_failures():
    result = _no_deal_result((HIJ, AUG1, 43270, None), (MYJ, AUG1, None, "取得失敗"))
    msg = formatter.format_no_deal(result)
    assert "失敗1" in msg


def test_no_deal_when_time_filter_leaves_nothing():
    """時間帯条件で全滅した場合は原因の候補を示す。"""
    result = _no_deal_result((HIJ, AUG1, None, None))
    msg = formatter.format_no_deal(result)
    assert "time_filter" in msg


def test_no_deal_fits_one_line_message():
    """43路線でもLINE1通に収まる。"""
    specs = []
    for i in range(43):
        route = RouteConfig(iata=f"X{i:02d}", name=f"空港{i}", market_price=40000,
                            max_price=34000, enabled=True)
        specs.append((route, AUG1, 45000 + i * 100, None))
    msg = formatter.format_no_deal(_no_deal_result(*specs))
    assert len(formatter.split_message(msg)) == 1
