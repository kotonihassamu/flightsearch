# フィクスチャ（要件6.2）

外部サイトへ接続するテストは CI の合否条件に含めない。
代わりに保存済みのデータを入力にして、パース部を検証する。

## 2種類ある

| 場所 | 中身 | 用途 | テスト |
|---|---|---|---|
| `./*.json` | **正規化済みの合成データ**（手書き） | `FixtureFetcher` の動作確認 | `test_fetchers.py` |
| `./raw/*.html` | **実際に取得した生HTML** | パーサの回帰テスト | `test_parser_regression.py` |

生HTMLの採取方法は [`raw/README.md`](raw/README.md) を参照。

## 正規化済みフィクスチャの形式

`FixtureFetcher` が読む形式。ファイル名は `<ORIGIN>-<DEST>-<YYYY-MM-DD>.json`。

```json
[
  {
    "airline": "ANA",
    "depart_time": "07:25",
    "arrive_time": "08:50",
    "price": 11400,
    "flight_number": "NH673"
  }
]
```

> 現在置いてある `HND-HIJ-2026-08-01.json` は**手書きの合成データ**（実在の便ではない）。
> `FixtureFetcher` が正しく読めるかの確認用であり、実勢価格を表すものではない。
> 実データの回帰テストは `raw/` の生HTMLで行う。

`python scripts/phase0_check.py --save` を使うと、実取得した結果をこの形式で
保存できる（合成データを実データで置き換えたい場合に使う）。
