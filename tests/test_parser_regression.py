"""保存済み実HTMLによるパーサ回帰テスト（要件6.2）。

外部サイトへは接続しない。Phase 0 で採取した実レスポンスを入力に、
fast-flights の parser + 本システムのマッピングが期待どおり動くかを検証する。

HTMLの採取:
    python scripts/phase0_check.py --dest HIJ --save-raw

採取していない環境（CI初期・fast-flights未導入）では自動的にスキップされる。
Google側の構造が変わったときに、ここが最初に落ちて気づけるのが狙い。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from flightdeal.fetchers.fast_flights_fetcher import flights_to_flight

RAW_DIR = Path(__file__).resolve().parent / "fixtures" / "raw"


def _raw_files() -> list[Path]:
    return sorted(RAW_DIR.glob("*.html")) if RAW_DIR.is_dir() else []


def _parse_or_skip(path: Path):
    try:
        from fast_flights.parser import parse
    except ImportError:
        pytest.skip("fast-flights 未導入のためスキップ")
    return parse(path.read_text(encoding="utf-8"))


def _meta_from_name(path: Path) -> tuple[str, str, date]:
    """HND-HIJ-2026-08-01.html -> ('HND', 'HIJ', date(2026,8,1))"""
    origin, dest, iso = path.stem.split("-", 2)
    return origin, dest, date.fromisoformat(iso)


def test_raw_fixture_parses():
    """保存済みHTMLが解析でき、便が1件以上取れること。"""
    files = _raw_files()
    if not files:
        pytest.skip(
            "実HTML未採取。`python scripts/phase0_check.py --dest HIJ --save-raw` で採取できます"
        )

    for path in files:
        result = _parse_or_skip(path)
        assert len(result) > 0, f"{path.name}: 便が0件"


def test_raw_fixture_maps_to_flight():
    """解析結果が Flight に変換でき、必須項目が揃うこと。"""
    files = _raw_files()
    if not files:
        pytest.skip("実HTML未採取")

    for path in files:
        origin, dest, flight_date = _meta_from_name(path)
        result = _parse_or_skip(path)

        flights = [
            f for f in (flights_to_flight(p, origin, dest, flight_date) for p in result)
            if f is not None
        ]
        assert flights, f"{path.name}: 全件が変換不能（パーサのマッピングずれ）"

        for f in flights:
            assert f.airline, "航空会社名が空"
            assert f.price > 0, "価格が不正"
            assert f.origin == origin and f.destination == dest
            assert f.flight_date == flight_date


def test_raw_fixture_is_not_flagged_as_blocked():
    """実際に取得成功したHTMLがBot判定扱いにならないこと（誤検知の回帰防止）。

    2026-07-29 に "recaptcha" と「を確認しています」で誤検知し、
    IPを変えても全滅する障害が起きた。実物のHTMLで再発を防ぐ。
    """
    from flightdeal.fetchers.fast_flights_fetcher import looks_blocked

    files = _raw_files()
    if not files:
        pytest.skip("実HTML未採取")

    for path in files:
        html = path.read_text(encoding="utf-8")
        assert looks_blocked(200, html) is False, f"{path.name} が誤ってブロック判定された"


def test_raw_fixture_prices_are_plausible_jpy():
    """価格が日本の国内線片道として妥当なレンジか（通貨取り違えの検知）。"""
    files = _raw_files()
    if not files:
        pytest.skip("実HTML未採取")

    for path in files:
        origin, dest, flight_date = _meta_from_name(path)
        result = _parse_or_skip(path)
        prices = [
            f.price for f in (flights_to_flight(p, origin, dest, flight_date) for p in result)
            if f is not None
        ]
        assert prices
        # USD等で返ってくると3桁になる。JPYなら概ね4〜6桁。
        assert min(prices) >= 3_000, f"{path.name}: 価格が安すぎる（通貨がJPYでない可能性）"
        assert max(prices) <= 500_000, f"{path.name}: 価格が高すぎる"
