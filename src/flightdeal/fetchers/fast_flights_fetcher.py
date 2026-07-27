"""優先度1: fast-flights を用いた取得実装（要件3.2.2）。

【重要】fast-flights 3.x の内部HTTPクライアント（primp）は環境依存で
DNS "Query Refused" になることがある（独自DNSリゾルバを使うため）。
本実装は **取得を requests で行い、解析だけ fast-flights の parser に任せる**
ことで primp を完全に回避する。Phase 0 の実機検証（2026-07）でこの方式に確定。

fast-flights 3.x の使い方（2系から全面変更されている）:
    from fast_flights import FlightQuery, Passengers, create_filter
    from fast_flights.parser import parse
    q = create_filter(flights=[FlightQuery(date, from_airport, to_airport, max_stops=0)],
                      trip="one-way", seat="economy", passengers=Passengers(adults=1),
                      currency="JPY", language="ja")
    params = q.params()                  # {'tfs': ..., 'hl': 'ja', 'curr': 'JPY'}
    html = requests.get(URL, params=params, headers=...).text
    result = parse(html)                 # ResultList[Flights]

解析結果 Flights の構造:
    .price     : int（例: 20590）
    .airlines  : list[str]（例: ['ANA']）
    .type      : str（航空会社コード。例: 'NH'）
    .flights   : list[SingleFlight]  区間。直行便は1件
        seg.departure.time : [時, 分]（分=0のとき [時] の1要素）
        seg.arrival.time   : 同上
        seg.from_airport.code / seg.to_airport.code
    便名は parser が取得しないため None とする（要件3.6は便名を任意扱い）。
"""

from __future__ import annotations

import logging
from datetime import date, time

from ..artifacts import save_debug
from ..models import Flight
from .base import FetchError, FlightFetcher

log = logging.getLogger(__name__)

URL = "https://www.google.com/travel/flights"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def to_time(parts: object) -> time:
    """[時, 分] または [時] を time に変換する。

    Googleの内部データは分が0のとき [21] のように1要素になる。

    Raises:
        ValueError: 時刻として解釈できない場合
    """
    if not isinstance(parts, (list, tuple)) or not parts:
        raise ValueError(f"時刻が空か不正です: {parts!r}")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 and parts[1] is not None else 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"時刻の値が範囲外です: {parts!r}")
    return time(hour, minute)


def flights_to_flight(
    parsed: object, origin: str, destination: str, flight_date: date
) -> Flight | None:
    """解析済み Flights を Flight に変換する。直行便でない/欠損なら None。

    純粋関数。テストではダミーの Flights 互換オブジェクトを渡して検証する。
    """
    segments = getattr(parsed, "flights", None)
    if not segments or len(segments) != 1:  # 直行便のみ（要件3.1）
        return None
    seg = segments[0]

    airlines = getattr(parsed, "airlines", None)
    airline = airlines[0] if airlines else getattr(parsed, "type", None)
    price = getattr(parsed, "price", None)
    if not airline or price is None:
        return None

    try:
        depart = to_time(getattr(seg.departure, "time", None))
        arrive = to_time(getattr(seg.arrival, "time", None))
        price_int = int(price)
    except (ValueError, TypeError, AttributeError):
        return None

    return Flight(
        origin=origin,
        destination=destination,
        flight_date=flight_date,
        airline=str(airline).strip(),
        depart_time=depart,
        arrive_time=arrive,
        price=price_int,
        flight_number=None,  # parser が取得しないため
    )


class FastFlightsFetcher(FlightFetcher):
    """fast-flights のクエリ生成＋parser を使い、取得は requests で行う。"""

    name = "fast_flights"

    def __init__(
        self,
        seat: str = "economy",
        currency: str = "JPY",
        language: str = "ja",
        max_stops: int = 0,
        timeout: int = 30,
    ) -> None:
        self.seat = seat
        self.currency = currency
        self.language = language
        self.max_stops = max_stops  # 0 = 直行便のみ（要件3.1）
        self.timeout = timeout
        self.last_excluded = 0
        self._session = None  # 遅延生成（import できない環境でも __init__ は通す）

    def _get_session(self):
        if self._session is None:
            try:
                import requests
            except ImportError as e:  # pragma: no cover
                raise FetchError(
                    "requests がインストールされていません。"
                    "`pip install -r requirements.txt` を実行してください。"
                ) from e
            self._session = requests.Session()
            self._session.headers.update(DEFAULT_HEADERS)
        return self._session

    def _build_params(self, origin: str, destination: str, flight_date: date) -> dict:
        try:
            from fast_flights import FlightQuery, Passengers, create_filter
        except ImportError as e:
            raise FetchError(
                "fast-flights がインストールされていません。"
                "`pip install -r requirements.txt` を実行してください。"
            ) from e

        q = create_filter(
            flights=[
                FlightQuery(
                    date=flight_date.isoformat(),
                    from_airport=origin,
                    to_airport=destination,
                    max_stops=self.max_stops,
                )
            ],
            trip="one-way",
            seat=self.seat,
            passengers=Passengers(adults=1),
            currency=self.currency,
            language=self.language,
        )
        return q.params()

    def fetch_html(self, origin: str, destination: str, flight_date: date) -> str:
        """検索結果のHTMLを取得する（解析はしない）。

        パーサ回帰テスト用のフィクスチャ採取にも使う（要件6.2）。
        取得は requests で行い primp を回避する。
        """
        params = self._build_params(origin, destination, flight_date)
        session = self._get_session()

        try:
            resp = session.get(URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
        except Exception as e:
            raise FetchError(
                f"取得に失敗しました ({origin}-{destination} {flight_date}): "
                f"{type(e).__name__}: {e}"
            ) from e

        return resp.text

    def fetch(self, origin: str, destination: str, flight_date: date) -> list[Flight]:
        try:
            from fast_flights.exceptions import FlightsNotFound
            from fast_flights.parser import parse
        except ImportError as e:
            raise FetchError(
                "fast-flights がインストールされていません。"
                "`pip install -r requirements.txt` を実行してください。"
            ) from e

        html = self.fetch_html(origin, destination, flight_date)
        label = f"{origin}-{destination}-{flight_date.isoformat()}"

        try:
            result = parse(html)
        except FlightsNotFound:
            # その日に便が無いのは異常ではない。空リストを返す。
            log.info(
                "no_flights",
                extra={"segment": f"{origin}-{destination}", "date": flight_date.isoformat()},
            )
            return []
        except Exception as e:
            # 解析失敗はGoogleの構造変化やBot判定ページの可能性。
            # 後から調査できるよう生HTMLを残す（要件4.3 失敗の可視化）。
            saved = save_debug(html, f"parse-failed_{label}")
            raise FetchError(
                f"解析に失敗しました ({origin}-{destination} {flight_date}): "
                f"{type(e).__name__}: {e}"
                "（Googleの仕様変更やBot判定ページの可能性"
                + (f"。生HTMLを保存: {saved}" if saved else "")
                + "）"
            ) from e

        flights: list[Flight] = []
        excluded = 0
        for parsed in result:
            flight = flights_to_flight(parsed, origin, destination, flight_date)
            if flight is None:
                excluded += 1
            else:
                flights.append(flight)

        self.last_excluded = excluded
        if excluded:
            log.info(
                "flights_excluded",
                extra={
                    "segment": f"{origin}-{destination}",
                    "date": flight_date.isoformat(),
                    "excluded": excluded,
                    "kept": len(flights),
                },
            )

        if excluded and not flights:
            # max_stops=0 で取得しているので、全件除外は解釈失敗のサイン。
            # 黙って0件を返すとサイレント障害になるため失敗として扱う（要件4.3）。
            saved = save_debug(html, f"all-excluded_{label}")
            raise FetchError(
                f"{origin}-{destination} {flight_date}: "
                f"{excluded}件取得しましたが全件を解釈できませんでした"
                "（ライブラリ/Google側の構造変化の可能性"
                + (f"。生HTMLを保存: {saved}" if saved else "")
                + "）"
            )

        return flights

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
