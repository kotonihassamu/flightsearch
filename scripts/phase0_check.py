#!/usr/bin/env python3
"""Phase 0 技術検証スクリプト（要件2）。

手元PCで実行し、データ取得方式が使えるかを確認する。
完了条件: 3日連続で、価格・時刻・航空会社名が取得できること。

本スクリプトは本体と同じ FastFlightsFetcher（requests + fast-flights parser、
primp回避）を使う。ここが通れば config.json の fetcher を "fast_flights" にして
本番運用できる。

使い方:
    python scripts/phase0_check.py                 # HND -> HIJ の次の土曜を検証
    python scripts/phase0_check.py --dest MYJ
    python scripts/phase0_check.py --save          # 結果を tests/fixtures/ に保存

GitHub Actions では実行しない（Bot判定検証は手元PCで行う）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FIXTURE_DIR = ROOT / "tests" / "fixtures"


def next_saturday(today: date) -> date:
    days = (5 - today.weekday()) % 7
    return today + timedelta(days=days or 7)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--origin", default="HND")
    p.add_argument("--dest", default="HIJ")
    p.add_argument("--date", default=None, help="YYYY-MM-DD（既定: 次の土曜）")
    p.add_argument("--save", action="store_true", help="正規化フィクスチャを保存")
    p.add_argument(
        "--save-raw",
        action="store_true",
        help="生HTMLも tests/fixtures/raw/ に保存（パーサ回帰テスト用。要件6.2）",
    )
    args = p.parse_args()

    from flightdeal.fetchers import FetchError
    from flightdeal.fetchers.fast_flights_fetcher import FastFlightsFetcher

    target = date.fromisoformat(args.date) if args.date else next_saturday(date.today())
    print(f"検証: {args.origin} -> {args.dest} / {target}")
    print("方式: FastFlightsFetcher（requests + fast-flights parser / primp回避）\n")

    fetcher = FastFlightsFetcher()
    try:
        if args.save_raw:
            raw_dir = FIXTURE_DIR / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_path = raw_dir / f"{args.origin}-{args.dest}-{target.isoformat()}.html"
            html = fetcher.fetch_html(args.origin, args.dest, target)
            raw_path.write_text(html, encoding="utf-8")
            print(f"生HTMLを保存: {raw_path}（{len(html):,} 文字）")
            print("  → 以後 pytest がこのHTMLでパーサの回帰テストを行う\n")

        flights = fetcher.fetch(args.origin, args.dest, target)
    except FetchError as e:
        print("取得に失敗しました:")
        print(" ", e)
        print("\n対処のヒント:")
        print("  - fast-flights / requests 未導入 -> pip install -r requirements.txt")
        print("  - 解析失敗 -> Googleの構造変化やBot判定ページの可能性。時間をおいて再試行")
        print("  - 連続で失敗 -> 要件3.2.2 の優先度2（Playwright）への切替を検討")
        return 1
    finally:
        fetcher.close()

    print(f"取得件数: {len(flights)}")
    if not flights:
        print("  （便が0件。日付・空港を確認。max_stops=0 で直行便のみ）")
        return 1

    for f in flights:
        no = f" / {f.flight_number}" if f.flight_number else ""
        print(f"  - {f.airline:<10} {f.depart_time.strftime('%H:%M')} 発 "
              f"→ {f.arrive_time.strftime('%H:%M')} 着  ￥{f.price:,}{no}")

    print("\nチェックリスト（要件2 完了条件）:")
    print("  [ ] 航空会社名が取れているか")
    print("  [ ] 出発/到着時刻が取れているか")
    print("  [ ] 価格がJPYで妥当か")
    print(f"  [ ] docs/phase0_log.md に本日の結果を記録したか（3日連続成功が完了条件）")

    if args.save:
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        out = FIXTURE_DIR / f"{args.origin}-{args.dest}-{target.isoformat()}.json"
        rows = [
            {
                "airline": f.airline,
                "depart_time": f.depart_time.strftime("%H:%M"),
                "arrive_time": f.arrive_time.strftime("%H:%M"),
                "price": f.price,
                "flight_number": f.flight_number,
            }
            for f in flights
        ]
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n保存: {out}")
        print("  （このフィクスチャは FixtureFetcher / パーステストで再利用できる）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
