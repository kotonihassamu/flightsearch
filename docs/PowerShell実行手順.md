# PowerShell 実行手順（Windows）

コピペで動くコマンドだけを並べたもの。上から順に実行する。
`>` で始まる行は入力するコマンド、その下が期待する表示。

**PowerShell の起動**: スタートメニューで「PowerShell」と入力 →「Windows PowerShell」を開く。
管理者権限は不要。

---

## STEP 1. フォルダへ移動する

```powershell
cd "C:\Users\nuram\OneDrive - 元富士製作所\フライト検索システム"
```

パスに空白が入っているので、**ダブルクォートは必須**。

確認:

```powershell
ls
```

`README.md` `config.json` `src` `tests` `docs` などが並んでいればOK。

---

## STEP 2. Python があるか確認する

```powershell
python --version
```

期待: `Python 3.11.x` 以上。

### うまくいかない場合

**Microsoft Store が開いた / `Python was not found`**
→ Python が未インストール。https://www.python.org/downloads/windows/ から入れる。
   インストーラの最初の画面で **「Add python.exe to PATH」に必ずチェック**を入れる。
   インストール後は PowerShell を開き直す。

**`Python 3.10` 以下だった**
→ 同じく python.org から 3.11 以上を入れる。複数入っている場合は以下で確認:

```powershell
py --list
```

3.11以上があれば、以降の `python` をすべて `py -3.11` に読み替える。

---

## STEP 3. 仮想環境をつくる（初回のみ）

システムのPythonを汚さないよう、このフォルダ専用の環境をつくる。

```powershell
python -m venv .venv
```

数秒〜数十秒かかる。何も表示されずプロンプトが戻れば成功。

> **OneDrive について**: `.venv` フォルダは数千ファイルになるので、OneDrive の同期が
> 重くなることがある。気になる場合は、エクスプローラで `.venv` を右クリック →
> 「常にこのデバイス上に保持しない」または同期対象から外す。動作には影響しない。

---

## STEP 4. 仮想環境を有効にする（PowerShellを開くたびに毎回）

```powershell
.\.venv\Scripts\Activate.ps1
```

成功すると、プロンプトの先頭に `(.venv)` が付く:

```
(.venv) PS C:\Users\nuram\OneDrive - 元富士製作所\フライト検索システム>
```

### `このシステムではスクリプトの実行が無効になっているため…` と出たら

PowerShell の既定の制限。**このウィンドウだけ**許可すれば済む:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

`実行ポリシーを変更しますか?` と聞かれたら `Y` を入力してEnter。
そのあと、もう一度:

```powershell
.\.venv\Scripts\Activate.ps1
```

`-Scope Process` なのでこのウィンドウを閉じれば元に戻る。安全。
毎回打つのが面倒なら、次のコマンドで自分のアカウントにだけ恒久設定できる:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

---

## STEP 5. ライブラリを入れる（初回のみ）

`(.venv)` が付いていることを確認してから:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

最後に `Successfully installed ...` と出れば成功。

### エラーが出たら

`fast-flights` が入らなくても、**STEP 7〜14 は全部通る**（外部接続しないため）。
その場合は `requirements.txt` の `fast-flights` の行頭に `#` を付けて保存し、再実行:

```powershell
notepad requirements.txt
pip install -r requirements.txt
```

`UnicodeDecodeError` が出る場合は pip が古い。先に `python -m pip install --upgrade pip`。

---

## STEP 6. 文字化け対策（推奨・毎回）

日本語表示を確実にする。

```powershell
chcp 65001
```

`Active code page: 65001` と出ればOK。

やらなくても異常終了はしないよう作ってあるが、
やっておくと表示が確実にきれいになる。

---

## STEP 7. テストを流す

```powershell
pytest
```

期待:

```
........................................................ [100%]
129 passed, 3 skipped in 2.1s
```

skipped の3件は「実HTMLを使ったパーサ回帰テスト」。STEP 15 でHTMLを採取すると有効になる。

**ここが全部通れば、判定ロジックは正しく動いている。**

失敗したら、失敗したテスト名がそのまま原因の場所を指している。
詳しく見たいとき:

```powershell
pytest -v
pytest tests\test_ranking.py -v
```

---

## STEP 8. パスを通す（PowerShellを開くたびに毎回）

`pytest` には不要だが、`python -m flightdeal...` を直接叩くときに必要。

```powershell
$env:PYTHONPATH = "src"
```

何も表示されない。それで正常。

> STEP 4・6・8 は PowerShell を開き直すたびに必要。
> 面倒なら STEP 14 のショートカットを使う。

---

## STEP 9. ドライラン（一番大事）

外部サイトにもLINEにも接続せず、検索から通知本文まで通す。

```powershell
python -m flightdeal.main --dry-run
```

期待: `{"ts": ...}` のログが8行ほど流れたあと、こう表示される。

```
============================================================
[DRY-RUN] 通知本文
============================================================
週末の格安便が 6件 見つかりました

【S】羽田⇔広島 8/1(土)〜8/2(日)
実質 ￥22,800（片道×2の合算 / 相場 ￥35,000 / ▲35%）
往路 8/1: ANA 07:25発 → 08:50着（片道 ￥11,400 / NH673）
復路 8/2: ANA 19:05発 → 20:30着（片道 ￥11,400 / NH688）
補正: なし（FSC）
往路検索: https://www.google.com/travel/flights?...
復路検索: https://www.google.com/travel/flights?...
...
```

> この数字は **StubFetcher（デモ用のダミーデータ）** のもの。実在の便ではない。
> 実データで動かすのは STEP 15。

### 目で確認すること

- [ ] 往路の**到着**時刻がすべて 11:00 以前
- [ ] 復路の**出発**時刻がすべて 17:00 以降
- [ ] 実質価格 ＝ 往路＋復路＋補正（1件だけ電卓で検算する）
- [ ] Jetstar の便に `手荷物 +￥3,500` が付いている
- [ ] ANA/JAL だけの便は `補正: なし（FSC）`
- [ ] 1路線あたり最大3件
- [ ] 往路検索/復路検索のリンクが**それぞれの日付の片道**を指している

---

## STEP 10. 日付を変えて週末算出を確認する

土曜まで待つ必要はない。`--today` で今日を偽装できる。

```powershell
python -m flightdeal.main --dry-run --today 2026-07-31
```

ログの `"date"` が `2026-08-01`（土）と `2026-08-02`（日）になっていることを確認。

**土曜に実行した場合が要注意。** 当日ではなく翌週になるのが仕様:

```powershell
python -m flightdeal.main --dry-run --today 2026-08-01
```

期待: `"date": "2026-08-08"` と `"2026-08-09"`。

ログが多くて見づらいときは、日付だけ抜き出す:

```powershell
python -m flightdeal.main --dry-run --today 2026-08-01 2>$null | Select-String '"date"'
```

---

## STEP 11. 障害時の動きを確認する

わざと失敗させられる。実際に壊れるのを待たなくてよい。

### 11-1. 1路線だけ失敗 → 他は生き残る

```powershell
python -m flightdeal.main --dry-run --fail-route HND-HIJ
```

期待: 広島が `route_failed` になるが、**松山の結果はそのまま通知される**。

終了コードの確認:

```powershell
$LASTEXITCODE
```

期待: `0`（一部失敗は正常終了）

### 11-2. 全路線失敗 → 障害通知が出る

```powershell
python -m flightdeal.main --dry-run --fail-route HND-HIJ --fail-route HND-MYJ
$LASTEXITCODE
```

期待: `【取得失敗】航空券を取得できませんでした（全路線）` という本文が出て、
終了コードが **2**（GitHub Actions が赤くなる条件）。

ログを見ると同じ区間で `"attempt": 1, 2, 3` と3回試している（初回＋リトライ2回）。

---

## STEP 12. 設定を変えて判定が動くか確認する

```powershell
notepad config.json
```

### 12-1. 相場を下げる

広島（`"iata": "HIJ"`）の `"market_price"` を `35000` → `24000` に変更して保存し:

```powershell
python -m flightdeal.main --dry-run
```

期待: さっき【S】だった広島が **【B】** に落ちる。

### 12-2. 設定ミスは起動時に弾かれる

`"rank_thresholds"` を `{"S": 0.90, "A": 0.85}` に変更して保存し、実行:

```powershell
python -m flightdeal.main --dry-run
$LASTEXITCODE
```

期待: 検索を始める前に止まり、終了コード `2`。

```
設定ファイルに問題があります: rank_thresholds は 0 < S < A < 1 である必要があります (S=0.9, A=0.85)
config.json を確認してください（docs/テスト手順.md T4-4 参照）。
```

**確認が終わったら config.json を必ず元に戻すこと。**
元に戻したかは、これで確かめられる:

```powershell
pytest tests\test_config.py
```

---

## STEP 13. 実装状況を見る

```powershell
python -m flightdeal.main --status
```

期待: `未実装の関数 : 0件`。

---

## STEP 14. 毎回の起動を1コマンドにする（任意）

STEP 1・4・6・8 をまとめたショートカットを作っておくと楽。

```powershell
notepad 起動.ps1
```

メモ帳に以下を貼り付けて保存:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
Set-Location "C:\Users\nuram\OneDrive - 元富士製作所\フライト検索システム"
& ".\.venv\Scripts\Activate.ps1"
chcp 65001 > $null
$env:PYTHONPATH = "src"
Write-Host "準備完了。 python -m flightdeal.main --dry-run で試せます。" -ForegroundColor Green
```

以降は PowerShell を開いてこれだけ:

```powershell
cd "C:\Users\nuram\OneDrive - 元富士製作所\フライト検索システム"
.\起動.ps1
```

---

# ここから先は外部接続を伴う

STEP 13 までは何度実行してもGoogleにもLINEにも接続しない。
以下は実際に通信するので、内容を理解してから進める。

---

## STEP 15. Phase 0 — 実際に価格が取れるか

**完了条件: 3日連続で成功すること。**

```powershell
python scripts\phase0_check.py --dest HIJ --save --save-raw
```

期待: 便のリストが数件表示され、航空会社名・時刻・価格が入っている。
`--save-raw` により生HTMLが `tests\fixtures\raw\` に保存され、
以後 `pytest` でパーサの回帰テストが有効になる（skip が消える）。

確認すること:

| 項目 | OK の基準 |
|---|---|
| 取得件数 | 1件以上 |
| 航空会社名 | ANA / JAL などが入っている |
| 時刻 | 出発・到着とも入っている |
| 価格 | **円**として妥当（1万〜2万円台） |
| stops | `0` の便がある |

結果を `docs\phase0_log.md` に記入する:

```powershell
notepad docs\phase0_log.md
```

**翌日・翌々日も同じコマンドを実行**して、3日分記録する。

### 取れたら実データでドライランする

```powershell
notepad config.json
```

`"fetcher"` が `"fast_flights"`、`"notifier"` が `"console"` であることを確認
（LINEには飛ばない）。

```powershell
python -m flightdeal.main
```

STEP 9 のチェックリストを、今度は実データでもう一度確認する。

**0件通知でも正常です。** ログのこの部分を見る:

```
"route": "HIJ", "cheapest_total": 43270, "market_price": 35000, "notifiable": 0
```

`cheapest_total`（実勢の最安往復）が `market_price`（相場設定）より高ければ、
「今週はお得な便が無い」という**正しい判定**。相場設定を実勢に合わせたい場合は
`docs\運用手順.md` の「相場（market_price）がずれてきたら」を参照。

実際の通知を見てみたいときは、実勢に合わせたデモ設定で:

```powershell
python -m flightdeal.main --config config_demo.json
```

---

## STEP 16. LINE通知の疎通

### 16-1. 準備

1. https://developers.line.biz/ でログイン
2. Messaging API チャネルを作成
3. チャネルアクセストークン（長期）を発行
4. そのチャネルを自分のLINEで**友だち追加**（これを忘れると届かない）
5. 自分の userId（`U` で始まる文字列）を控える

```powershell
copy .env.example .env
notepad .env
```

2行に値を書いて保存:

```
LINE_CHANNEL_ACCESS_TOKEN=（発行したトークン）
LINE_TO_USER_ID=U（自分のID）
```

### 16-2. まず疎通だけ確認する

**いきなり本番実行しない。** テストメッセージだけ送る口がある。

```powershell
notepad config.json
```

`"notifier"` を `"console"` → `"line"` に変更して保存。

```powershell
python -m flightdeal.main --test-notify
```

期待: LINEに「【テスト送信】…」が届き、画面に
`line への送信に成功しました。` と表示される。

| 表示 | 原因 |
|---|---|
| `環境変数が未設定です` | `.env` が読まれていない → STEP 16-3 |
| `status=401` | トークンが誤り／失効 |
| `status=400` | userId が誤り |
| 成功と出るが届かない | 友だち追加していない |

### 16-3. `.env` が読まれない場合

環境変数を直接指定する:

```powershell
$env:LINE_CHANNEL_ACCESS_TOKEN = "（トークン）"
$env:LINE_TO_USER_ID = "U（自分のID）"
python -m flightdeal.main --test-notify
```

これで届くなら `.env` の書式（余計な空白・引用符）を見直す。

### 16-4. 本番相当で1回流す

```powershell
python -m flightdeal.main
```

**該当便が0件だと何も届かないのが正常。**
そのときはログに `run_no_deal` が出ているはず:

```powershell
python -m flightdeal.main 2>$null | Select-String "run_no_deal"
```

---

## よく使うコマンド早見表

PowerShell を開いたら、まず:

```powershell
cd "C:\Users\nuram\OneDrive - 元富士製作所\フライト検索システム"
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "src"
```

| やりたいこと | コマンド |
|---|---|
| テスト | `pytest` |
| ロジック確認 | `python -m flightdeal.main --dry-run` |
| 週末算出の確認 | `python -m flightdeal.main --dry-run --today 2026-08-01` |
| 障害時の動き | `python -m flightdeal.main --dry-run --fail-route HND-HIJ` |
| 通知の疎通だけ | `python -m flightdeal.main --test-notify` |
| 実装状況 | `python -m flightdeal.main --status` |
| 詳細ログ | 上に `--verbose` を足す |
| 終了コード確認 | `$LASTEXITCODE` |
| ログを絞る | `... 2>$null \| Select-String "route_done"` |
| 仮想環境を抜ける | `deactivate` |

`--dry-run` が付いている限り、Google にも LINE にも接続しない。
