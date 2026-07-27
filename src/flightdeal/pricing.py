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
    return re.sub(r"[\s\-_.]", "", normalized)


def classify_airline(airline: str, cfg: Config) -> AirlineClass:
    """航空会社名から補正区分を判定する（要件3.4）。

    設定値との部分一致で判定するため、"Solaseed Air" と設定値 "Solaseed" のような
    表記ゆれを吸収できる。誤判定を避けるため FSC を先に評価する。
    """
    if not airline or not airline.strip():
        return AirlineClass.UNKNOWN

    target = _normalize_airline(airline)

    for name in cfg.fsc_airlines:
        key = _normalize_airline(name)
        if key and (key in target or target in key):
            return AirlineClass.FSC

    for name in cfg.lcc_airlines:
        key = _normalize_airline(name)
        if key and (key in target or target in key):
            return AirlineClass.LCC

    return AirlineClass.UNKNOWN


def surcharge_for(airline: str, cfg: Config) -> tuple[int, bool]:
    """片道あたりの補正額と「暫定フラグ」を返す（要件3.4）。

    Returns:
        (補正額, provisional)
        provisional=True のとき、通知本文に「補正額は仮」の注記を入れる。
    """
    kind = classify_airline(airline, cfg)
    if kind is AirlineClass.FSC:
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
    out_sc, out_prov = surcharge_for(outbound.airline, cfg)
    in_sc, in_prov = surcharge_for(inbound.airline, cfg)
    total = outbound.price + out_sc + inbound.price + in_sc
    return total, out_sc, in_sc, (out_prov or in_prov)
