"""障害調査用アーティファクトの保存（要件4.3「失敗の可視化」）。

取得や解析に失敗したとき、そのときのレスポンス本文を残しておかないと
「なぜ壊れたのか」を後から調べられない（サイレント障害の一種）。

保存先は既定で `./artifacts/`。GitHub Actions ではこのディレクトリが
`actions/upload-artifact` で回収され、7日間保持される（daily.yml）。
環境変数 `FLIGHTDEAL_ARTIFACT_DIR` で変更できる。

保存は best-effort。ここでの失敗が本処理を止めてはいけない。
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

ENV_KEY = "FLIGHTDEAL_ARTIFACT_DIR"
DEFAULT_DIR = "artifacts"
MAX_BYTES = 5_000_000  # 1ファイル5MBまで（Google Flightsは約2MB）

_SAFE = re.compile(r"[^0-9A-Za-z._-]+")


def artifact_dir() -> Path:
    return Path(os.environ.get(ENV_KEY) or DEFAULT_DIR)


def _safe(label: str) -> str:
    """ファイル名に使える文字だけにする。

    パス区切りだけでなく連続ドットも潰す。`..` が残っても Path 結合の仕方から
    ディレクトリを抜け出すことはないが、紛らわしい名前を作らないため。
    """
    cleaned = _SAFE.sub("_", label)
    while ".." in cleaned:
        cleaned = cleaned.replace("..", "_")
    return cleaned.strip("._") or "unknown"


def save_debug(
    content: str,
    label: str,
    suffix: str = ".html",
    directory: Path | None = None,
) -> Path | None:
    """調査用の本文を保存し、パスを返す。失敗した場合は None。

    Args:
        content: 保存する本文（HTML等）
        label: ファイル名に使う識別子（例 "HND-HIJ-2026-08-01"）
        suffix: 拡張子
        directory: 保存先。省略時は artifact_dir()
    """
    if not content:
        return None

    target_dir = directory or artifact_dir()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = target_dir / f"{stamp}_{_safe(label)}{suffix}"

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(content[:MAX_BYTES], encoding="utf-8", errors="replace")
    except OSError as e:  # ディスクフル・権限など。本処理は止めない。
        log.warning("artifact_save_failed", extra={"label": label, "error": str(e)})
        return None

    log.info("artifact_saved", extra={"path": str(path), "bytes": path.stat().st_size})
    return path
