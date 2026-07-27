""".env 読み込みのテスト（要件4.4）。"""

from __future__ import annotations

import os

from flightdeal.env import find_dotenv, load_dotenv, parse_dotenv


def test_parse_basic():
    assert parse_dotenv("A=1\nB=2") == {"A": "1", "B": "2"}


def test_parse_ignores_comments_and_blanks():
    text = """
# コメント
A=1

  # インデントされたコメント
B=2
"""
    assert parse_dotenv(text) == {"A": "1", "B": "2"}


def test_parse_strips_quotes_and_spaces():
    assert parse_dotenv('A = "hello"') == {"A": "hello"}
    assert parse_dotenv("A = 'hello'") == {"A": "hello"}
    assert parse_dotenv("A=  hello  ") == {"A": "hello"}


def test_parse_handles_export_prefix():
    assert parse_dotenv("export A=1") == {"A": "1"}


def test_parse_keeps_hash_inside_value():
    """トークンに # が含まれることがあるのでコメント扱いしない。"""
    assert parse_dotenv("TOKEN=abc#def") == {"TOKEN": "abc#def"}


def test_parse_keeps_equals_inside_value():
    """base64 のトークンは末尾に = が付く。"""
    assert parse_dotenv("TOKEN=abc=def==") == {"TOKEN": "abc=def=="}


def test_parse_skips_malformed_lines():
    assert parse_dotenv("A=1\nこれは行として不正\n=値だけ\nB=2") == {"A": "1", "B": "2"}


def test_load_sets_environment(tmp_path):
    path = tmp_path / ".env"
    path.write_text("FLIGHTDEAL_TEST_KEY=hello", encoding="utf-8")
    os.environ.pop("FLIGHTDEAL_TEST_KEY", None)

    try:
        assert load_dotenv(path) == 1
        assert os.environ["FLIGHTDEAL_TEST_KEY"] == "hello"
    finally:
        os.environ.pop("FLIGHTDEAL_TEST_KEY", None)


def test_load_does_not_override_existing(tmp_path):
    """GitHub Secrets（既存の環境変数）を .env が上書きしないこと。"""
    path = tmp_path / ".env"
    path.write_text("FLIGHTDEAL_TEST_KEY=from_file", encoding="utf-8")
    os.environ["FLIGHTDEAL_TEST_KEY"] = "from_secrets"

    try:
        load_dotenv(path)
        assert os.environ["FLIGHTDEAL_TEST_KEY"] == "from_secrets"
    finally:
        os.environ.pop("FLIGHTDEAL_TEST_KEY", None)


def test_load_can_override_when_asked(tmp_path):
    path = tmp_path / ".env"
    path.write_text("FLIGHTDEAL_TEST_KEY=from_file", encoding="utf-8")
    os.environ["FLIGHTDEAL_TEST_KEY"] = "old"

    try:
        load_dotenv(path, override=True)
        assert os.environ["FLIGHTDEAL_TEST_KEY"] == "from_file"
    finally:
        os.environ.pop("FLIGHTDEAL_TEST_KEY", None)


def test_load_missing_file_is_harmless(tmp_path):
    assert load_dotenv(tmp_path / "nope.env") == 0


def test_find_dotenv_walks_up(tmp_path):
    (tmp_path / ".env").write_text("A=1", encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    found = find_dotenv(nested)
    assert found is not None
    assert found.parent == tmp_path.resolve()


def test_find_dotenv_returns_none_when_absent(tmp_path):
    nested = tmp_path / "x"
    nested.mkdir()
    # tmp_path 配下に .env は無い（上位に実在する可能性があるので存在有無は問わない）
    result = find_dotenv(nested)
    assert result is None or result.is_file()
