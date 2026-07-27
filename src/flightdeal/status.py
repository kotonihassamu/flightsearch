"""実装状況レポート（骨組み専用の補助モジュール）。

各モジュールのソースを走査し、NotImplementedError を送出したままの関数を
「未実装」として一覧表示する。実装が進めば自動的にリストから消える。
Phase 1 完了時点で「未実装: 0件」になることが目安。
"""

from __future__ import annotations

import ast
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent

PHASE_HINT = {
    "weekend": "Phase 1",
    "filters": "Phase 1",
    "pricing": "Phase 1",
    "ranking": "Phase 1",
    "pipeline": "Phase 1",
    "formatter": "Phase 1 / 2",
    "notifiers.line": "Phase 2",
    "fetchers.fast_flights_fetcher": "Phase 0 検証後",
}


def _module_label(path: Path) -> str:
    rel = path.relative_to(PKG_DIR).with_suffix("")
    return ".".join(rel.parts)


def _raises_not_implemented(node: ast.FunctionDef) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Raise) and child.exc is not None:
            exc = child.exc
            name = None
            if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
                name = exc.func.id
            elif isinstance(exc, ast.Name):
                name = exc.id
            if name == "NotImplementedError":
                return True
    return False


def scan() -> list[tuple[str, str, str]]:
    """(モジュール, 関数名, フェーズ) のリストを返す。"""
    found: list[tuple[str, str, str]] = []
    for path in sorted(PKG_DIR.rglob("*.py")):
        if path.name in ("status.py", "__init__.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = _module_label(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _raises_not_implemented(node):
                    found.append((module, node.name, PHASE_HINT.get(module, "-")))
    return found


def render(config_path: str | None = None) -> str:
    lines: list[str] = []
    lines.append("週末格安航空券 通知システム — 実装状況")
    lines.append("=" * 60)

    try:
        from .config import load_config

        cfg = load_config(config_path)
        lines.append(f"設定読み込み            : OK ({len(cfg.destinations)}路線定義)")
        lines.append(f"  有効路線              : {[d.iata for d in cfg.enabled_destinations]}")
        lines.append(f"  weekends_ahead        : {cfg.weekends_ahead}")
        lines.append(f"  fetcher / notifier    : {cfg.fetcher} / {cfg.notifier}")
    except Exception as e:  # pragma: no cover
        lines.append(f"設定読み込み            : NG ({e})")

    todos = scan()
    lines.append("")
    lines.append(f"未実装の関数            : {len(todos)}件")
    lines.append("-" * 60)
    current = ""
    for module, func, phase in todos:
        if module != current:
            lines.append(f"[{module}]")
            current = module
        lines.append(f"  - {func:<28} ({phase})")

    if not todos:
        lines.append("  （なし）— Phase 1 相当のロジックはすべて実装済みです。")
        lines.append("")
        lines.append("残りは実環境での確認作業です:")
        lines.append("  - Phase 0: python scripts/phase0_check.py --dest HIJ （3日連続で成功）")
        lines.append("  - Phase 2: LINEトークン設定 → config.json を line / fast_flights に変更")
        lines.append("  - 詳細は docs/開発ロードマップ.md")

    return "\n".join(lines)
