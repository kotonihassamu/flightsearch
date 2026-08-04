# 週末格安航空券 自動発見・LINE通知システム

羽田（HND）発の週末弾丸旅行（土曜朝発・日曜夜帰着）向け格安国内線を毎日1回自動検索し、
お得な便だけを LINE に通知する個人用システム。

- 対応要件: `週末格安航空券通知システム_要件定義書_v3.md`（v3.0）
- 現在の状態: **実装すべき要件はすべて完了**。実データ取得・判定・通知本文まで動作確認済み
  （残るのは実環境での確認のみ: Phase 0 の3日連続 / LINE疎通 / Actions稼働）
- **Windowsでの実行手順（コマンド逐一）: [`docs/PowerShell実行手順.md`](docs/PowerShell実行手順.md)**
- 手動テストの考え方: [`docs/テスト手順.md`](docs/テスト手順.md)
- 開発計画: [`docs/開発ロードマップ.md`](docs/開発ロードマップ.md)
- 自動実行の設定: [`docs/GitHub設定手順.md`](docs/GitHub設定手順.md)
- **定時実行（7時前・18時前に確実に届かせる）: [`docs/定時実行の設定.md`](docs/定時実行の設定.md)**

---

## クイックスタート

```bash
# このフォルダ（フライト検索システム）で実行
python -m venv .venv
.venv\Scripts\activate                 # Windows
pip install -r requirements.txt

# テスト（143件）
pytest

# ドライラン — 外部接続なしで通知本文まで出力する
set PYTHONPATH=src
python -m flightdeal.main --dry-run

# 実装状況の確認
python -m flightdeal.main --status
```

`pytest` 用の `PYTHONPATH` は `pytest.ini` で設定済み。CLI を直接叩くときのみ
`set PYTHONPATH=src`（PowerShell は `$env:PYTHONPATH="src"`）が必要。

`--dry-run` は StubFetcher（固定のサンプル便）とコンソール出力を使うため、
Google Flights にも LINE にも一切接続しない。判定ロジックの確認はこれで行う。
`--today 2026-08-01` で基準日を上書きすれば、週末算出の挙動も確認できる。

---

## ディレクトリ構成

```
フライト検索システム/
├── 週末格安航空券通知システム_要件定義書_v3.md
├── config.json                  設定の一元管理（要件4.5）。ここだけでフェーズ移行できる
├── requirements.txt
├── pytest.ini
├── .env.example                 ローカル実行用の環境変数テンプレート
├── .gitignore
│
├── src/flightdeal/
│   ├── models.py           ✅  ドメインモデル（Flight / Combination / Rank ほか）
│   ├── config.py           ✅  config.json の読み込みと整合性検証
│   ├── logging_setup.py    ✅  構造化ログ（1行1JSON）
│   ├── status.py           ✅  実装状況レポート（--status）
│   ├── main.py             ✅  エントリポイント / CLI
│   │
│   ├── weekend.py          ✅  週末日付の算出（要件3.1）
│   ├── filters.py          ✅  時間帯フィルター・組み合わせ生成（要件3.3 / 3.2.1）
│   ├── pricing.py          ✅  LCC手荷物補正・実質価格（要件3.4）
│   ├── ranking.py          ✅  安さランク判定・上位N件（要件3.5）
│   ├── formatter.py        ✅  通知本文の組み立て（要件3.6）
│   ├── search_link.py      ✅  片道検索リンク生成（tfs形式）
│   ├── artifacts.py        ✅  障害時の生HTML保存（要件4.3）
│   ├── env.py              ✅  .env 読み込み（依存なし・要件4.4）
│   ├── pipeline.py         ✅  実行パイプライン（要件4.3）
│   │
│   ├── fetchers/
│   │   ├── base.py                 ✅  FlightFetcher 抽象インターフェース（要件3.2.2）
│   │   ├── stub.py                 ✅  StubFetcher / FixtureFetcher
│   │   └── fast_flights_fetcher.py ✅  requests+parser方式（primp回避・実取得OK）
│   │
│   └── notifiers/
│       ├── base.py         ✅  Notifier インターフェース
│       ├── console.py      ✅  ドライラン出力
│       └── line.py         ⚠️  LINE Messaging API Push（未疎通）
│
├── tests/
│   ├── conftest.py         ✅  共通フィクスチャ
│   ├── test_config.py      ✅  設定検証（通過する）
│   ├── test_fetchers.py    ✅  取得層（外部接続なし）
│   ├── test_weekend.py     ✅  週末算出の境界値（要件6.1）
│   ├── test_filters.py     ✅  時間帯境界値
│   ├── test_pricing.py     ✅  補正・混在ケース
│   ├── test_ranking.py     ✅  70% / 85% / max_price 境界値
│   ├── test_formatter.py   ✅  通知本文・分割
│   ├── test_pipeline.py    ✅  隔離・リトライ・上限・Phase 3構成
│   ├── test_notifiers.py   ✅  設定漏れ検知・トークン非漏洩
│   ├── test_main.py        ✅  CLI・終了コード
│   ├── test_artifacts.py   ✅  障害調査用ファイル保存
│   ├── test_env.py         ✅  .env パース・優先順位
│   ├── test_parser_regression.py ✅ 実HTMLでのパーサ回帰（未採取ならskip）
│   └── fixtures/                 合成データ + raw/（実HTML）
│
├── scripts/
│   ├── phase0_check.py     ✅  Phase 0 技術検証スクリプト（手元PCで実行）
│   └── pre_push_check.py   ✅  push前の秘匿情報チェック
│
├── docs/
│   ├── 開発ロードマップ.md
│   ├── PowerShell実行手順.md      Windowsでのコマンド逐一
│   ├── テスト手順.md              手動テストの手順書
│   ├── GitHub設定手順.md          自動実行の設定
│   ├── 定時実行の設定.md          外部cronで時刻どおりに動かす
│   ├── アーキテクチャ.md
│   ├── 運用手順.md
│   └── phase0_log.md             技術検証の記録（3日連続成功の証跡）
│
└── .github/workflows/daily.yml   日次実行（要件4.1）
```

✅ = 実装済み・テスト済み / ⚠️ = 実装済みだが実環境で未検証（現在 line.py のみ）

---

## 設計の要点

**片道分解方式（要件3.2.1）** — 往復検索は行わず、片道検索を2回（往路・復路）実行し、
組み合わせと合算はローカルで計算する。これによりスクレイピング難度が大きく下がる。

**取得層の抽象化（要件3.2.2）** — すべての取得は `FlightFetcher` インターフェース経由。
`config.json` の `fetcher` を書き換えるだけで stub / fast-flights / fixture を切り替えられ、
将来 Playwright や公式API へ移行しても上位ロジックは変更不要。

**設定によるフェーズ移行（要件4.5）** — `destinations[].enabled` と `weekends_ahead` だけで
Phase 1（2路線・第1週末）→ Phase 3（5路線・第2週末）へコード変更なしに移行できる。
設定検証は「有効路線数 × 週末数 × 2 ≤ 20検索」を強制する（要件4.3 負荷抑制）。

**純粋関数と副作用の分離** — 週末算出・フィルター・組み合わせ・補正・ランク判定はすべて
外部I/Oを持たない純粋関数。だからこそ単体テストが安定し、外部サイト依存部分は
フィクスチャテストに切り出せる（要件6）。

---

## 次にやること

ロジックは実装・テスト済み。残るのは**実環境でしか確認できないこと**の2つ。

### 1. Phase 0 — データ取得の検証（未実施）

`fast_flights_fetcher.py` は fast-flights の想定APIに対して実装してあるが、
実際のレスポンスで動作確認していない。ライブラリの版によってフィールド名・
時刻表記・通貨が異なりうるため、まずこれを確認する。

```bash
pip install -r requirements.txt
python scripts/phase0_check.py --dest HIJ --save
```

結果を `docs/phase0_log.md` に記録し、**3日連続で成功**することを確認する。
`--save` で保存した生レスポンスを見て、必要なら `_to_flight()` のマッピングを調整する。

### 2. Phase 2 — LINE通知の疎通（未実施）

LINE Developers で Messaging API チャネルを作り、`.env` にトークンとUIDを設定してから
`config.json` の `notifier` を `"line"` に変更する。

詳細な手順は [`docs/開発ロードマップ.md`](docs/開発ロードマップ.md) を参照。

---

## 注意事項

- 本システムは「発見の補助」であり、最終的な価格・空席は必ず各航空会社・予約サイトで確認すること（要件1.1 / R3）
- データ取得は非公式手段であり、恒久的な動作保証はない。個人利用・1日1回・最大20検索に抑制している（要件R1）
- LINEチャネルアクセストークンと宛先UIDは環境変数 / GitHub Secrets で管理し、コード・ログに出さない（要件4.4）
