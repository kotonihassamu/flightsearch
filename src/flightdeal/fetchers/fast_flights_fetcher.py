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
from .base import BlockedError, FetchError, FlightFetcher

log = logging.getLogger(__name__)

# Bot判定・アクセス制限ページの目印。
#
# 【重要・実測による教訓 2026-07-29】マーカーは狭くすること。
# 当初 v6（Yahoo用）から借りた広いマーカーで誤検知が発生した:
#   - "recaptcha"        … Googleの正常ページにもJSルート定義 "/recaptcha/challenge" として常に含まれる
#   - "を確認しています"  … Google Flights自身のローディング文言「複数のソースから価格を確認しています…」
# この誤検知により、IPを何度変えても「Bot判定」となる偽の全滅が起きた。
# 現在のマーカーは、Bot判定ページにしか現れない文言だけに絞ってある。
# 判定に迷う場合は「ブロックと断定できるときだけ True」に倒す。誤って通しても
# 後段の parse 失敗で検知・HTML保存されるが、誤ってブロック扱いすると全機能が死ぬ。
BLOCK_MARKERS = (
    "unusual traffic from your computer",
    "our systems have detected unusual traffic",
    "通常と異なるトラフィックが検出されました",
    "sending automated queries",
    "automated queries from your computer",
)
BLOCK_STATUS = (403, 429, 503)

# 正常な検索結果ページには必ず ds:1 のデータスクリプトがある（parser が読む場所）。
_DATA_SCRIPT_MARK = 'class="ds:1"'


def looks_blocked(status_code: int, text: str) -> bool:
    """Bot判定ページかどうかを判定する。

    ステータスコードが明確ならそれで判定。200 の場合は、
    「ブロック特有の文言がある」かつ「検索結果データが無い」ときだけブロック扱い。
    """
    if status_code in BLOCK_STATUS:
        return True
    low = text.lower()
    if not any(marker in low for marker in BLOCK_MARKERS):
        return False
    # ブロック文言らしきものがあっても、実データが載っていれば正常ページとみなす
    return _DATA_SCRIPT_MARK not in text


URL = "https://www.google.com/travel/flights"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def import_failure_message(error: Exception) -> str:
    """fast-flights を読み込めなかったときの説明文を組み立てる。

    「インストールされていません」と決めつけないこと。実際には
    「古い版が入っていてAPIが違う」「依存ライブラリの読み込み失敗」なども
    ImportError になる。原因を握りつぶすと調査できなくなる。
    """
    return (
        f"fast-flights を読み込めません: {type(error).__name__}: {error} / "
        "確認: (1) pip install -r requirements.txt が成功しているか "
        "(2) fast-flights 3.x が入っているか（本システムは FlightQuery / create_filter を使う。"
        "2.x の FlightData ではない） "
        '(3) python -c "import fast_flights; print(fast_flights.__version__ '
        'if hasattr(fast_flights,\'__version__\') else fast_flights.__file__)"'
    )


def _load_fast_flights():
    """必要な fast-flights のシンボルをまとめて読み込む。

    Returns:
        (FlightQuery, Passengers, create_filter, parse, FlightsNotFound)

    Raises:
        FetchError: 読み込めない場合（原因を含めたメッセージ付き）
    """
    try:
        from fast_flights import FlightQuery, Passengers, create_filter
        from fast_flights.exceptions import FlightsNotFound
        from fast_flights.parser import parse
    except Exception as e:  # ImportError 以外（初期化時エラー等）も拾う
        raise FetchError(import_failure_message(e)) from e

    return FlightQuery, Passengers, create_filter, parse, FlightsNotFound


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
        FlightQuery, Passengers, create_filter, _, _ = _load_fast_flights()

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
        except Exception as e:
            raise FetchError(
                f"取得に失敗しました ({origin}-{destination} {flight_date}): "
                f"{type(e).__name__}: {e}"
            ) from e

        # Bot判定は「IPを変えれば解決する種類の失敗」として区別する（VPN切替の判断材料）
        if looks_blocked(resp.status_code, resp.text):
            raise BlockedError(
                f"Bot判定/アクセス制限を検知 ({origin}-{destination} {flight_date}): "
                f"HTTP {resp.status_code}"
            )

        try:
            resp.raise_for_status()
        except Exception as e:
            raise FetchError(
                f"取得に失敗しました ({origin}-{destination} {flight_date}): "
                f"{type(e).__name__}: {e}"
            ) from e

        return resp.text

    def fetch(self, origin: str, destination: str, flight_date: date) -> list[Flight]:
        _, _, _, parse, FlightsNotFound = _load_fast_flights()

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
