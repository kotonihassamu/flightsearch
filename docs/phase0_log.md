# Phase 0 技術検証ログ

> 完了条件: **3日連続**で、価格・時刻・航空会社名が取得できること（要件2）

```powershell
python scripts\phase0_check.py --dest HIJ --save --save-raw
```

## ライブラリ調査

| 項目 | 内容 | 確認日 |
|---|---|---|
| fast-flights バージョン | 3.0.2 | 2026-07-27 |
| API | 2系から全面変更。`FlightQuery` + `create_filter` + `parse` | 2026-07-27 |
| primp（内部HTTP） | 環境依存でDNS "Query Refused"。requests方式で回避 | 2026-07-27 |
| 採用判断 | fast-flights（取得=requests / 解析=parser）で確定 | 2026-07-27 |

---

## 実行記録

### Day 1 — 2026-07-27 ✅ 成功

- 区間 / 対象日: HND → HIJ / 2026-08-01（土）
- 方式: FastFlightsFetcher（requests + fast-flights parser）
- **取得件数: 12件**
- 航空会社名: ✅ ANA / JAL
- 出発・到着時刻: ✅ 全便で取得
- 価格（JPY）: ✅ ¥20,590 〜 ¥33,570（片道）
- 直行便の絞り込み: ✅ `max_stops=0` で全件直行
- 便名: ❌ parser が非対応（None。要件上は任意項目）
- 生HTML: ✅ `tests/fixtures/raw/HND-HIJ-2026-08-01.html`（2,231,384 文字）
- 正規化フィクスチャ: ✅ `tests/fixtures/HND-HIJ-2026-08-01.json`

取得できた便（抜粋）:

```
ANA 18:10 → 19:35  ¥20,590      JAL 08:45 → 10:05  ¥22,790
ANA 19:40 → 21:00  ¥20,590      JAL 10:10 → 11:30  ¥22,790
JAL 07:30 → 08:50  ¥23,120      ANA 08:10 → 09:30  ¥24,880
```

備考:
- primp 直呼びは DNS 拒否で失敗。requests 経由で解決（この方式を正式採用）
- 時間帯フィルター（11時までに到着）を満たすのは 12便中4便
- 実勢の最安往復は ¥43,270（`cheapest_total`）。config の相場 35,000 より高いため
  現状では通知対象なし＝正しい判定

### Day 2 — ____-__-__

- 実行日時:
- 取得件数:
- 航空会社名 / 時刻 / 価格:
- 結果: 成功 / 失敗
- `cheapest_total`:
- 備考:

### Day 3 — ____-__-__

- 実行日時:
- 取得件数:
- 航空会社名 / 時刻 / 価格:
- 結果: 成功 / 失敗
- `cheapest_total`:
- 備考:

---

## 判断（0-8）

- **採用方式**: fast-flights（取得=requests / 解析=`fast_flights.parser`、primp回避）
- 判断日: 2026-07-27（1日目成功。3日連続確認で正式完了）
- 理由: primp が本環境でDNS拒否される。requests は正常動作し、
  解析器は fast-flights のものをそのまま使えるため保守コストが低い。
- フォールバック: 将来この方式も失敗するようになったら Playwright を実装
  （`build_fetcher` に登録するだけでよい設計）

## 相場調整のメモ（要件 Phase 1-17）

毎回の `route_done` ログに出る `cheapest_total` を記録していくと、
その路線の「普段の価格」が見えてくる。数週間ぶんたまったら `market_price` を設定する。

| 日付 | 路線 | 対象週末 | cheapest_total |
|---|---|---|---|
| 2026-07-27 | HIJ | 8/1-8/2 | ¥43,270 |
| 2026-07-27 | MYJ | 8/1-8/2 | ¥66,570 |
| | | | |
