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
