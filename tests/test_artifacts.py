"""障害調査用アーティファクト保存のテスト（要件4.3 失敗の可視化）。"""

from __future__ import annotations

import os
from pathlib import Path

from flightdeal import artifacts


def test_save_debug_writes_file(tmp_path):
    path = artifacts.save_debug("<html>test</html>", "HND-HIJ-2026-08-01", directory=tmp_path)

    assert path is not None
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "<html>test</html>"
    assert path.suffix == ".html"
    assert "HND-HIJ-2026-08-01" in path.name


def test_save_debug_sanitizes_label(tmp_path):
    """ラベルにパス区切りが混ざってもディレクトリを抜け出さない。"""
    path = artifacts.save_debug("x", "../../etc/passwd", directory=tmp_path)

    assert path is not None
    assert path.parent == tmp_path
    assert ".." not in path.name


def test_save_debug_ignores_empty_content(tmp_path):
    assert artifacts.save_debug("", "label", directory=tmp_path) is None


def test_save_debug_truncates_huge_content(tmp_path):
    path = artifacts.save_debug("y" * (artifacts.MAX_BYTES + 1000), "big", directory=tmp_path)
    assert path is not None
    assert len(path.read_text(encoding="utf-8")) == artifacts.MAX_BYTES


def test_save_debug_creates_missing_directory(tmp_path):
    target = tmp_path / "nested" / "dir"
    path = artifacts.save_debug("x", "label", directory=target)
    assert path is not None
    assert target.is_dir()


def test_save_debug_returns_none_on_error(tmp_path):
    """保存に失敗しても例外を投げず None を返す（本処理を止めない）。"""
    blocker = tmp_path / "blocked"
    blocker.write_text("I am a file, not a directory", encoding="utf-8")

    assert artifacts.save_debug("x", "label", directory=blocker) is None


def test_artifact_dir_respects_env(tmp_path):
    """環境変数で保存先を変えられる（GitHub Actions 用）。

    Windows では Path が区切り文字を正規化するため、文字列ではなく Path で比較する。
    """
    original = os.environ.get(artifacts.ENV_KEY)
    try:
        os.environ[artifacts.ENV_KEY] = str(tmp_path)
        assert artifacts.artifact_dir() == Path(tmp_path)

        os.environ.pop(artifacts.ENV_KEY)
        assert artifacts.artifact_dir() == Path(artifacts.DEFAULT_DIR)
    finally:
        if original is None:
            os.environ.pop(artifacts.ENV_KEY, None)
        else:
            os.environ[artifacts.ENV_KEY] = original


def test_artifact_dir_ignores_empty_env():
    """環境変数が空文字なら既定値にフォールバックする。"""
    original = os.environ.get(artifacts.ENV_KEY)
    try:
        os.environ[artifacts.ENV_KEY] = ""
        assert artifacts.artifact_dir() == Path(artifacts.DEFAULT_DIR)
    finally:
        if original is None:
            os.environ.pop(artifacts.ENV_KEY, None)
        else:
            os.environ[artifacts.ENV_KEY] = original
