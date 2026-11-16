"""LCC手荷物料金の補正と実質価格の算出（要件3.4）。

補正は片道単位。
  実質価格（往復） = 往路価格 + 往路補正 + 復路価格 + 復路補正
"""

from __future__ import annotations

import re
import unicodedata

from .config import Config
from .models import AirlineClass, Flight

_DIGITS = re.compile(r"\d+")


def parse_price(raw: str | int | float) -> int:
    """'¥11,400' / '11400' / '￥ 9,800' などを整数に正規化する（要件3.2.2）。

    Raises:
        ValueError: 数値を取り出せない場合（呼び出し側で除外扱いにする）
    """
    if isinstance(raw, bool):  # bool は int の派生なので明示的に弾く
        raise ValueError(f"価格として不正な値です: {raw!r}")
    if isinstance(raw, (int, float)):
        return int(raw)

    # 全角数字・全角記号を半角へ寄せてから数字だけ取り出す
    normalized = unicodedata.normalize("NFKC", str(raw))
    digits = "".join(_DIGITS.findall(normalized))
    if not digits:
        raise ValueError(f"価格を数値化できません: {raw!r}")
    return int(digits)


def _normalize_airline(name: str) -> str:
    """比較用に航空会社名を正規化する（大小文字・空白・記号の揺れを吸収）。"""
    normalized = unicodedata.normalize("NFKC", name).lower()
    # 「エア・ドゥ」「スプリング・ジャパン」のような中黒も揺れとして吸収する
    return re.sub(r"[\s\-_.・]", "", normalized)


def classify_airline(airline: str, cfg: Config) -> AirlineClass:
    """航空会社名から補正区分を判定する（要件3.4）。

    設定値との部分一致で判定するため、"Solaseed Air" と設定値 "Solaseed" のような
    表記ゆれを吸収できる。Google Flights は language=ja だと航空会社名を日本語
    （「スカイマーク」等）で返すため、設定には英語名と日本語名の両方を並べる。

    評価順は FSC → 機内持ち込み無料 → LCC。補正なし側を先に評価し、
    部分一致の重なりで誤って補正をかけないようにする。
    """
    if not airline or not airline.strip():
        return AirlineClass.UNKNOWN

    target = _normalize_airline(airline)

    for name in cfg.fsc_airlines:
        key = _normalize_airline(name)
        if key and (key in target or target in key):
            return AirlineClass.FSC

    for name in cfg.carry_on_free_airlines:
        key = _normalize_airline(name)
        if key and (key in target or target in key):
            return AirlineClass.CARRY_ON

    for name in cfg.lcc_airlines:
        key = _normalize_airline(name)
        if key and (key in target or target in key):
            return AirlineClass.LCC

    return AirlineClass.UNKNOWN


def surcharge_for(
    airline: str, cfg: Config, carry_on_included: bool | None = None
) -> tuple[int, bool]:
    """片道あたりの補正額と「暫定フラグ」を返す（要件3.4）。

    判定の優先順:
      1. Google Flights の運賃情報（carry_on_included）があればそれに従う。
         機内持ち込み手荷物が含まれる運賃なら +0円、含まれないなら補正額を加える。
         LCCでも持ち込み1個が無料なら補正しない、という方針をそのまま表す。
      2. 情報が無ければ航空会社リストで判定する（FSC・機内持ち込み無料 → +0円、
         LCC → 補正額、リスト外 → 補正額＋「仮」注記）。

    Returns:
        (補正額, provisional)
        provisional=True のとき、通知本文に「補正額は仮」の注記を入れる。
    """
    if carry_on_included is True:
        return 0, False
    if carry_on_included is False:
        return cfg.baggage_surcharge_oneway, False

    kind = classify_airline(airline, cfg)
    if kind in (AirlineClass.FSC, AirlineClass.CARRY_ON):
        # FSC は受託手荷物込み。LCC・中堅でも機内持ち込み1個が無料なら補正しない。
        return 0, False
    if kind is AirlineClass.LCC:
        return cfg.baggage_surcharge_oneway, False
    # リスト外はLCC扱い（安全側に倒す）＋通知で注記
    return cfg.baggage_surcharge_oneway, True


def effective_price(
    outbound: Flight, inbound: Flight, cfg: Config
) -> tuple[int, int, int, bool]:
    """実質価格（往復）を算出する。

    Returns:
        (実質価格, 往路補正, 復路補正, provisional)
    """
    out_sc, out_prov = surcharge_for(outbound.airline, cfg, outbound.carry_on_included)
    in_sc, in_prov = surcharge_for(inbound.airline, cfg, inbound.carry_on_included)
    total = outbound.price + out_sc + inbound.price + in_sc
    return total, out_sc, in_sc, (out_prov or in_prov)
