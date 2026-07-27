"""テスト・ドライラン用の StubFetcher。

外部サイトへ一切アクセスせず、決定的な便リストを返す。
用途:
  - Phase 1 のドライラン（実取得なしでパイプライン全体を動かす）
  - 単体テストで FlightFetcher を差し替える
  - CI（外部接続を伴うテストは合否条件に含めない: 要件6.2）

このモジュールは骨組み段階でも完全に動作する必要があるため実装済み。
"""

from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path

from ..models import Flight
from .base import FetchError, FlightFetcher

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


def _t(hhmm: str) -> time:
    hh, mm = hhmm.split(":")
    return time(int(hh), int(mm))


# 区間ごとのサンプル便（時刻・価格は架空。判定ロジックの動作確認用）
_SAMPLE: dict[str, list[dict]] = {
    "HND-HIJ": [
        {"airline": "ANA", "dep": "07:25", "arr": "08:50", "price": 11400, "no": "NH673"},
        {"airline": "JAL", "dep": "08:05", "arr": "09:30", "price": 13200, "no": "JL255"},
        {"airline": "ANA", "dep": "12:10", "arr": "13:35", "price": 9800, "no": "NH677"},
    ],
    "HIJ-HND": [
        {"airline": "ANA", "dep": "19:05", "arr": "20:30", "price": 11400, "no": "NH688"},
        {"airline": "JAL", "dep": "16:20", "arr": "17:45", "price": 10100, "no": "JL264"},
        {"airline": "JAL", "dep": "20:10", "arr": "21:35", "price": 14300, "no": "JL266"},
    ],
    "HND-MYJ": [
        {"airline": "JAL", "dep": "07:40", "arr": "09:05", "price": 12600, "no": "JL431"},
        {"airline": "Jetstar", "dep": "09:15", "arr": "10:40", "price": 6900, "no": "GK455"},
    ],
    "MYJ-HND": [
        {"airline": "Jetstar", "dep": "18:35", "arr": "20:00", "price": 7400, "no": "GK458"},
        {"airline": "JAL", "dep": "19:40", "arr": "21:05", "price": 13100, "no": "JL438"},
    ],
    # --- Phase 3 で有効化する路線（ドライラン用） ---
    "HND-FUK": [
        {"airline": "ANA", "dep": "06:55", "arr": "08:50", "price": 12800, "no": "NH241"},
        {"airline": "Skymark", "dep": "08:20", "arr": "10:15", "price": 9600, "no": "BC003"},
        {"airline": "Peach", "dep": "09:40", "arr": "11:35", "price": 5900, "no": "MM523"},
    ],
    "FUK-HND": [
        {"airline": "Skymark", "dep": "18:10", "arr": "19:45", "price": 9200, "no": "BC016"},
        {"airline": "ANA", "dep": "20:00", "arr": "21:35", "price": 13400, "no": "NH264"},
    ],
    "HND-CTS": [
        {"airline": "AIRDO", "dep": "07:30", "arr": "09:05", "price": 10800, "no": "HD013"},
        {"airline": "JAL", "dep": "08:00", "arr": "09:35", "price": 14200, "no": "JL503"},
    ],
    "CTS-HND": [
        {"airline": "AIRDO", "dep": "19:00", "arr": "20:40", "price": 11200, "no": "HD028"},
        {"airline": "Peach", "dep": "17:25", "arr": "19:05", "price": 6800, "no": "MM108"},
    ],
    "HND-OKA": [
        {"airline": "JAL", "dep": "06:45", "arr": "09:40", "price": 18900, "no": "JL901"},
        {"airline": "Solaseed Air", "dep": "08:15", "arr": "11:00", "price": 15600, "no": "6J121"},
    ],
    "OKA-HND": [
        {"airline": "ANA", "dep": "19:30", "arr": "21:55", "price": 17400, "no": "NH472"},
        {"airline": "Solaseed Air", "dep": "17:45", "arr": "20:15", "price": 14800, "no": "6J124"},
    ],
}


class StubFetcher(FlightFetcher):
    """固定のサンプル便を返す取得器。"""

    name = "stub"

    def __init__(self, fail_routes: set[str] | None = None) -> None:
        # fail_routes に "HND-FUK" のようなキーを入れると、その区間で FetchError を送出する。
        # 要件4.3（路線単位の隔離・失敗の可視化）の動作確認に使う。
        self.fail_routes = fail_routes or set()

    def fetch(self, origin: str, destination: str, flight_date: date) -> list[Flight]:
        key = f"{origin}-{destination}"
        if key in self.fail_routes:
            raise FetchError(f"stub: 意図的な失敗 ({key})")

        rows = _SAMPLE.get(key)
        if rows is None:
            raise FetchError(f"stub: サンプルデータ未定義の区間です ({key})")

        return [
            Flight(
                origin=origin,
                destination=destination,
                flight_date=flight_date,
                airline=r["airline"],
                depart_time=_t(r["dep"]),
                arrive_time=_t(r["arr"]),
                price=r["price"],
                flight_number=r.get("no"),
            )
            for r in rows
        ]


class FixtureFetcher(FlightFetcher):
    """保存済みJSONフィクスチャを読むフェッチャ（要件6.2 フィクスチャテスト用）。

    tests/fixtures/<ORIGIN>-<DEST>-<YYYY-MM-DD>.json を読み込む。
    Phase 0 で実取得した生レスポンスを保存し、パース部の回帰テストに使う。
    """

    name = "fixture"

    def __init__(self, fixture_dir: Path | None = None) -> None:
        self.fixture_dir = fixture_dir or FIXTURE_DIR

    def fetch(self, origin: str, destination: str, flight_date: date) -> list[Flight]:
        path = self.fixture_dir / f"{origin}-{destination}-{flight_date.isoformat()}.json"
        if not path.exists():
            raise FetchError(f"fixture が見つかりません: {path}")

        rows = json.loads(path.read_text(encoding="utf-8"))
        return [
            Flight(
                origin=origin,
                destination=destination,
                flight_date=flight_date,
                airline=r["airline"],
                depart_time=_t(r["depart_time"]),
                arrive_time=_t(r["arrive_time"]),
                price=int(r["price"]),
                flight_number=r.get("flight_number"),
            )
            for r in rows
        ]
