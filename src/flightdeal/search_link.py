"""Google Flights の検索リンク生成（要件3.6 / P5）。

本システムは片道分解方式（要件3.2.1）で価格を算出する。したがって検索リンクも
**片道検索**を指すべきである。往復の自然言語クエリ（?q=...）はGoogleが復路日を
勝手に補完してしまい（例: 土曜発なのに4日後帰着の往復を表示）、本文の計算と
食い違う。これを避けるため、fast-flights が生成する tfs パラメータで
「その片道・その日付・直行便のみ」を正確に指すURLを作る。

tfs URL は Phase 0 で実際に取得に成功したものと同一なので、クリックすれば
本文に出したのと同じ片道便が表示される。

fast-flights が使えない環境（純粋なドライラン等）では自然言語クエリに
フォールバックする。リンクはあくまで補助であり、本文だけで予約行動に移れる
情報量を担保しているため（要件3.6）、フォールバックでも実害はない。
"""

from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

BASE = "https://www.google.com/travel/flights"


def oneway_url(origin: str, destination: str, flight_date: date) -> str:
    """指定した片道・日付・直行便の検索URLを返す。"""
    try:
        return _tfs_oneway_url(origin, destination, flight_date)
    except Exception:
        # フォールバック: 自然言語クエリ（fast-flights 未導入時など）
        query = urlencode(
            {"hl": "ja", "curr": "JPY", "q": f"{origin} to {destination} {flight_date.isoformat()}"}
        )
        return f"{BASE}?{query}"


def _tfs_oneway_url(origin: str, destination: str, flight_date: date) -> str:
    from fast_flights import FlightQuery, Passengers, create_filter

    q = create_filter(
        flights=[
            FlightQuery(
                date=flight_date.isoformat(),
                from_airport=origin,
                to_airport=destination,
                max_stops=0,
            )
        ],
        trip="one-way",
        seat="economy",
        passengers=Passengers(adults=1),
        currency="JPY",
        language="ja",
    )
    return f"{BASE}?{urlencode(q.params())}"
