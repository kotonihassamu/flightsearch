# 多空港対応とVPN（要件変更）

当初の要件（MVP2路線・1実行20検索まで）を、**全国20空港**へ拡張した。
検索数が増えるとGoogleにBot判定されやすくなるため、投資スクレイパ(nikkei_DB)で
使っている**VPN(Surfshark/WireGuard)によるIP切替**を取り込んだ。

## 対象空港（20）

HND発・直行便のある空港。

| 地域 | 空港 |
|---|---|
| 中国・四国 | 広島 HIJ / 松山 MYJ / 高知 KCH |
| 北陸・近畿 | 小松 KMQ / 南紀白浜 SHM |
| 九州・沖縄 | 福岡 FUK / 長崎 NGS / 宮崎 KMI / 大分 OIT / 鹿児島 KOJ / 那覇 OKA |
| 北海道（全空港） | 新千歳 CTS / 函館 HKD / 旭川 AKJ / 女満別 MMB / 釧路 KUH / 帯広 OBO / 稚内 WKJ / 中標津 SHB / 紋別 MBE |

追加したい空港があれば `config.json` の `destinations` に1件足すだけ。
IATAコードと `market_price` / `max_price`（暫定値でよい。survey で調整）を入れる。

## 変更した要件

| 項目 | 変更前 | 変更後 |
|---|---|---|
| 対象路線 | MVP 2路線 | 20空港 |
| 1実行の検索上限 | 20 | 100（`config.json` の `max_searches_per_run`） |
| Bot対策 | GitHub Actions失敗3日でローカル切替 | **VPNでIPを切り替えながらローカル実行** |
| 実行場所 | GitHub Actions中心 | **ローカル中心**（VPNはローカルでしか使えない） |

## なぜローカル中心になるか

Surfshark/WireGuard はこのPCのVPN。**GitHub Actions（クラウド）からは使えない**。
20空港をVPNで回すなら実行はローカル。GitHub Actions は使うなら少数路線の見張り用。

## VPN設定（config.json の `vpn`）

```json
"vpn": {
  "enabled": false,          // true で常時VPN必須。survey は --vpn でも有効化できる
  "mode": "manual",          // "manual"（v6方式・確実） / "auto"（v5方式・要管理者） / "off"
  "conf_dir": "VPN",         // .conf 置き場（nikkei_DB/VPN を指してもよい）
  "home_ip": "",             // 自宅の外部IP（分かれば。自宅IP検出に使う）
  "home_org_hint": "",       // 自宅ISP名の一部（org に含まれれば自宅とみなす）
  "wireguard_exe": "",       // 空なら既定パスを自動探索
  "switch_timeout": 40
}
```

### home_ip / home_org_hint の調べ方

VPNを切った状態で:

```powershell
python -c "import requests; print(requests.get('https://ipinfo.io/json').json())"
```

出た `ip` を `home_ip` に、`org`（例 "AS17676 SoftBank"）の一部を `home_org_hint` に入れる。
これで「VPN未接続のまま実行」を検出して止められる（v6の require_vpn と同じ）。

### mode の選び方

- **manual（推奨）**: Bot判定を検知したら「Surfsharkで別サーバーに繋いで」と促し、
  IPの変化を検出したら自動再開する。v6で実績のある確実な方式。
- **auto**: `wireguard.exe /installtunnelservice` でトンネルを付け替える。管理者権限が必要。
  v5で試したが「このPCでは不安定」だった実績があるので、まず manual を使うこと。
  auto が失敗したら自動で manual にフォールバックする。
- **off**: VPNを使わない。

### .conf ファイル

nikkei_DB の `VPN/` フォルダの `.conf` をそのまま使える。`conf_dir` に
そのパスを指定するか、このプロジェクトに `VPN/` を作ってコピーする。

## 使い方

### 調査（survey）— まずこれで全空港の相場を知る

```powershell
# 全空港・4週先まで・VPNあり
python scripts\survey.py --all --weeks 4 --vpn

# VPNなしで少なめに試す（自宅IPで数十件なら通ることが多い）
python scripts\survey.py --all --weeks 2
```

- `--all`: `enabled` に関わらず config の全空港が対象
- `--vpn`: VPN必須で実行。Bot判定時に mode に従って切替
- 検索数が60を超えると確認プロンプトが出る（`--yes` でスキップ）

Bot判定を検知すると:
```
    Bot判定: Bot判定/アクセス制限を検知 (HND-WKJ ...): HTTP 429
⚠ Bot判定を検知しました。VPNサーバーを切り替えてください。
```
manual なら Surfshark で別サーバーに繋ぐと自動で再開する。

### 日次通知（多空港）

`config.json` の `vpn.enabled` を true にして `home_ip`/`home_org_hint` を設定してから:

```powershell
python -m flightdeal.main
```

VPN未接続なら起動時に止まる。Bot判定時はリトライ内で失敗し、
3日連続で全滅ならローカル運用の見直し（`docs/運用手順.md`）。

> **注意**: 20路線すべてにお得便が出る極端な日は通知が3通になり、LINE無料枠に配慮した
> 2通制限で末尾が切れる。通常は数路線しか該当しないため問題にならないが、
> 気になる場合は `notify_top_n_per_route` を 1 にするか、路線を絞る。

## 検索量の目安

| 対象 | 週数 | 検索数 | 目安時間（待機5〜15秒込み） |
|---|---|---|---|
| 全20空港 | 1 | 40 | 約10分 |
| 全20空港 | 4 | 160 | 約40分 |
| 全20空港 | 13（3か月） | 520 | 約2時間 |

VPNなしで数百件を一気に投げると自宅IPがBot判定されやすい。
多い場合は `--vpn` を付けるか、週数・空港を分ける。時間をかけてよいなら
`--all --weeks 13 --vpn` で3か月分を一度に取り切ることもできる。

---

# 1日2回の自動通知（GitHub Actions）

## スケジュール

`.github/workflows/daily.yml` に2つの cron を設定してある。

| cron (UTC) | JST | 狙い |
|---|---|---|
| `15 21 * * *` | 06:15 | 7時前に通知 |
| `15 9 * * *`  | 18:15 | 19時前に通知 |

**目標時刻の45分前**に設定している。GitHub Actions の cron は「その時刻以降に実行」で、
混雑時は数十分〜1時間遅れる（公式仕様。毎時0分は特に混むので `:15` にしてある）。

> **「必ず7時までに」は Actions では保証できない。** 確実性が必要なら、
> ローカルPCのタスクスケジューラで実行すること（`docs/運用手順.md` 参照）。

## 各回の内容

- 実行のたびに**その場で検索し直す**（キャッシュなし）
- 対象は**次の2つの週末**（`weekends_ahead: 2`）
- 20空港 × 2週末 × 往復 = **80検索**、待機込みで約15分

## 無料枠の収まり（実測に基づく設計）

| 資源 | 無料枠 | 本設定での消費 |
|---|---|---|
| GitHub Actions（private） | 2,000分/月 | 約15分 × 2回 × 30日 ＝ **約900〜1,000分** |
| LINE Messaging API | 200通/月 | 最大 1通 × 2回 × 30日 ＝ **最大60通** |

LINEを1通に収めるため、通知件数に上限を設けてある:

```json
"notify_top_n_per_route": 1,   // 1路線につき最安1件（20路線あるため）
"notify_max_total": 12         // 全路線通算で12件まで（安い順）
```

**12件で約4,100文字＝LINE1通**（20路線すべてが該当する最悪ケースで実測）。
15件にすると2通に割れる。増やしたい場合はこのトレードオフを承知の上で。

上限で省略した分は本文に「他 N件」と明記される（黙って捨てない）。

## 通知が2回とも同じ内容になる件

重複制御は行わない仕様（要件3.6）。同じ便が朝と夕方の両方で通知されうる。
価格は都度取得しているので、**同じ便でも値段が変わっていれば違う金額で届く**。
「前回と同じなら送らない」は将来拡張の候補（要件7）。

## 動作確認

push 後、Actions タブ → daily-flight-check → **Run workflow**（dry_run OFF）で
即座に1回試せる。スケジュールを待つ必要はない。

---

# 通しテスト（好きな時に検索〜LINE通知を確認）

日次通知は「お得な便がある時だけ」送るので、平常時は通しの確認ができない。
`smoke_test.py` は **お得な便が0件でも必ずLINEに1通送る**通しテスト。
届いた本文に検索結果の要約（各路線の便数・最安値）が入るので、
検索・判定・LINE通知が全てつながっているかを1発で確認できる。

## ローカルで実行

```powershell
# 先頭2路線を実検索してLINE送信（約30秒）
python scripts\smoke_test.py

# 路線を指定
python scripts\smoke_test.py --dest HIJ FUK

# LINEに送らずコンソールだけで確認（実検索はする）
python scripts\smoke_test.py --console

# Google・LINEに一切接続せずチェーンだけ確認（完全オフライン）
python scripts\smoke_test.py --dry-run
```

届くLINEの例:
```
【通しテスト】週末格安便システム
実行 2026-07-29 12:47 / 所要 28秒 / 実検索

検索: 2路線（失敗 0）
  広島: 往路12/復路10便 最安 ￥43,270（相場 ￥35,000）
  松山: 往路9/復路9便 最安 ￥66,570（相場 ￥33,000）

お得な便（ランク入り）: 0件
（相場設定より高いだけ。検索・判定は正常に動いています）

このメッセージが届いていれば、検索→判定→LINE通知まで全て正常です。
```

## GitHub上で実行（好きな時にボタンで）

push 後、**Actions タブ → smoke-test → Run workflow**。

- `routes`: 先頭から何路線を実検索するか（既定2。速いほうがよければ1）
- `dest`: 路線を指定したいとき（例 `HIJ FUK`）
- `dry_run`: Google・LINEに接続せずチェーンだけ確認したいとき ON

数分でLINEに「【通しテスト】…」が届けば、GitHub上でも全チェーンが正常。
**これで日次通知を待たずに、いつでもGitHub経由の疎通を確認できる。**

終了コード: 0=成功 / 2=検索が全滅 / 3=LINE送信失敗
