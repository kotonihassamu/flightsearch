"""通知本文の組み立て（要件3.6）。

原則: リンクが機能しなくても、本文情報だけで航空会社サイトから予約行動に移れること。

フォーマット例（要件3.6 をベースに、片道分解方式に合わせて調整）:
    【S】羽田⇔広島 8/1(土)〜8/2(日)
    実質 ￥22,800（片道×2の合算 / 相場 ￥35,000 / ▲35%）
    往路 8/1: ANA 07:25発 → 08:50着（片道 ￥11,400）
    復路 8/2: ANA 19:05発 → 20:30着（片道 ￥11,400）
    補正: なし（FSC）
    往路検索: https://www.google.com/travel/flights?tfs=...
    復路検索: https://www.google.com/travel/flights?tfs=...

検索リンクは「片道・その日付・直行便のみ」を指す tfs URL（search_link.py）。
往復の自然言語クエリはGoogleが復路日を勝手に補完し本文と食い違うため使わない。
"""

from __future__ import annotations

from datetime import date

from .models import Combination, Rank, RunResult
from .search_link import oneway_url

MAX_TEXT_LENGTH = 5000
WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]

BLOCK_SEPARATOR = "\n\n"
FOOTER = "※表示価格は目安です。予約前に必ず各社サイトで空席・価格を確認してください。"


def yen(amount: int) -> str:
    """9800 -> '￥9,800'。

    半角¥(U+00A5)はWindowsの既定コードページ(cp932)で表現できず、
    コンソール出力時に UnicodeEncodeError になる。全角￥を使う。
    """
    return f"￥{amount:,}"


def hhmm(value) -> str:
    return f"{value.hour:02d}:{value.minute:02d}"


def format_date_range(saturday: date, sunday: date) -> str:
    """'8/1(土)〜8/2(日)' 形式の文字列を返す。"""
    sat = f"{saturday.month}/{saturday.day}({WEEKDAY_JA[saturday.weekday()]})"
    sun = f"{sunday.month}/{sunday.day}({WEEKDAY_JA[sunday.weekday()]})"
    return f"{sat}〜{sun}"


def _surcharge_note(combo: Combination) -> str:
    """補正の内訳を1行で表す。"""
    total = combo.outbound_surcharge + combo.inbound_surcharge
    if total == 0:
        base = "なし（FSC）"
    else:
        parts = []
        if combo.outbound_surcharge:
            parts.append(f"往路+{yen(combo.outbound_surcharge)}")
        if combo.inbound_surcharge:
            parts.append(f"復路+{yen(combo.inbound_surcharge)}")
        base = f"手荷物 {' / '.join(parts)}"

    if combo.provisional_surcharge:
        base += "（※補正額は仮。航空会社が未分類のため実際と異なる場合あり）"
    return base


def format_combination(combo: Combination) -> str:
    """1件分の通知ブロックを組み立てる（要件3.6 の必須項目をすべて含む）。"""
    route = combo.route
    weekend = combo.weekend
    out, ret = combo.outbound, combo.inbound
    discount = round(combo.discount_rate * 100)

    lines = [
        f"【{combo.rank.value}】羽田⇔{route.name} {format_date_range(weekend.saturday, weekend.sunday)}",
        f"実質 {yen(combo.total_price)}（片道×2の合算 / 相場 {yen(route.market_price)} / ▲{discount}%）",
        f"往路 {weekend.saturday.month}/{weekend.saturday.day}: "
        f"{out.airline} {hhmm(out.depart_time)}発 → {hhmm(out.arrive_time)}着"
        f"（片道 {yen(out.price)}{_flight_no(out.flight_number)}）",
        f"復路 {weekend.sunday.month}/{weekend.sunday.day}: "
        f"{ret.airline} {hhmm(ret.depart_time)}発 → {hhmm(ret.arrive_time)}着"
        f"（片道 {yen(ret.price)}{_flight_no(ret.flight_number)}）",
        f"補正: {_surcharge_note(combo)}",
        f"往路検索: {oneway_url(out.origin, out.destination, weekend.saturday)}",
        f"復路検索: {oneway_url(ret.origin, ret.destination, weekend.sunday)}",
    ]
    return "\n".join(lines)


def _flight_no(number: str | None) -> str:
    return f" / {number}" if number else ""


_RANK_ORDER = {Rank.S: 0, Rank.A: 1, Rank.B: 2, Rank.NONE: 3}


def format_run(result: RunResult, max_total: int = 0) -> str:
    """全結果を1通に集約した本文を返す（要件3.6 集約）。

    Args:
        result: 実行結果
        max_total: 通知する最大件数（全路線通算）。0 なら無制限。
                   多空港運用でLINEの文字数上限を超えないための全体上限。

    ランク入りが0件なら空文字を返す。呼び出し側は通知しない。
    上限で省略した場合は「他N件」と本文に明記する（黙って捨てない）。
    """
    from .ranking import limit_total

    all_combos = result.notifiable
    if not all_combos:
        return ""

    combos = limit_total(all_combos, max_total)
    omitted = len(all_combos) - len(combos)

    # 表示順は安い順（多空港だと路線順よりお得順のほうが実用的）
    combos = sorted(
        combos,
        key=lambda c: (c.total_price, c.route.iata, c.weekend.index, c.outbound.depart_time),
    )

    if omitted > 0:
        header = f"週末の格安便が {len(all_combos)}件（安い順に {len(combos)}件を表示 / 他 {omitted}件）"
    else:
        header = f"週末の格安便が {len(combos)}件 見つかりました"

    blocks = [header] + [format_combination(c) for c in combos] + [FOOTER]
    return BLOCK_SEPARATOR.join(blocks)


def format_failure(result: RunResult) -> str:
    """全路線失敗時の障害通知本文（要件4.3 サイレント障害防止）。

    スタックトレースは載せない。運用者が次に何をすべきかだけを伝える。
    """
    lines = ["【取得失敗】航空券を取得できませんでした（全路線）", ""]
    for r in result.results:
        reason = (r.error or "不明").splitlines()[0][:120]
        lines.append(f"・{r.route.name}({r.route.iata}) {r.weekend.saturday}: {reason}")

    lines += [
        "",
        "取得元の仕様変更、またはBot判定によるIPブロックの可能性があります。",
        "全路線の失敗が3日連続した場合は、ローカル実行（自宅PC / Raspberry Pi）へ",
        "切り替えてください（docs/運用手順.md 参照）。",
    ]
    return "\n".join(lines)


def split_message(text: str, limit: int = MAX_TEXT_LENGTH) -> list[str]:
    """LINEの文字数上限で分割する（要件3.6: 5,000文字超の場合のみ分割）。

    1件分のブロック（空行区切り）の途中では切らない。
    単独で limit を超えるブロックのみ、やむを得ず文字数で切る。
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""

    for block in text.split(BLOCK_SEPARATOR):
        candidate = block if not current else current + BLOCK_SEPARATOR + block

        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(block) <= limit:
            current = block
        else:
            # 単独ブロックが上限超え（通常は起きない）。行単位 -> 文字数で切る。
            for piece in _hard_split(block, limit):
                chunks.append(piece)

    if current:
        chunks.append(current)
    return chunks


def _hard_split(block: str, limit: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for line in block.split("\n"):
        candidate = line if not current else current + "\n" + line
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            pieces.append(current)
            current = ""
        while len(line) > limit:
            pieces.append(line[:limit])
            line = line[limit:]
        current = line
    if current:
        pieces.append(current)
    return pieces
