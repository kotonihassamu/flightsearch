#!/usr/bin/env python3
"""週末料金の一括調査スクリプト（相場を知るための一回限りの調査）。

日次の自動実行とは別物。以下の点で本番と違う:
  - 週末を1〜2個ではなく、指定した週数ぶん全部見る
  - LINEには一切通知しない。テキストファイルに書き出すだけ
  - ランク判定はするが、通知はしない（相場設定が仮のため参考値）

目的は「その路線の普段の価格を知る」こと。得られた統計から
config.json の market_price / max_price を根拠を持って決められる（要件 Phase 1-17）。

使い方:
    python scripts/survey.py                     # 3か月ぶん（13週）、有効な全路線
    python scripts/survey.py --weeks 8
    python scripts/survey.py --dest HIJ --dest MYJ
    python scripts/survey.py --out 調査結果.txt

注意:
  検索回数 = 週数 × 路線数 × 2 になる。13週×2路線なら52回。
  Bot判定を避けるため検索間にランダム待機を入れるので、10分前後かかる。
  1日に何度も走らせないこと（要件R1: 個人利用の範囲に留める）。
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
import time as time_mod
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from flightdeal import filters, pricing, ranking  # noqa: E402
from flightdeal.config import load_config  # noqa: E402
from flightdeal.fetchers import FetchError  # noqa: E402
from flightdeal.fetchers.fast_flights_fetcher import FastFlightsFetcher  # noqa: E402
from flightdeal.logging_setup import ensure_console_encoding  # noqa: E402
from flightdeal.models import Combination, Rank, RouteConfig, WeekendDates  # noqa: E402
from flightdeal.vpn import VpnController, fetch_with_rotation  # noqa: E402
from flightdeal.weekend import next_saturday  # noqa: E402


def yen(v: int | None) -> str:
    return "—" if v is None else f"￥{v:,}"


@dataclass
class Result:
    """1路線・1週末ぶんの調査結果。"""

    route: RouteConfig
    weekend: WeekendDates
    outbound_count: int = 0
    inbound_count: int = 0
    best_filtered: Combination | None = None   # 時間帯条件を満たす最安
    best_any: Combination | None = None        # 時間帯を無視した最安（比較用）
    error: str | None = None


def build_combinations(outs, ins, route, weekend, cfg) -> list[Combination]:
    combos = []
    for o, i in filters.combine(outs, ins):
        total, out_sc, in_sc, provisional = pricing.effective_price(o, i, cfg)
        combos.append(
            Combination(
                route=route,
                weekend=weekend,
                outbound=o,
                inbound=i,
                outbound_surcharge=out_sc,
                inbound_surcharge=in_sc,
                total_price=total,
                rank=ranking.judge_rank(total, route, cfg),
                provisional_surcharge=provisional,
            )
        )
    return combos


def cheapest(combos: list[Combination]) -> Combination | None:
    return min(combos, key=lambda c: c.total_price) if combos else None


def survey_one(fetcher, route: RouteConfig, weekend: WeekendDates, cfg, vpn=None) -> Result:
    result = Result(route=route, weekend=weekend)
    try:
        outs = fetch_with_rotation(fetcher, vpn, cfg.origin, route.iata, weekend.saturday)
        sleep_politely(cfg)
        ins = fetch_with_rotation(fetcher, vpn, route.iata, cfg.origin, weekend.sunday)
    except FetchError as e:
        result.error = str(e)
        return result

    result.outbound_count = len(outs)
    result.inbound_count = len(ins)

    # 時間帯条件あり（本番と同じ条件）
    fo = filters.filter_outbound(outs, cfg.time_filter.outbound_arrive_by)
    fi = filters.filter_return(ins, cfg.time_filter.return_depart_after)
    result.best_filtered = cheapest(build_combinations(fo, fi, route, weekend, cfg))

    # 時間帯条件なし（弾丸縛りの「コスト」を見るため。追加の通信はしない）
    result.best_any = cheapest(build_combinations(outs, ins, route, weekend, cfg))

    return result


def sleep_politely(cfg) -> None:
    lo, hi = cfg.search.sleep_between_searches
    time_mod.sleep(random.uniform(lo, hi))


def describe(combo: Combination | None) -> list[str]:
    if combo is None:
        return ["      該当便なし"]
    o, i = combo.outbound, combo.inbound
    lines = [
        f"      実質 {yen(combo.total_price)}"
        f"（往路 {yen(o.price)} + 復路 {yen(i.price)}"
        + (f" + 手荷物 {yen(combo.outbound_surcharge + combo.inbound_surcharge)}"
           if (combo.outbound_surcharge + combo.inbound_surcharge) else "")
        + "）",
        f"      往路 {o.airline} {o.depart_time:%H:%M}→{o.arrive_time:%H:%M} / "
        f"復路 {i.airline} {i.depart_time:%H:%M}→{i.arrive_time:%H:%M}",
    ]
    if combo.rank is not Rank.NONE:
        lines.append(f"      現在の設定でのランク: {combo.rank.value}")
    return lines


def percentile(values: list[int], q: float) -> int:
    """簡易パーセンタイル（線形補間なし・下側に丸める）。"""
    if not values:
        return 0
    ordered = sorted(values)
    idx = min(int(len(ordered) * q), len(ordered) - 1)
    return ordered[idx]


def build_report(results: list[Result], cfg, weeks: int, started: date) -> str:
    out: list[str] = []
    w = out.append

    w("=" * 72)
    w("週末格安航空券 調査レポート")
    w("=" * 72)
    w(f"実行日        : {started.isoformat()}")
    w(f"対象          : 今後 {weeks} 週ぶんの土日")
    w(f"出発地        : {cfg.origin}")
    w(f"路線          : {', '.join(f'{r.name}({r.iata})' for r in {id(x.route): x.route for x in results}.values())}")
    w(f"時間帯条件    : 往路 {cfg.time_filter.outbound_arrive_by:%H:%M} までに到着 / "
      f"復路 {cfg.time_filter.return_depart_after:%H:%M} 以降に出発")
    w(f"手荷物補正    : LCC 片道 {yen(cfg.baggage_surcharge_oneway)}")
    w("")
    w("※ 実質価格 = 往路片道 + 復路片道 + 手荷物補正（往復の実質負担）")
    w("※ LINE通知は行っていません。これは調査用の出力です。")
    w("")

    # ---- 1. 安い順ランキング ----
    ranked = [r for r in results if r.best_filtered is not None]
    ranked.sort(key=lambda r: r.best_filtered.total_price)

    w("=" * 72)
    w("1. 安い週末ランキング（時間帯条件を満たすもの）")
    w("=" * 72)
    if not ranked:
        w("  条件を満たす便が1つもありませんでした。")
        w("  時間帯条件が厳しすぎる可能性があります（config.json の time_filter）。")
    else:
        w(" 順 | 路線   | 週末          |   実質価格 | 往路                  | 復路")
        w("-" * 84)
        for n, r in enumerate(ranked[:25], 1):
            c = r.best_filtered
            o, i = c.outbound, c.inbound
            out_leg = f"{o.airline} {o.depart_time:%H:%M}→{o.arrive_time:%H:%M}"
            in_leg = f"{i.airline} {i.depart_time:%H:%M}→{i.arrive_time:%H:%M}"
            name = r.route.name + "　" * max(0, 3 - len(r.route.name))
            w(f"{n:>3} | {name} | "
              f"{r.weekend.saturday:%m/%d}-{r.weekend.sunday:%m/%d} | "
              f"{yen(c.total_price):>10} | {out_leg:<21} | {in_leg}")
    w("")

    # ---- 2. 路線別の統計（相場設定の根拠） ----
    w("=" * 72)
    w("2. 路線別の統計 — config.json の相場設定に使う")
    w("=" * 72)

    by_route: dict[str, list[Result]] = {}
    for r in results:
        by_route.setdefault(r.route.iata, []).append(r)

    suggestions: list[tuple[RouteConfig, int, int]] = []

    for iata, rows in by_route.items():
        route = rows[0].route
        prices = [x.best_filtered.total_price for x in rows if x.best_filtered]
        all_prices = [x.best_any.total_price for x in rows if x.best_any]

        w(f"■ {route.name}({iata})")
        w(f"   調査した週末     : {len(rows)} 件")
        w(f"   条件を満たした   : {len(prices)} 件")
        if not prices:
            w("   → 時間帯条件を満たす便がありませんでした")
            w("")
            continue

        median = int(statistics.median(prices))
        w(f"   最安             : {yen(min(prices))}")
        w(f"   中央値（＝相場） : {yen(median)}")
        w(f"   最高             : {yen(max(prices))}")
        w(f"   下位25%ライン    : {yen(percentile(prices, 0.25))}")
        if all_prices:
            w(f"   （参考）時間帯条件を外した場合の最安: {yen(min(all_prices))}")
            diff = min(prices) - min(all_prices)
            if diff > 0:
                w(f"   　→ 弾丸日程（土朝発・日夜帰り）にこだわる分の上乗せ: {yen(diff)}")
        w(f"   現在の設定       : market_price {yen(route.market_price)} / "
          f"max_price {yen(route.max_price)}")

        suggested_market = median
        suggested_max = percentile(prices, 0.25)
        if suggested_max >= suggested_market:
            suggested_max = int(suggested_market * 0.9)
        suggestions.append((route, suggested_market, suggested_max))

        if route.market_price < min(prices):
            w("   ⚠ 現在の相場設定が実勢の最安より低いため、通知は一生出ません")
        w("")

    # ---- 3. 設定の提案 ----
    if suggestions:
        w("=" * 72)
        w("3. config.json の設定案（この調査結果に基づく）")
        w("=" * 72)
        w("中央値を「相場」、下位25%を「この値段なら買う上限」とした案です。")
        w("そのまま使う必要はありません。予算感に合わせて調整してください。")
        w("")
        for route, market, mx in suggestions:
            w(f'    {{"iata": "{route.iata}", "name": "{route.name}", '
              f'"market_price": {market}, "max_price": {mx}, "enabled": true}},')
        w("")
        w("この設定にすると、")
        w("  S: 相場の70%以下（中央値より3割以上安い週末）")
        w("  A: 相場の85%以下")
        w("  B: 相場未満 かつ max_price 以下（＝おおむね下位25%）")
        w("が通知対象になります。")
        w("")

    # ---- 4. 週末ごとの詳細 ----
    w("=" * 72)
    w("4. 週末ごとの詳細")
    w("=" * 72)
    for r in sorted(results, key=lambda x: (x.weekend.saturday, x.route.iata)):
        head = (f"{r.weekend.saturday:%Y/%m/%d}(土)〜{r.weekend.sunday:%m/%d}(日)  "
                f"{r.route.name}({r.route.iata})")
        w(head)
        if r.error:
            w(f"      取得失敗: {r.error[:120]}")
            w("")
            continue
        w(f"      取得便数: 往路 {r.outbound_count} / 復路 {r.inbound_count}")
        w("    [時間帯条件あり]")
        out.extend(describe(r.best_filtered))
        w("    [時間帯条件なし・参考]")
        out.extend(describe(r.best_any))
        w("")

    # ---- 5. 失敗のまとめ ----
    failures = [r for r in results if r.error]
    if failures:
        w("=" * 72)
        w("5. 取得に失敗したもの")
        w("=" * 72)
        for r in failures:
            w(f"  {r.route.name} {r.weekend.saturday}: {r.error[:150]}")
        w("")

    w("=" * 72)
    w("以上")
    return "\n".join(out)


def main() -> int:
    ensure_console_encoding()

    p = argparse.ArgumentParser(description="週末料金の一括調査（LINE通知なし）")
    p.add_argument("--weeks", type=int, default=13, help="調査する週数（既定13＝約3か月）")
    p.add_argument("--dest", action="append", default=[],
                   help="対象空港コード（複数指定可）。省略時は config の有効路線")
    p.add_argument("--out", default=None, help="出力ファイル名")
    p.add_argument("--config", default=None)
    p.add_argument("--all", action="store_true",
                   help="enabled を無視して config の全空港を対象にする")
    p.add_argument("--vpn", action="store_true",
                   help="VPN必須で実行し、Bot判定時にサーバー切替（config の vpn 設定を使う）")
    p.add_argument("--yes", action="store_true", help="検索数の確認をスキップして実行")
    p.add_argument("--max-minutes", type=int, default=0,
                   help="この分数を超えたら打ち切って、それまでの結果を書き出す（0=無制限）。"
                        "CIのジョブタイムアウトでレポートごと消えるのを防ぐため、"
                        "ジョブ上限より少し短く設定する")
    args = p.parse_args()

    cfg = load_config(args.config)

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
        print("対象路線がありません。config.json の enabled を確認してください。")
        return 1

    today = date.today()
    first = next_saturday(today)
    weekends = [
        WeekendDates(saturday=first + timedelta(days=7 * i),
                     sunday=first + timedelta(days=7 * i + 1),
                     index=i + 1)
        for i in range(args.weeks)
    ]

    total_searches = len(weekends) * len(routes) * 2
    lo, hi = cfg.search.sleep_between_searches
    est_min = total_searches * ((lo + hi) / 2 + 1) / 60

    print("=" * 60)
    print("週末料金 一括調査")
    print("=" * 60)
    print(f"対象路線  : {len(routes)} 路線"
          + ("（全空港）" if args.all else ""))
    print(f"          {', '.join(f'{r.name}' for r in routes)}")
    print(f"対象週末  : {len(weekends)} 件（{weekends[0].saturday} 〜 {weekends[-1].sunday}）")
    print(f"検索回数  : {total_searches} 回")
    print(f"推定所要  : 約 {est_min:.0f} 分（Bot判定を避けるため待機を入れます）")
    print(f"VPN       : {'あり（Bot判定で切替）' if args.vpn else 'なし'}")
    print("=" * 60)

    # 大量検索は確認を挟む（自宅IPだとBot判定されうるため）
    if total_searches > 60 and not args.yes:
        print(f"\n⚠ 検索回数が {total_searches} 回と多めです。")
        if not args.vpn:
            print("  VPNなしで多数を投げると自宅IPがBot判定される可能性があります。")
            print("  --vpn を付けるか、--weeks で週数を減らすことを検討してください。")
        try:
            ans = input("このまま実行しますか？ [y/N]: ").strip().lower()
        except EOFError:
            ans = "n"
        if ans not in ("y", "yes"):
            print("中止しました。")
            return 0
    print()

    # VPN 準備（--vpn 指定時）
    vpn = None
    if args.vpn:
        vpn_cfg = cfg.vpn
        vpn_cfg.enabled = True  # --vpn 指定なら強制的に有効
        if vpn_cfg.mode == "off":
            vpn_cfg.mode = "manual"
        vpn = VpnController(vpn_cfg, base_dir=ROOT)
        try:
            vpn.require_vpn()
        except RuntimeError as e:
            print(f"\nVPN確認に失敗しました:\n{e}")
            return 1

    results: list[Result] = []
    fetcher = FastFlightsFetcher()
    done = 0
    consecutive_failures = 0
    MAX_CONSECUTIVE_FAILURES = 8  # 連続全滅なら環境の問題。無駄打ちせず打ち切って書き出す
    started_at = time_mod.monotonic()

    try:
        for weekend in weekends:
            for route in routes:
                if args.max_minutes and (time_mod.monotonic() - started_at) / 60 >= args.max_minutes:
                    print(f"\n時間上限（{args.max_minutes}分）に達したため打ち切ります。")
                    raise KeyboardInterrupt

                done += 1
                label = (f"[{done}/{len(weekends) * len(routes)}] "
                         f"{route.name} {weekend.saturday:%m/%d}-{weekend.sunday:%m/%d}")
                print(f"{label} ... ", end="", flush=True)

                r = survey_one(fetcher, route, weekend, cfg, vpn=vpn)
                results.append(r)

                if r.error:
                    print("失敗")
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        print(f"\n⚠ {MAX_CONSECUTIVE_FAILURES} 回連続で失敗したため打ち切ります。")
                        print("  （IPブロック・ネットワーク・仕様変更などの環境要因の可能性）")
                        raise KeyboardInterrupt
                else:
                    consecutive_failures = 0
                    if r.best_filtered:
                        print(f"最安 {yen(r.best_filtered.total_price)}")
                    else:
                        print("条件を満たす便なし")

                if done < len(weekends) * len(routes):
                    sleep_politely(cfg)
    except KeyboardInterrupt:
        print("\n中断しました。ここまでの結果を書き出します。")
    finally:
        fetcher.close()
        if vpn is not None:
            vpn.close()

    elapsed = (time_mod.monotonic() - started_at) / 60
    print(f"\n完了（{elapsed:.1f} 分）")

    report = build_report(results, cfg, args.weeks, today)
    out_path = Path(args.out) if args.out else ROOT / f"調査結果_{today:%Y%m%d}.txt"
    # Windows のメモ帳でも確実に開けるよう BOM 付きUTF-8
    out_path.write_text(report, encoding="utf-8-sig")

    print(f"レポートを書き出しました: {out_path}")

    ok = [r for r in results if r.best_filtered]
    if ok:
        best = min(ok, key=lambda r: r.best_filtered.total_price)
        print(f"最安は {best.route.name} {best.weekend.saturday:%m/%d}-"
              f"{best.weekend.sunday:%m/%d} の {yen(best.best_filtered.total_price)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
