"""取得層のテスト。

外部サイトへ接続するテストは書かない（要件6.2: CIの合否条件に含めない）。
実取得の検証は Phase 0 で手元PCの scripts/phase0_check.py により行う。
"""

from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest

from flightdeal.fetchers import FetchError, build_fetcher
from types import SimpleNamespace

from flightdeal.fetchers.fast_flights_fetcher import (
    FastFlightsFetcher,
    flights_to_flight,
    parse_flights_html,
    to_time,
)
from flightdeal.fetchers.stub import FixtureFetcher, StubFetcher


def test_build_fetcher_stub():
    assert isinstance(build_fetcher("stub"), StubFetcher)


def test_build_fetcher_unknown():
    with pytest.raises(ValueError):
        build_fetcher("nope")


def test_build_fetcher_playwright_not_implemented():
    with pytest.raises(NotImplementedError):
        build_fetcher("playwright")


def test_stub_returns_flights():
    flights = StubFetcher().fetch("HND", "HIJ", date(2026, 8, 1))
    assert len(flights) == 3
    assert all(f.price > 0 for f in flights)
    assert all(f.origin == "HND" and f.destination == "HIJ" for f in flights)


def test_stub_route_isolation():
    """意図的失敗を注入できること（要件4.3 の動作確認用）。"""
    fetcher = StubFetcher(fail_routes={"HND-HIJ"})
    with pytest.raises(FetchError):
        fetcher.fetch("HND", "HIJ", date(2026, 8, 1))
    # 別路線は影響を受けない
    assert fetcher.fetch("HND", "MYJ", date(2026, 8, 1))


def test_fixture_fetcher_missing_file(tmp_path):
    with pytest.raises(FetchError):
        FixtureFetcher(fixture_dir=tmp_path).fetch("HND", "HIJ", date(2026, 8, 1))


def test_fixture_fetcher_reads_saved_response():
    """Phase 0 で保存した実レスポンスのパース回帰テスト（要件6.2）。"""
    flights = FixtureFetcher().fetch("HND", "HIJ", date(2026, 8, 1))
    assert flights
    assert flights[0].airline


# --- fast-flights 3.x のパース部（外部接続なし） ---
# fast-flights の SingleFlight / Flights を模した最小の互換オブジェクトで検証する。
# 実データ構造（Phase 0 2026-07 実測）:
#   Flights(price=int, airlines=['ANA'], type='NH', flights=[SingleFlight(...)])
#   SingleFlight.departure.time = [時, 分]（分=0のとき [時]）


def _seg(dep, arr, frm="HND", to="HIJ"):
    return SimpleNamespace(
        departure=SimpleNamespace(time=dep, date=[2026, 8, 1]),
        arrival=SimpleNamespace(time=arr, date=[2026, 8, 1]),
        from_airport=SimpleNamespace(code=frm),
        to_airport=SimpleNamespace(code=to),
    )


def _parsed(price=20590, airlines=("ANA",), segments=None, type_="NH"):
    return SimpleNamespace(
        price=price,
        airlines=list(airlines),
        type=type_,
        flights=segments if segments is not None else [_seg([8, 45], [10, 5])],
    )


@pytest.mark.parametrize(
    "parts,expected",
    [
        ([18, 10], time(18, 10)),
        ([8, 45], time(8, 45)),
        ([21], time(21, 0)),      # 分=0 は1要素
        ([13], time(13, 0)),
        ([0, 5], time(0, 5)),
    ],
)
def test_to_time(parts, expected):
    assert to_time(parts) == expected


@pytest.mark.parametrize("bad", [[], None, "18:10", [25, 0], [12, 70]])
def test_to_time_invalid(bad):
    with pytest.raises(ValueError):
        to_time(bad)


def test_flights_to_flight_maps_fields():
    parsed = _parsed(price=20590, airlines=("ANA",), segments=[_seg([18, 10], [19, 35])])
    flight = flights_to_flight(parsed, "HND", "HIJ", date(2026, 8, 1))

    assert flight is not None
    assert flight.airline == "ANA"
    assert flight.depart_time == time(18, 10)
    assert flight.arrive_time == time(19, 35)
    assert flight.price == 20590
    assert flight.flight_number is None


def test_flights_to_flight_handles_zero_minute():
    parsed = _parsed(segments=[_seg([19, 40], [21])])  # 21:00 が [21]
    flight = flights_to_flight(parsed, "HND", "HIJ", date(2026, 8, 1))
    assert flight.arrive_time == time(21, 0)


def test_flights_to_flight_excludes_connecting():
    """2区間（乗り継ぎ）は直行便でないので除外（要件3.1）。"""
    parsed = _parsed(segments=[_seg([7, 25], [9, 0]), _seg([9, 40], [11, 50])])
    assert flights_to_flight(parsed, "HND", "HIJ", date(2026, 8, 1)) is None


def test_flights_to_flight_excludes_missing_price():
    parsed = _parsed(price=None, segments=[_seg([8, 45], [10, 5])])
    assert flights_to_flight(parsed, "HND", "HIJ", date(2026, 8, 1)) is None


def test_flights_to_flight_falls_back_to_type_when_no_airline_name():
    parsed = _parsed(airlines=(), type_="NH", segments=[_seg([8, 45], [10, 5])])
    flight = flights_to_flight(parsed, "HND", "HIJ", date(2026, 8, 1))
    assert flight is not None
    assert flight.airline == "NH"


def test_looks_blocked_by_status():
    from flightdeal.fetchers.fast_flights_fetcher import looks_blocked

    assert looks_blocked(429, "") is True
    assert looks_blocked(403, "") is True
    assert looks_blocked(200, "<html>flights</html>") is False


def test_looks_blocked_by_markers():
    from flightdeal.fetchers.fast_flights_fetcher import looks_blocked

    assert looks_blocked(200, "Our systems have detected unusual traffic from your network") is True
    assert looks_blocked(200, "通常と異なるトラフィックが検出されました") is True
    assert looks_blocked(200, "普通の検索結果ページです") is False


def test_looks_blocked_not_fooled_by_normal_page_noise():
    """実測で誤検知した文言（2026-07-29）が正常ページ扱いのままであること。

    Googleの正常ページには "/recaptcha/challenge"（JSルート定義）や
    「複数のソースから価格を確認しています」（ローディング文言）が含まれる。
    これらでブロック判定してはならない。
    """
    from flightdeal.fetchers.fast_flights_fetcher import looks_blocked

    normal = (
        '<script class="ds:1">data</script>'
        '"/recaptcha/challenge","/recaptcha/challenge/*"'
        "複数のソースから価格を確認しています..."
    )
    assert looks_blocked(200, normal) is False


def test_looks_blocked_marker_with_data_is_not_blocked():
    """ブロック文言らしきものがあっても、検索結果データ(ds:1)があれば正常扱い。"""
    from flightdeal.fetchers.fast_flights_fetcher import looks_blocked

    text = '<script class="ds:1">x</script> unusual traffic from your computer'
    assert looks_blocked(200, text) is False


def test_synthesized_stub_covers_unknown_routes():
    """20空港のドライラン用: _SAMPLE に無い区間も便を返す。"""
    flights = StubFetcher().fetch("HND", "WKJ", date(2026, 8, 1))  # 稚内
    assert flights
    assert all(f.price > 0 for f in flights)
    # 決定的（同じ区間なら同じ結果）
    again = StubFetcher().fetch("HND", "WKJ", date(2026, 8, 1))
    assert [f.price for f in flights] == [f.price for f in again]


def test_synthesize_can_be_disabled():
    with pytest.raises(FetchError):
        StubFetcher(synthesize=False).fetch("HND", "WKJ", date(2026, 8, 1))


def test_import_failure_message_includes_real_cause():
    """「未インストール」と決めつけず、実際の例外内容を出すこと。

    ImportError を握りつぶして固定文言にすると、
    「古い版が入っている」「依存の初期化に失敗」といった別原因を追えなくなる。
    """
    from flightdeal.fetchers.fast_flights_fetcher import import_failure_message

    msg = import_failure_message(ImportError("cannot import name 'FlightQuery'"))

    assert "ImportError" in msg
    assert "cannot import name 'FlightQuery'" in msg  # 本当の原因が残る
    assert "3.x" in msg                                # 対処のヒント


def test_parser_skips_unpriced_rows_without_losing_priced_flights():
    """価格なしの表示行が混ざっても、同じページの価格付き便を取得する。"""
    import copy
    import json
    from pathlib import Path

    from fast_flights.parser import parse
    from selectolax.lexbor import LexborHTMLParser

    raw = (
        Path(__file__).parent / "fixtures" / "raw" / "HND-HIJ-2026-08-01.html"
    ).read_text(encoding="utf-8")
    baseline, baseline_skipped = parse_flights_html(raw)
    assert baseline_skipped == 0

    document = LexborHTMLParser(raw)
    script = document.css_first(r"script.ds\:1")
    assert script is not None
    original_js = script.text()
    payload = json.loads(original_js.split("data:", 1)[1].rsplit(",", 1)[0])

    unpriced = copy.deepcopy(payload[3][0][0])
    unpriced[1] = [[], "no-price-token"]
    payload[3][0].append(unpriced)
    broken_js = "data:" + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ) + ","
    broken_html = raw.replace(original_js, broken_js, 1)

    with pytest.raises(IndexError):
        parse(broken_html)

    result, skipped = parse_flights_html(broken_html)
    assert skipped == 1
    assert len(result) == len(baseline)


# --- おすすめ欄・エラー応答の扱い（2026-11 修正） ---------------------------------

RAW_HIJ = Path(__file__).parent / "fixtures" / "raw" / "HND-HIJ-2026-08-01.html"


def _load_raw_payload():
    import json

    from selectolax.lexbor import LexborHTMLParser

    raw = RAW_HIJ.read_text(encoding="utf-8")
    js = LexborHTMLParser(raw).css_first(r"script.ds\:1").text()
    payload = json.loads(js.split("data:", 1)[1].rsplit(",", 1)[0])
    return raw, js, payload


def _html_with_payload(raw, original_js, payload):
    import json

    new_js = "data:" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ","
    return raw.replace(original_js, new_js, 1)


def test_parser_reads_recommended_section():
    """「おすすめの便」欄（payload[2]）の便も取得する。

    fast-flights 3.0.2 の parse は payload[3]（その他の便）しか読まない。
    最安便がおすすめ欄にしか無いことがあるため、両欄を読む必要がある。
    """
    from fast_flights.parser import parse

    raw, _, payload = _load_raw_payload()
    recommended = len(payload[2][0])
    others = len(payload[3][0])
    assert recommended > 0  # 前提: フィクスチャにおすすめ欄がある

    upstream = list(parse(raw))
    result, skipped = parse_flights_html(raw)

    assert len(upstream) == others
    assert len(result) == recommended + others
    assert skipped == 0


def test_parser_handles_only_recommended_section():
    """「その他」欄が None（おすすめ欄だけ）のページでも落ちない。"""
    raw, js, payload = _load_raw_payload()
    recommended = len(payload[2][0])
    payload[3] = None

    result, _ = parse_flights_html(_html_with_payload(raw, js, payload))
    assert len(result) == recommended


def test_parser_returns_empty_when_no_flights():
    """両欄とも空なら便なし（[]）。解析失敗の例外にはしない。"""
    raw, js, payload = _load_raw_payload()
    payload[2] = None
    payload[3] = None

    result, skipped = parse_flights_html(_html_with_payload(raw, js, payload))
    assert result == []
    assert skipped == 0


def test_parser_deduplicates_same_flight_keeping_cheaper():
    """同じ便が両欄に載っていたら1件にまとめ、安いほうを残す。"""
    import copy

    raw, js, payload = _load_raw_payload()
    total = len(payload[2][0]) + len(payload[3][0])
    duplicate = copy.deepcopy(payload[2][0][0])
    original_price = duplicate[1][0][1]
    duplicate[1][0][1] = original_price - 1000
    payload[3][0].append(duplicate)

    result, _ = parse_flights_html(_html_with_payload(raw, js, payload))
    assert len(result) == total
    assert min(f.price for f in result) <= original_price - 1000


def test_parser_raises_on_google_error_response():
    """errorHasStatus は「便なし」ではなく、リトライ対象のエラーとして扱う。"""
    from flightdeal.fetchers import GoogleErrorResponse

    raw, js, _ = _load_raw_payload()
    broken = raw.replace(js, "data:[null],errorHasStatus: true,", 1)

    with pytest.raises(GoogleErrorResponse):
        parse_flights_html(broken)


def test_fetch_propagates_google_error_as_fetch_error(monkeypatch):
    """fetch() はエラー応答を0件として返さず、FetchError（リトライ対象）にする。"""
    from flightdeal.fetchers import GoogleErrorResponse

    raw, js, _ = _load_raw_payload()
    broken = raw.replace(js, "data:[null],errorHasStatus: true,", 1)

    fetcher = FastFlightsFetcher()
    monkeypatch.setattr(fetcher, "fetch_html", lambda *a, **k: broken)

    with pytest.raises(GoogleErrorResponse) as excinfo:
        fetcher.fetch("FUK", "HND", date(2026, 11, 22))
    assert isinstance(excinfo.value, FetchError)
    assert "FUK-HND" in str(excinfo.value)


def test_fetch_returns_empty_list_when_no_flights(monkeypatch):
    """本当に便が無い区間は、エラーではなく0件を返す。"""
    raw, js, payload = _load_raw_payload()
    payload[2] = None
    payload[3] = None
    empty = _html_with_payload(raw, js, payload)

    fetcher = FastFlightsFetcher()
    monkeypatch.setattr(fetcher, "fetch_html", lambda *a, **k: empty)

    assert fetcher.fetch("HND", "HNA", date(2026, 11, 21)) == []
    assert fetcher.last_excluded == 0
