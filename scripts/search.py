#!/usr/bin/env python3
"""日付を指定して航空券を検索する（週末縛りなしの手動検索）。

日次通知（main.py）は「次の週末」しか見ないが、これは
**出発日と帰着日を自分で指定**して同じロジックで検索する。
判定ロジック（片道×2の合算・LCC手荷物補正・相場比較・ランク）は本番と同一。

日次通知との違い:
  - 日付を自由に指定できる（週末でなくてよい。連泊でもよい）
  - 時間帯フィルターは既定で**なし**（指定した日程で全便を見たいはずなので）
  - ランク外でも結果を表示する（絞り込むのではなく、選択肢を見せる）
  - LINEには既定で送らない（--line で送れる）

使い方:
    # 9/19発・9/22帰り、config で有効な全空港
    python scripts/search.py --out 2026-09-19 --back 2026-09-22

    # 行き先を指定
    python scripts/search.py --out 2026-09-19 --back 2026-09-22 --dest OKA ISG MMY

    # 弾丸日程の時間帯条件（朝着・夜発）を適用する
    python scripts/search.py --out 2026-09-19 --back 2026-09-21 --weekend-hours

    # 時間帯を自分で指定
    python scripts/search.py --out 2026-09-19 --back 2026-09-22 --arrive-by 14:00 --depart-after 15:00

    # 結果をLINEにも送る / VPNを使う
    python scripts/search.py --out 2026-09-19 --back 2026-09-22 --dest OKA --line
    python scripts/search.py --out 2026-09-19 --back 2026-09-22 --all --vpn
"""

from __future__ import annotations

import argparse
import random
import sys
import time as time_mod
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flightdeal import filters, formatter, pricing, ranking  # noqa: E402
from flightdeal.config import load_config  # noqa: E402
from flightdeal.env import load_dotenv  # noqa: E402
from flightdeal.fetchers import FetchError, build_fetcher  # noqa: E402
from flightdeal.logging_setup import ensure_console_encoding  # noqa: E402
from flightdeal.models import Combination, Rank, RouteConfig, WeekendDates  # noqa: E402
from flightdeal.notifiers import build_notifier  # noqa: E402
from flightdeal.vpn import VpnController, fetch_with_rotation  # noqa: E402


def yen(v) -> str:
    return "—" if v is None else f"￥{v:,}"


def parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def trip_dates(outbound: date, inbound: date) -> WeekendDates:
    """指定日程を WeekendDates として表現する。

    WeekendDates は本来「土曜・日曜」の組だが、実体は単なる日付ペア。
    ここでは往路日・復路日として流用し、既存の Combination / formatter を
    そのまま再利用する（曜日表示は自動で正しく出る）。
    """
    return WeekendDates(saturday=outbound, sunday=inbound, index=1)


@dataclass
class RouteSearch:
    """1路線分の検索結果。"""

    route: RouteConfig
    outbound_count: int = 0
    inbound_count: int = 0
    after_filter_out: int = 0
    after_filter_in: int = 0
    combinations: list[Combination] | None = None
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None

    @property
    def best(self) -> Combination | None:
        if not self.combinations:
            return None
        return self.combinations[0]


def search_route(fetcher, route, out_date, back_date, cfg, tf, vpn=None,
                 top_n: int = 3) -> RouteSearch:
    """1路線を検索して、安い順の組み合わせを返す。

    tf: (arrive_by, depart_after) いずれも None なら時間帯フィルターなし。
    """
    result = RouteSearch(route=route)
    arrive_by, depart_after = tf

    try:
        outs = fetch_with_rotation(fetcher, vpn, cfg.origin, route.iata, out_date)
        sleep_politely(cfg)
        ins = fetch_with_rotation(fetcher, vpn, route.iata, cfg.origin, back_date)
    except FetchError as e:
        result.error = str(e)
        return result

    result.outbound_count = len(outs)
    result.inbound_count = len(ins)

    if arrive_by is not None:
        outs = filters.filter_outbound(outs, arrive_by)
    if depart_after is not None:
        ins = filters.filter_return(ins, depart_after)

    result.after_filter_out = len(outs)
    result.after_filter_in = len(ins)

    weekend = trip_dates(out_date, back_date)
    combos: list[Combination] = []
    for o, i in filters.combine(outs, ins):
        total, out_sc, in_sc, provisional = pricing.effective_price(o, i, cfg)
        combos.append(
            Combination(
                route=route, weekend=weekend, outbound=o, inbound=i,
                outbound_surcharge=out_sc, inbound_surcharge=in_sc,
                total_price=total,
                rank=ranking.judge_rank(total, route, cfg),
                provisional_surcharge=provisional,
            )
        )

    # ランクで絞らず、安い順に上位N件を見せる（選択肢を出すのが目的）
    combos.sort(key=lambda c: (c.total_price, c.outbound.depart_time))
    result.combinations = combos[:top_n]
    return result


def sleep_politely(cfg) -> None:
    lo, hi = cfg.search.sleep_between_searches
    if hi > 0:
        time_mod.sleep(random.uniform(lo, hi))


def build_report(results: list[RouteSearch], out_date: date, back_date: date,
                 cfg, tf) -> str:
    """人が読むレポートを組み立てる。"""
    arrive_by, depart_after = tf
    nights = (back_date - out_date).days
    lines: list[str] = []
    w = lines.append

    w("=" * 72)
    w("航空券検索（日付指定）")
    w("=" * 72)
    w(f"出発 : {out_date:%Y/%m/%d} ({formatter.WEEKDAY_JA[out_date.weekday()]})")
    w(f"帰着 : {back_date:%Y/%m/%d} ({formatter.WEEKDAY_JA[back_date.weekday()]})"
      f"  … {nights}泊{nights + 1}日" if nights > 0 else
      f"帰着 : {back_date:%Y/%m/%d} … 日帰り")
    w(f"出発地: {cfg.origin}")
    if arrive_by or depart_after:
        cond = []
        if arrive_by:
            cond.append(f"往路 {arrive_by:%H:%M} までに到着")
        if depart_after:
            cond.append(f"復路 {depart_after:%H:%M} 以降に出発")
        w(f"時間帯: {' / '.join(cond)}")
    else:
        w("時間帯: 指定なし（全便）")
    w("")
    w("※ 価格は片道×2の合算＋LCC手荷物補正（実質の往復負担）")
    w("")

    ok = [r for r in results if not r.failed and r.best]
    ok.sort(key=lambda r: r.best.total_price)

    # ---- ランキング ----
    w("=" * 72)
    w("安い順")
    w("=" * 72)
    if not ok:
        w("  条件に合う便が見つかりませんでした。")
    else:
        w(" 順 | 行き先     |   実質価格 | 相場との差       | ランク")
        w("-" * 68)
        for n, r in enumerate(ok, 1):
            c = r.best
            diff = c.total_price - r.route.market_price
            pct = abs(diff / r.route.market_price * 100) if r.route.market_price else 0
            # 「相場より安い/高い」を言葉で書く（+/− だけだと解釈が割れる）
            label = f"{pct:>3.0f}% 安い" if diff < 0 else f"{pct:>3.0f}% 高い"
            rank = c.rank.value if c.rank is not Rank.NONE else "-"
            name = r.route.name + "　" * max(0, 5 - len(r.route.name))
            w(f"{n:>3} | {name} | {yen(c.total_price):>10} | "
              f"{yen(r.route.market_price):>9} より {label} | {rank}")
    w("")

    # ---- 路線ごとの詳細 ----
    w("=" * 72)
    w("詳細（各行き先の安い順）")
    w("=" * 72)
    for r in ok:
        w(f"■ {r.route.name}({r.route.iata})   "
          f"取得 往路{r.outbound_count}/復路{r.inbound_count}便"
          + (f" → 条件後 {r.after_filter_out}/{r.after_filter_in}便"
             if (arrive_by or depart_after) else ""))
        w(f"   相場（週末往復の目安）: {yen(r.route.market_price)}")
        for c in r.combinations or []:
            o, i = c.outbound, c.inbound
            rank = f"【{c.rank.value}】" if c.rank is not Rank.NONE else ""
            surcharge = c.outbound_surcharge + c.inbound_surcharge
            w(f"   {rank}実質 {yen(c.total_price)}"
              + (f"（うち手荷物 {yen(surcharge)}）" if surcharge else ""))
            w(f"      往路 {out_date:%m/%d} {o.airline} "
              f"{o.depart_time:%H:%M}→{o.arrive_time:%H:%M} {yen(o.price)}")
            w(f"      復路 {back_date:%m/%d} {i.airline} "
              f"{i.depart_time:%H:%M}→{i.arrive_time:%H:%M} {yen(i.price)}")
            if c.provisional_surcharge:
                w("      ※補正額は仮（航空会社が未分類）")
        w(f"   往路検索: {formatter.oneway_url(cfg.origin, r.route.iata, out_date)}")
        w(f"   復路検索: {formatter.oneway_url(r.route.iata, cfg.origin, back_date)}")
        w("")

    # ---- 便が無かった/失敗した路線 ----
    empty = [r for r in results if not r.failed and not r.best]
    failed = [r for r in results if r.failed]
    if empty:
        w(f"条件に合う便なし: {', '.join(r.route.name for r in empty)}")
        w("")
    if failed:
        w("取得失敗:")
        for r in failed:
            w(f"  {r.route.name}: {(r.error or '')[:100]}")
        w("")

    w("=" * 72)
    w("※ 表示価格は目安です。予約前に必ず各社サイトで空席・価格を確認してください。")
    return "\n".join(lines)


def build_line_message(results: list[RouteSearch], out_date: date, back_date: date,
                       cfg, top: int = 5) -> str:
    """LINE用の短い本文（安い順に上位のみ）。"""
    ok = [r for r in results if not r.failed and r.best]
    ok.sort(key=lambda r: r.best.total_price)

    head = (f"【検索結果】{out_date:%m/%d}({formatter.WEEKDAY_JA[out_date.weekday()]})"
            f"〜{back_date:%m/%d}({formatter.WEEKDAY_JA[back_date.weekday()]})")
    if not ok:
        return head + "\n\n条件に合う便が見つかりませんでした。"

    blocks = [head + f"\n{len(ok)}路線で見つかりました（安い順に{min(top, len(ok))}件）"]
    for r in ok[:top]:
        blocks.append(formatter.format_combination(r.best))
    blocks.append(formatter.FOOTER)
    return formatter.BLOCK_SEPARATOR.join(blocks)


def main() -> int:
    ensure_console_encoding()
    load_dotenv()

    p = argparse.ArgumentParser(description="日付を指定して航空券を検索する")
    p.add_argument("--out", "--depart", dest="out_date", required=True,
                   metavar="YYYY-MM-DD", help="出発日")
    p.add_argument("--back", "--return", dest="back_date", required=True,
                   metavar="YYYY-MM-DD", help="帰着日")
    p.add_argument("--dest", nargs="*", default=None,
                   help="行き先をIATAで指定（例: OKA ISG）。省略時は config の有効路線")
    p.add_argument("--all", action="store_true",
                   help="enabled を無視して config の全空港を対象にする")
    p.add_argument("--top", type=int, default=3, help="各路線で表示する候補数（既定3）")
    p.add_argument("--weekend-hours", action="store_true",
                   help="config の時間帯条件（朝着・夜発）を適用する")
    p.add_argument("--arrive-by", default=None, metavar="HH:MM",
                   help="往路の到着時刻の上限")
    p.add_argument("--depart-after", default=None, metavar="HH:MM",
                   help="復路の出発時刻の下限")
    p.add_argument("--line", action="store_true", help="結果をLINEにも送る")
    p.add_argument("--save", nargs="?", const="", default=None, metavar="PATH",
                   help="結果をテキストに保存（パス省略で自動命名）")
    p.add_argument("--vpn", action="store_true", help="VPN必須で実行しBot判定時に切替")
    p.add_argument("--config", default=None)
    args = p.parse_args()

    try:
        out_date = date.fromisoformat(args.out_date)
        back_date = date.fromisoformat(args.back_date)
    except ValueError as e:
        print(f"日付の形式が不正です（YYYY-MM-DD）: {e}")
        return 1

    if back_date < out_date:
        print("帰着日が出発日より前です。")
        return 1

    today = date.today()
    if out_date < today:
        print(f"⚠ 出発日 {out_date} は過去です。検索は実行しますが結果は期待できません。")

    cfg = load_config(args.config)

    # 対象路線
    if args.dest:
        wanted = {d.upper() for d in args.dest}
        routes = [d for d in cfg.destinations if d.iata in wanted]
        unknown = wanted - {d.iata for d in routes}
        if unknown:
            print(f"config.json に無い空港コードです: {sorted(unknown)}")
            return 1
    elif args.all:
        routes = list(cfg.destinations)
    else:
        routes = cfg.enabled_destinations

    if not routes:
        print("対象路線がありません。")
        return 1

    # 時間帯条件
    if args.weekend_hours:
        tf = (cfg.time_filter.outbound_arrive_by, cfg.time_filter.return_depart_after)
    else:
        tf = (
            parse_hhmm(args.arrive_by) if args.arrive_by else None,
            parse_hhmm(args.depart_after) if args.depart_after else None,
        )

    total_searches = len(routes) * 2
    lo, hi = cfg.search.sleep_between_searches
    est_min = total_searches * ((lo + hi) / 2 + 1) / 60

    print("=" * 60)
    print("航空券検索（日付指定）")
    print("=" * 60)
    print(f"出発     : {out_date} ({formatter.WEEKDAY_JA[out_date.weekday()]})")
    print(f"帰着     : {back_date} ({formatter.WEEKDAY_JA[back_date.weekday()]})")
    print(f"対象     : {len(routes)}路線 {', '.join(r.name for r in routes[:8])}"
          + (" …" if len(routes) > 8 else ""))
    print(f"時間帯   : {'指定なし（全便）' if tf == (None, None) else str(tf)}")
    print(f"検索回数 : {total_searches} 回（推定 {est_min:.0f} 分）")
    print("=" * 60)
    print()

    vpn = None
    if args.vpn:
        vpn_cfg = cfg.vpn
        vpn_cfg.enabled = True
        if vpn_cfg.mode == "off":
            vpn_cfg.mode = "manual"
        vpn = VpnController(vpn_cfg, base_dir=ROOT)
        try:
            vpn.require_vpn()
        except RuntimeError as e:
            print(f"\nVPN確認に失敗しました:\n{e}")
            return 1

    results: list[RouteSearch] = []
    fetcher = build_fetcher(cfg.fetcher)
    try:
        for n, route in enumerate(routes, 1):
            print(f"[{n}/{len(routes)}] {route.name} ... ", end="", flush=True)
            r = search_route(fetcher, route, out_date, back_date, cfg, tf,
                             vpn=vpn, top_n=args.top)
            results.append(r)
            if r.failed:
                print("失敗")
            elif r.best:
                print(f"最安 {yen(r.best.total_price)}")
            else:
                print("該当便なし")
            if n < len(routes):
                sleep_politely(cfg)
    except KeyboardInterrupt:
        print("\n中断しました。ここまでの結果を表示します。")
    finally:
        fetcher.close()
        if vpn is not None:
            vpn.close()

    report = build_report(results, out_date, back_date, cfg, tf)
    print()
    print(report)

    if args.save is not None:
        path = Path(args.save) if args.save else (
            ROOT / f"検索結果_{out_date:%Y%m%d}-{back_date:%Y%m%d}.txt")
        path.write_text(report, encoding="utf-8-sig")
        print(f"\n保存しました: {path}")

    if args.line:
        message = build_line_message(results, out_date, back_date, cfg)
        try:
            build_notifier("line").send(message)
            print("\nLINEに送信しました。")
        except Exception as e:
            print(f"\nLINE送信に失敗しました: {e}")
            return 3

    ok = [r for r in results if not r.failed and r.best]
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
