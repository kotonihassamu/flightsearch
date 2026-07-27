"""構造化ログの初期化（要件4.3「ログ」）。

標準出力へ1行1JSONで出す。GitHub Actions のログでも grep しやすく、
ローカル実行へ切り替えても同じ形式で残る（要件4.1 環境非依存）。

骨組み段階でも動作する必要があるため実装済み。
"""

from __future__ import annotations

import json
import logging
import sys

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def ensure_console_encoding() -> None:
    """コンソールの文字コードで落ちないようにする（Windows対策）。

    日本語WindowsのPowerShell/コマンドプロンプトは既定が cp932 のため、
    そこに含まれない文字を print すると UnicodeEncodeError で異常終了する。
    通知本文は cp932 で表現できる文字だけで組み立てているが、将来の文言追加や
    航空会社名に想定外の文字が混ざっても落ちないよう、置換出力にしておく。

    `chcp 65001` 済み（UTF-8）の端末では何も変わらない。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # パイプ・リダイレクト時など
            continue
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError):  # pragma: no cover
            pass


def setup_logging(level: int = logging.INFO) -> None:
    ensure_console_encoding()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
