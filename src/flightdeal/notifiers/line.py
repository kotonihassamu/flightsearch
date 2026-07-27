"""LINE Messaging API（Push Message）通知（要件3.6 / 4.4）。

LINE Notify はサービス終了済みのため使用しない。

必要な環境変数（GitHub Secrets / ローカルは .env）:
  LINE_CHANNEL_ACCESS_TOKEN  チャネルアクセストークン（長期）
  LINE_TO_USER_ID            送信先ユーザーID（自分のUID）

トークン・UIDはコードにもログにも出力しない（要件4.4）。
このモジュールでは例外メッセージにもトークンを含めないよう注意すること。
"""

from __future__ import annotations

import logging
import os

from ..formatter import split_message
from .base import Notifier, NotifyError

log = logging.getLogger(__name__)

PUSH_ENDPOINT = "https://api.line.me/v2/bot/message/push"
MAX_TEXT_LENGTH = 5000  # LINE のテキストメッセージ上限
MAX_MESSAGES_PER_RUN = 2  # 無料枠に配慮（要件R6）
TIMEOUT_SECONDS = 20


class LineNotifier(Notifier):
    name = "line"

    def __init__(self, token: str | None = None, to_user_id: str | None = None) -> None:
        self.token = token or os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
        self.to_user_id = to_user_id or os.environ.get("LINE_TO_USER_ID", "")

    @property
    def configured(self) -> bool:
        return bool(self.token and self.to_user_id)

    def send(self, text: str) -> None:
        """Push Message を送信する。

        Raises:
            NotifyError: 設定漏れ、または送信失敗
        """
        if not self.configured:
            missing = []
            if not self.token:
                missing.append("LINE_CHANNEL_ACCESS_TOKEN")
            if not self.to_user_id:
                missing.append("LINE_TO_USER_ID")
            raise NotifyError(f"環境変数が未設定です: {', '.join(missing)}")

        try:
            import requests
        except ImportError as e:  # pragma: no cover
            raise NotifyError(
                "requests がインストールされていません。"
                "`pip install -r requirements.txt` を実行してください。"
            ) from e

        chunks = split_message(text, MAX_TEXT_LENGTH)
        if len(chunks) > MAX_MESSAGES_PER_RUN:
            log.warning(
                "line_truncated",
                extra={"chunks": len(chunks), "limit": MAX_MESSAGES_PER_RUN},
            )
            chunks = chunks[:MAX_MESSAGES_PER_RUN]

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        for index, chunk in enumerate(chunks, start=1):
            try:
                response = requests.post(
                    PUSH_ENDPOINT,
                    headers=headers,
                    json={"to": self.to_user_id, "messages": [{"type": "text", "text": chunk}]},
                    timeout=TIMEOUT_SECONDS,
                )
            except Exception as e:
                raise NotifyError(f"LINE送信に失敗しました ({index}/{len(chunks)}): {e}") from e

            if response.status_code != 200:
                # レスポンス本文にトークンは含まれないが、念のため長さを制限する
                raise NotifyError(
                    f"LINE送信に失敗しました ({index}/{len(chunks)}): "
                    f"status={response.status_code} body={response.text[:300]}"
                )

            log.info("line_sent", extra={"chunk": index, "of": len(chunks), "chars": len(chunk)})
