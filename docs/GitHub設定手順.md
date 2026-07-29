# GitHub Actions 設定手順（Phase 2 の残り）

毎朝8時に自動実行させるための手順。**リポジトリは必ず private にすること。**

前提: LINE通知の疎通確認（`--test-notify`）が済んでいること。

---

## STEP 1. git の準備

```powershell
git --version
```

`git version 2.x.x` と出ればOK。

**出ない場合**: https://git-scm.com/download/win からインストール。
インストーラは既定のままでよい。終わったら PowerShell を開き直す。

### 初回のみ: 身元と文字コードの設定（**必須。これを飛ばすとコミットできない**）

```powershell
git config --global user.name "nuram"
git config --global user.email "nuramago2000@gmail.com"
git config --global i18n.commitEncoding utf-8
git config --global core.quotepath false
```

設定せずに `git commit` すると `Author identity unknown` で失敗し、
コミットが1つも無い状態になる。すると後続の push も
`src refspec main does not match any` で失敗する（原因は最初のエラー）。

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

LINEのトークンをリポジトリに置くわけにはいかないので、GitHub の金庫（Secrets）に入れる。
Actions 実行時だけ環境変数として渡され、ログにも表示されない。

### 5-1. 登録する値を手元に用意する

`.env` に書いたのと**まったく同じ値**を使う。

```powershell
notepad .env
```

`=` の**右側だけ**をコピーする。引用符・前後の空白・改行は含めない。

```
LINE_CHANNEL_ACCESS_TOKEN=ここから右をコピー
LINE_TO_USER_ID=ここから右をコピー
```

### 5-2. Secrets の画面を開く

1. ブラウザで自分のリポジトリを開く
   （例: `https://github.com/kotonihassamu/flightsearch`）
2. リポジトリ上部のタブから **Settings** をクリック
   （`Code / Issues / Pull requests / Actions / Projects / Security / Insights / Settings`
   の一番右。見えない場合はウィンドウを広げるか `...` の中）
3. **左サイドバー**を下にスクロールし、**Security** のグループにある
   **Secrets and variables** をクリック
4. 展開されたら **Actions** をクリック

URLを直接開いてもよい:

```
https://github.com/<ユーザー名>/<リポジトリ名>/settings/secrets/actions
```

### 5-3. 1つ目を登録する

1. 緑の **New repository secret** ボタンをクリック
2. **Name** に以下を**大文字・アンダースコアまで正確に**入力

   ```
   LINE_CHANNEL_ACCESS_TOKEN
   ```

3. **Secret** の欄にトークンを貼り付け
4. **Add secret** をクリック

### 5-4. 2つ目を登録する

同じく **New repository secret** から:

- **Name**: `LINE_TO_USER_ID`
- **Secret**: `U` で始まる33文字のユーザーID
- **Add secret**

### 5-5. 登録できたか確認する

**Repository secrets** の一覧に2つ並んでいればOK。

```
LINE_CHANNEL_ACCESS_TOKEN    Updated now
LINE_TO_USER_ID              Updated now
```

> 値は二度と表示できない（GitHubの仕様）。間違えた場合は
> 右の **Update** から入れ直す。削除して作り直す必要はない。

### よくある間違い

| 間違い | どうなるか |
|---|---|
| **Environments** に登録した | ワークフローから見えない。Repository secrets に登録すること |
| **Codespaces** タブに登録した | 同上。**Actions** タブであること |
| 名前が小文字・ハイフン | 名前は完全一致。`LINE_TO_USER_ID` であって `line-to-user-id` ではない |
| 値の前後に空白や改行が入った | 401/400 エラーになる。貼り直す |
| `.env` ではなくチャネルシークレットを入れた | 401。必要なのは**チャネルアクセストークン（長期）** |

### 登録漏れは実行時に検出される

ワークフローに **Check secrets** ステップがあり、検索を始める前に確認する。
未登録なら即座に赤くなり、こう表示される:

```
NG: 未登録の Secrets: LINE_TO_USER_ID
登録場所: リポジトリの Settings > Secrets and variables > Actions
```

登録済みなら値は伏せたまま、桁数だけ表示される（診断用）:

```
OK: Secrets を確認しました（値は表示しません）
  token  : 172 文字
  userId : 33 文字 / 先頭 'U'
```

`userId` が33文字でない、または `U` で始まっていない場合は値が違う。

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

終了コードの意味:

| コード | 意味 |
|---|---|
| 0 | 正常（通知した or 該当0件） |
| 2 | 全路線で取得失敗（障害通知は送れた） |
| 3 | 通知の送信に失敗（Secrets未登録など） |

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


---

## よくあるエラーと対処

### `Author identity unknown` / `unable to auto-detect email address`

STEP 1 の身元設定を飛ばしている。設定してから `git commit` をやり直す。

```powershell
git config --global user.name "nuram"
git config --global user.email "nuramago2000@gmail.com"
```

### `error: remote origin already exists`

すでに `origin` を登録済み（プレースホルダのまま登録してしまった等）。
追加ではなく**上書き**する。

```powershell
git remote set-url origin https://github.com/<ユーザー名>/<リポジトリ名>.git
git remote -v
```

`git remote -v` で正しいURLが2行出ることを確認する。

### `error: src refspec main does not match any`

**コミットが1つも無い**ときに出る。多くは上の `Author identity unknown` が原因。
身元を設定 → `git add .` → `git commit` の順にやり直す。

ブランチ名が `master` になっている場合は:

```powershell
git branch -M main
```

### `! [rejected]` / `fetch first`

GitHub側でREADMEやライセンスを作ってしまい、履歴が食い違っている。
リポジトリ作成時は何も追加しないのが正しいが、作ってしまった場合:

```powershell
git pull --rebase origin main
git push -u origin main
```

### `Node.js 20 is deprecated` という警告が出る（実行は緑）

**エラーではない。** GitHub のランナー側の予告。
本リポジトリのワークフローは Node 24 対応版
（`checkout@v6` / `setup-python@v6`）を使っているため、この警告は出ないはず。
出る場合は古い workflow が動いている可能性があるので、push できているか確認する。

### `ModuleNotFoundError: No module named 'typing_extensions'`

fast-flights 3.0.2 は `typing_extensions` を使うのに、**依存として宣言していない**
（ライブラリ側の不備）。ローカルでは pytest が間接的に入れるため気づきにくく、
クリーンインストール（CI）で初めて露呈する。

`requirements.txt` に `typing-extensions>=4.6.0` を明示済み。
出る場合は requirements.txt が push されているか確認する。

### `fast-flights を読み込めません` / `期待するAPIがありません`

依存は入っているが**版が違う**可能性が高い。`requirements.txt` は
`fast-flights==3.0.2` に固定してある。バージョン指定なしにすると、環境によっては
古い 2.x（API が全く違う）が入ってしまう。

ワークフローの **Verify fast-flights API** ステップが実行前に検出する。
このステップで落ちた場合はログの `path:` と `pip list` の出力を確認する。

### `NotifyError: 環境変数が未設定です` / 終了コード 3

**Secrets が未登録**（STEP 5 を飛ばしている）。
Settings → Secrets and variables → **Actions** に、名前を完全一致で登録する:

- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_TO_USER_ID`

> よくある間違い: 「Environments」や「Codespaces」の Secrets に登録している。
> **Actions** タブの Repository secrets に登録すること。

登録後は Run workflow をやり直す。なお通知に失敗しても、送れなかった本文は
ログに出力されるので内容は追える。

### `Authentication failed`

初回 push はブラウザで GitHub にログインする必要がある。
ブラウザが開かない場合は Git Credential Manager が入っているか確認する
（Git for Windows の既定で入っている）。
