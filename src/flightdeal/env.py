""".env ファイルの読み込み（要件4.4）。

秘匿情報は環境変数から注入する。ローカル実行では毎回 `$env:...` を打つのが
現実的でないため、`.env` があれば読み込む。

python-dotenv に依存しない最小実装。依存を1つ減らすことは、
「環境非依存で動く」という要件4.1 にも効く。

**既存の環境変数は上書きしない。** GitHub Actions では Secrets から環境変数として
渡ってくるので、そちらを優先させる（`.env` はリポジトリに入らないが、
誤ってコミットされた場合でも Secrets が勝つようにしておく）。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_NAME = ".env"


def find_dotenv(start: Path | None = None) -> Path | None:
    """カレントディレクトリから上へ辿って .env を探す。"""
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        candidate = directory / DEFAULT_NAME
        if candidate.is_file():
            return candidate
    return None


def parse_dotenv(text: str) -> dict[str, str]:
    """.env の中身を辞書にする。

    対応する書式:
        KEY=value
        KEY = value          （前後の空白は無視）
        export KEY=value     （export 接頭辞は無視）
        KEY="value"          （引用符は剥がす）
        # コメント行 / 空行  （無視）

    値の中の `#` はコメント扱いしない（トークンに # が含まれうるため）。
    """
    result: dict[str, str] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()

        key, sep, value = line.partition("=")
        if not sep:
            continue

        key = key.strip()
        if not key:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        result[key] = value

    return result


def load_dotenv(path: Path | None = None, *, override: bool = False) -> int:
    """.env を読み込んで環境変数に設定する。設定した件数を返す。

    Args:
        path: 読み込むファイル。省略時は find_dotenv() で探す
        override: True なら既存の環境変数も上書きする（既定は上書きしない）
    """
    target = path or find_dotenv()
    if target is None or not target.is_file():
        return 0

    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        log.warning("dotenv_read_failed", extra={"path": str(target), "error": str(e)})
        return 0

    applied = 0
    for key, value in parse_dotenv(text).items():
        if not override and key in os.environ:
            continue
        os.environ[key] = value
        applied += 1

    if applied:
        # 値そのものは絶対にログへ出さない（要件4.4）。キー名と件数のみ。
        log.info("dotenv_loaded", extra={"path": str(target), "count": applied})

    return applied
