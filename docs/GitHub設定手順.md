# GitHub Actions 設定手順（Phase 2 の残り）

毎朝8時に自動実行させるための手順。**リポジトリは必ず private にすること。**

前提: LINE通知の疎通確認（`--test-notify`）が済んでいること。

---

## STEP 1. git があるか確認

```powershell
git --version
```

`git version 2.x.x` と出ればOK。

**出ない場合**: https://git-scm.com/download/win からインストール。
インストーラは既定のままでよい。終わったら PowerShell を開き直す。

初回のみ、名前とメールを設定（GitHubのものでなくてもよい）:

```powershell
git config --global user.name "nuram"
git config --global user.email "nuramago2000@gmail.com"
```

---

## STEP 2. GitHub にリポジトリを作る

1. https://github.com/new を開く
2. **Repository name**: `flight-deal-notifier`（好きな名前でよい）
3. **Private** を選択 ← **必ず private**
4. README / .gitignore / license は**追加しない**（既にあるため）
5. 「Create repository」

次の画面に出る URL を控える:

```
https://github.com/<あなたのユーザー名>/flight-deal-notifier.git
```

> **なぜ private か**: 非公式な手段でGoogleからデータを取得しているため（要件R1）。
> また取得した生HTMLも含まれる。公開する性質のものではない。

---

## STEP 3. ローカルをリポジトリにする

```powershell
cd "C:\Users\nuram\OneDrive - 元富士製作所\フライト検索システム"
git init -b main
git add .
```

### push 前チェック（重要）

```powershell
python scripts\pre_push_check.py
```

期待:

```
[OK] 秘匿ファイル(.env)
[OK] トークン混入
[OK] config.json
[OK] ファイルサイズ
問題なし。push して大丈夫です。
```

**`[NG]` が出たら push しないこと。** 特に `.env` が管理対象に入っていた場合、
一度 push すると履歴に残り、LINEトークンの再発行が必要になる。

念のため目視でも確認:

```powershell
git status
```

`.env` が一覧に**出ていないこと**を確認する（`.gitignore` 済みなので通常は出ない）。

### コミット

```powershell
git commit -m "週末格安航空券 自動通知システム"
```

---

## STEP 4. push する

```powershell
git remote add origin https://github.com/<あなたのユーザー名>/flight-deal-notifier.git
git push -u origin main
```

初回はブラウザが開いて GitHub のログインを求められる（Git Credential Manager）。
ログインすれば以降は聞かれない。

> `_to_delete` フォルダも一緒に push されるのが気になる場合は、
> 先に中身を削除してから `git add .` すること。

---

## STEP 5. Secrets を登録する

GitHubのリポジトリページで:

**Settings** → 左メニュー **Secrets and variables** → **Actions** → **New repository secret**

2つ登録する（`.env` に書いたのと同じ値）:

| Name | Secret |
|---|---|
| `LINE_CHANNEL_ACCESS_TOKEN` | チャネルアクセストークン（長期） |
| `LINE_TO_USER_ID` | あなたのユーザーID（Uで始まる） |

**名前は完全一致させること。** 大文字小文字も含めて。

---

## STEP 6. まずドライランで試す

いきなり本番実行しない。外部接続なしで環境だけ検証する。

1. リポジトリの **Actions** タブを開く
2. 左メニューの **daily-flight-check** をクリック
3. 右上の **Run workflow** をクリック
4. **dry_run** のチェックを **ON** にする
5. 緑の **Run workflow** ボタン

期待: 数分で緑のチェックが付く。

ログの確認方法: 実行をクリック → `run` ジョブ → 各ステップを展開。

- **Unit tests** ステップ: テストが全通過している
- **Run** ステップ: `[DRY-RUN] 通知本文` が出ている（LINEには飛ばない）

**赤くなったら**: どのステップで落ちたかを見る。
`Install dependencies` で落ちたなら依存の問題、`Unit tests` ならテストの問題。

---

## STEP 7. 本番実行を試す

同じく **Run workflow**。今度は **dry_run のチェックを OFF**（既定）。

期待:
- 緑になる
- **該当便があればLINEに通知が届く。0件なら何も届かない**（これが正常）

ログの `Run` ステップで確認する:

| ログ | 意味 |
|---|---|
| `run_no_deal` | 該当便0件。正常 |
| `run_done` + `notified: N` | N件をLINEに送信した |
| `run_all_failed` | 全路線で取得失敗 → 下記「もし失敗したら」 |

---

## STEP 8. 自動実行を見守る（3日連続で成功が完了条件）

以降は毎日 JST 8:00 頃に自動実行される（`cron: "0 23 * * *"` = UTC 23:00）。

> **GitHub Actions の cron は数十分〜1時間遅れることがある**（公式仕様）。
> 8:00ちょうどに来なくても異常ではない。

Actions タブで3日連続グリーンになれば **Phase 2 完了**。

---

## もし失敗したら

### `run_all_failed` / 全路線で取得失敗

**要件で想定されているリスク（R2）です。** GitHub Actions のIPはデータセンターIPのため、
Googleに Bot と判定されてブロックされる可能性がある。

**判断基準（要件4.1）: 全路線失敗が3日連続したら、ローカル実行へ切り替える。**

1日や2日の失敗なら様子を見る。3日続いたら `docs/運用手順.md` の
「取得失敗が続く場合」に従って、自宅PCのタスクスケジューラでの実行に移行する。

切り分けには、まず手元で同じことを試す:

```powershell
python scripts\phase0_check.py --dest HIJ
```

- **手元では成功するのに Actions で失敗** → IPブロックの可能性が高い。ローカルへ移行
- **手元でも失敗** → Google側かライブラリ側の問題。`pytest tests\test_parser_regression.py` で切り分け

### 失敗時の証拠を見る

解析に失敗した場合、そのときの生HTMLが**アーティファクトとして7日間保存される**。

Actions の実行ページ → 下部の **Artifacts** → `debug-<番号>` をダウンロード。
中身のHTMLを見れば、Bot判定ページが返ってきているのか、構造が変わったのかが分かる。

### スケジュールを止めたいとき

`.github/workflows/daily.yml` の `schedule:` の2行をコメントアウトして push。

```yaml
on:
  # schedule:
  #   - cron: "0 23 * * *"
  workflow_dispatch:
```

`workflow_dispatch` は残しておくと、手動実行での疎通確認に使える。

---

## 以後、設定を変えたら push する

`config.json` を変更したら、Actions にも反映するため push が必要:

```powershell
git add config.json
git commit -m "相場を実勢に合わせて調整"
git push
```

Phase 3（全5路線・第2週末）への拡張も、`config.json` を変えて push するだけ
（コード変更不要）。ただし `notify_top_n_per_route` を 2 に下げること
（`docs/運用手順.md` 参照）。
