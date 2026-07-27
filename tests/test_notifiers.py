"""通知層のテスト。外部送信は行わない（要件6.2）。"""

from __future__ import annotations

import pytest

from flightdeal.notifiers import ConsoleNotifier, NotifyError, build_notifier
from flightdeal.notifiers.line import LineNotifier


def test_build_notifier_console():
    assert isinstance(build_notifier("console"), ConsoleNotifier)


def test_build_notifier_unknown():
    with pytest.raises(ValueError):
        build_notifier("smoke_signal")


def test_console_notifier_prints():
    ConsoleNotifier().send("テスト本文")  # 例外が出なければよい


def test_line_notifier_reports_missing_env():
    """設定漏れは送信前に検知する（要件4.4）。"""
    notifier = LineNotifier(token="", to_user_id="")
    assert not notifier.configured
    with pytest.raises(NotifyError, match="LINE_CHANNEL_ACCESS_TOKEN"):
        notifier.send("本文")


def test_line_notifier_reports_missing_user_id():
    notifier = LineNotifier(token="dummy-token", to_user_id="")
    with pytest.raises(NotifyError, match="LINE_TO_USER_ID"):
        notifier.send("本文")


def test_line_notifier_configured_flag():
    assert LineNotifier(token="t", to_user_id="U123").configured


def test_line_notifier_never_leaks_token_in_error():
    """例外メッセージにトークンを含めない（要件4.4）。"""
    secret = "super-secret-token-value"
    notifier = LineNotifier(token=secret, to_user_id="")
    try:
        notifier.send("本文")
    except NotifyError as e:
        assert secret not in str(e)
    else:
        raise AssertionError("NotifyError が送出されませんでした")
