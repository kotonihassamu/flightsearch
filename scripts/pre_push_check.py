#!/usr/bin/env python3
"""push 前の安全チェック（要件4.4）。

秘匿情報をリポジトリに入れてしまう事故は、起きてから気づいても手遅れ
（履歴に残るためトークンの再発行が必須になる）。push の前に必ず走らせる。

    python scripts/pre_push_check.py

チェック内容:
  1. .env が git の管理対象に入っていないか
  2. 追跡対象ファイルに LINE トークンらしき文字列が含まれていないか
  3. config.json が壊れていないか（UTF-8の正しいJSON）
  4. 巨大ファイルが紛れていないか

終了コード 0 = 安全。1 = 問題あり（push しないこと）。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# LINEのチャネルアクセストークン（長期）は非常に長いbase64風文字列
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9+/]{80,}={0,2}")
# チャネルシークレットは32桁の16進
SECRET_PATTERN = re.compile(r"\b[0-9a-f]{32}\b")

SKIP_SUFFIXES = {".html", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".pdf"}
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "artifacts", "_to_delete"}
MAX_FILE_MB = 10


def git(*args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return proc.returncode, proc.stdout


def tracked_files() -> list[Path] | None:
    code, out = git("ls-files")
    if code != 0:
        return None
    return [ROOT / line for line in out.splitlines() if line.strip()]


def check_env_not_tracked(files: list[Path]) -> list[str]:
    problems = []
    for f in files:
        if f.name == ".env" or f.name.endswith(".env"):
            if f.name != ".env.example":
                problems.append(f"{f.relative_to(ROOT)} が git の管理対象に入っています")
    return problems


def check_no_secrets(files: list[Path]) -> list[str]:
    problems = []
    for f in files:
        if f.suffix.lower() in SKIP_SUFFIXES or not f.is_file():
            continue
        if any(part in SKIP_DIRS for part in f.parts):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        rel = f.relative_to(ROOT)
        for m in TOKEN_PATTERN.finditer(text):
            # 誤検知しやすいもの（tfsパラメータ等）は除外
            line = text[: m.start()].count("\n") + 1
            problems.append(f"{rel}:{line} 長いトークン風の文字列（要確認）: {m.group()[:20]}...")
        if f.name != "pre_push_check.py":
            for m in SECRET_PATTERN.finditer(text):
                line = text[: m.start()].count("\n") + 1
                problems.append(f"{rel}:{line} 32桁hex（チャネルシークレット？）: {m.group()[:8]}...")
    return problems


def check_config_valid() -> list[str]:
    path = ROOT / "config.json"
    if not path.exists():
        return ["config.json が見つかりません"]
    try:
        json.loads(path.read_bytes().decode("utf-8"))
    except Exception as e:
        return [f"config.json が壊れています: {e}"]
    return []


def check_file_sizes(files: list[Path]) -> list[str]:
    problems = []
    for f in files:
        if not f.is_file():
            continue
        mb = f.stat().st_size / 1_000_000
        if mb > MAX_FILE_MB:
            problems.append(f"{f.relative_to(ROOT)} が大きすぎます（{mb:.1f}MB）")
    return problems


def main() -> int:
    print("push 前チェック")
    print("=" * 55)

    files = tracked_files()
    if files is None:
        print("git リポジトリではありません（まだ git init していない）。")
        print("先に git init してから再実行してください。")
        return 1

    print(f"追跡対象ファイル: {len(files)} 件\n")

    checks = [
        ("秘匿ファイル(.env)", check_env_not_tracked(files)),
        ("トークン混入", check_no_secrets(files)),
        ("config.json", check_config_valid()),
        ("ファイルサイズ", check_file_sizes(files)),
    ]

    failed = False
    for label, problems in checks:
        if problems:
            failed = True
            print(f"[NG] {label}")
            for p in problems[:10]:
                print(f"     - {p}")
            if len(problems) > 10:
                print(f"     ... 他 {len(problems) - 10} 件")
        else:
            print(f"[OK] {label}")

    print("=" * 55)
    if failed:
        print("問題が見つかりました。push しないでください。")
        print("秘匿情報が含まれる場合は、該当ファイルを .gitignore に追加し")
        print("`git rm --cached <file>` で管理対象から外してください。")
        return 1

    print("問題なし。push して大丈夫です。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
