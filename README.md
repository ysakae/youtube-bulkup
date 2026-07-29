# YouTube Bulk Uploader (youtube-bulkup)

大量の動画ファイルをYouTubeへ効率的に一括アップロードするためのPython製CLIツールです。
コンテンツクリエイターや企業の運用負荷を軽減するために設計されています。

## 主な機能

- **🚀 一括アップロード**: ディレクトリ内の動画を自動検出し、並行してアップロードします。
- **📺 プレイリスト対応**: アップロード時にプレイリスト名を指定可能。指定がない場合はディレクトリ名から自動的にプレイリストを作成・追加します。
- **🔄 重複検知**: ファイルハッシュを確認し、既にアップロード済みの動画は自動的にスキップします。
- **📂 自動メタデータ設定**: テンプレートとファイル情報からタイトル・説明・タグを自動生成します。フォルダ別に `.yt-meta.yaml` でカスタマイズも可能。
- **🛡️ 堅牢な再開機能**: ネットワーク切断時の一時停止・再開（レジューム）や、指数バックオフによるリトライ処理を完備。
- **📊 リッチな進捗表示**: アップロード状況をリアルタイムに美しく表示します。
- **📋 Quota自動制御**: YouTube APIの日次クォータ残量を自動チェックし、超過前に警告します。

## 前提条件

- **Python 3.10+**
- **Google Cloud Platform (GCP) プロジェクト**
    - YouTube Data API v3 の有効化
    - OAuth 2.0 クライアントIDの作成 (`client_secrets.json` の取得)

## Google API セットアップ手順

このツールを使用するには、Google Cloud プロジェクトで YouTube Data API を有効にし、認証情報を取得する必要があります。

1. **プロジェクトの作成/選択**
   - [Google Cloud Console](https://console.cloud.google.com/) にアクセスし、プロジェクトを作成または選択します。
2. **YouTube Data API v3 の有効化**
   - 「APIとサービス」 > 「ライブラリ」から **YouTube Data API v3** を検索し、「有効にする」をクリックします。
3. **OAuth 同意画面の設定**
   - 「APIとサービス」 > 「OAuth 同意画面」で、User Type を「外部」として設定します。
   - アプリ名等の必須項目を入力し、スコープに `.../auth/youtube.upload` を追加します。
   - **重要**: 「テストユーザー」に自分の Google アカウントのメールアドレスを追加してください。
4. **認証情報の作成**
   - 「APIとサービス」 > 「認証情報」 > 「認証情報を作成」 > 「OAuth クライアント ID」を選択します。
   - アプリケーションの種類で **「デスクトップ アプリ」** を選択し、名前を入力して作成します。
5. **JSON ファイルのダウンロード**
   - 作成したクライアント ID の右側にあるダウンロードボタン（⬇️）から JSON ファイルを取得します。
   - ファイル名を `client_secrets.json` に変更して、プロジェクトのルートディレクトリに配置します。

## インストール

1. **リポジトリのクローン**
   ```bash
   git clone https://github.com/ysakae/youtube-bulkup.git
   cd youtube-bulkup
   ```

2. **セットアップ**
   `uv` (高速なPythonパッケージマネージャー) の利用を推奨します。
   ```bash
   # uvが未インストールの場合はインストール
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # 依存関係のインストールと環境構築
   uv sync
   ```

3. **認証情報の配置**
   GCPコンソールからダウンロードした `client_secrets.json` をプロジェクトのルートディレクトリに配置してください。

## 設定

`settings.yaml` で挙動をカスタマイズできます。

```yaml
auth:
  client_secrets_file: "client_secrets.json"
  token_file: "token.pickle"

upload:
  chunk_size: 4194304  # 4MB (ネットワーク環境に応じて調整)
  retry_count: 5       # 失敗時の最大リトライ回数
  privacy_status: "private" # private, public, unlisted
  daily_quota_limit: 10000  # YouTube API 日次クォータ上限 (ユニット)

# クォータ設定
quota:
  daily_limit: 10000   # YouTube Data API 日次クォータ上限 (ユニット)
  reserve: 1000        # 予備として残すユニット

# YouTube 側の状態のローカルキャッシュ
cache:
  enabled: true
  ttl_hours: 24
  path: "youtube_cache.db"

# 履歴DB (SQLite)
history_db: "upload_history.db"

# メタデータテンプレート
# 利用可能な変数: {folder}, {stem}, {filename}, {date}, {year}, {index}, {total}
metadata:
  title_template: "【{folder}】{stem}"
  description_template: |
    {folder}
    No. {index}/{total}

    File: {filename}
    Captured: {date}
  tags:
    - "auto-upload"
```

### クォータとキャッシュの設定

#### `quota.daily_limit`

YouTube Data API の日次クォータ上限（ユニット）です。

> **重要:** GCP でクォータの引き上げ申請をしている場合は、**必ず実際の上限値に設定してください。** 既定の `10000` のままだと、大量アップロード後に `playlist orphans --fix` / `playlist dedupe --fix` が動作しなくなります。
>
> 動画のアップロードは1本あたり 1,600 ユニットを消費するため、既定値のままだと **7本アップロードした時点でその日の残量が 0 と見積もられ**、`--fix` 系コマンドが「本日の推定残量では1件も処理できません」と表示して何もしなくなります。毎日アップロードしている場合、これは恒久的に壊れているように見えます。

クォータの設定箇所は `quota.daily_limit` と `upload.daily_quota_limit` の2つがありますが、**大きい方が採用されます。** どちらを引き上げても効くため、「上げたのに反映されない」ということはありません。新しく設定するなら `quota.daily_limit` を使ってください。

#### `quota.reserve`

予備として書き込み操作の予算から除いておくユニット数です（既定: `1000`）。

`orphans` / `dedupe` は判定のために毎回全走査を行い、動画一覧・全プレイリストの中身・プレイリスト一覧の取得で**1回あたり約 1,000 ユニット**を消費します（動画 10,000 本 / プレイリスト 550 個規模の場合）。この読み取り分を差し引いておくための値なので、下げすぎるとクォータを超過します。

#### `cache.*`

YouTube 側の状態（プレイリスト一覧・各プレイリストの中身・動画一覧）をローカルの SQLite に保存し、API 呼び出しを減らします。

| キー | 既定値 | 説明 |
|------|--------|------|
| `cache.enabled` | `true` | `false` にするとキャッシュを使わず毎回APIから取得します（クォータ消費が大幅に増えます） |
| `cache.ttl_hours` | `24` | キャッシュの有効期限（時間）。期限内は再取得しません |
| `cache.path` | `youtube_cache.db` | キャッシュDBのパス。履歴DB (`upload_history.db`) とは別ファイルで、いつ削除しても再取得できます |

`orphans --offline` はこのキャッシュだけで判定するため、クォータを使い切った状態でも調査できます。

フォルダに `.yt-meta.yaml` を配置すると、そのフォルダの動画だけテンプレートをオーバーライドできます。

```yaml
# .yt-meta.yaml の例
title_template: "{stem} @ {folder}"
extra_tags: ["vacation", "summer"]
```

## 使い方

### 1. 認証 (Authentication)
YouTubeアカウントとの連携・管理を行います。
```bash
yt-up auth login    # ログイン (新規プロファイル作成)
yt-up auth status   # 現在の認証状態を確認
yt-up auth list     # 保存されているプロファイル一覧
yt-up auth switch [NAME] # プロファイルの切り替え
yt-up auth logout   # ログアウト (トークン削除)
```

### 2. ドライラン (動作確認)
実際のアップロードを行わずに、対象ファイルや生成されるメタデータを確認します。
```bash
yt-up upload ./my_videos --dry-run
```

### 3. 一括アップロード実行
```bash
yt-up upload ./my_videos --workers 2 --playlist "My Vacation 2023"
```
- `--workers`: 並行アップロード数（YouTube APIのクォータにご注意ください）。
- `--playlist / -p`: 動画を追加するプレイリスト名を指定します。このオプションを省略した場合、**動画が格納されているディレクトリ名** がプレイリスト名として使用されます（自動作成）。

### 4. 再アップロード (Re-upload)
アップロードに失敗したファイルや、特定のファイルを再アップロードします。
履歴をクリアして強制的にアップロードを試みます。

```bash
# ファイルパス指定
yt-up reupload ./my_videos/video.mp4

# ファイルハッシュ指定（元ファイルが移動していても履歴から特定可能）
yt-up reupload --hash <FILE_HASH>

# 動画ID指定（YouTube Video IDから履歴を検索）
yt-up reupload --video-id <VIDEO_ID>

# ドライラン（履歴削除を行わずにシミュレーション）
yt-up reupload ./my_videos/video.mp4 --dry-run
```

- `--playlist / -p`: 再アップロード時にプレイリストを指定（または上書き）できます。

### 5. プレイリスト管理 (Playlist Management)
プレイリストの操作やメンテナンスを行います。

#### プレイリスト一覧
```bash
yt-up playlist list              # 全プレイリスト一覧
yt-up playlist list "Playlist"   # 特定プレイリスト内の動画一覧
```

#### プレイリスト名変更
```bash
yt-up playlist rename "Old Name" "New Name"
```

#### 未分類動画（Orphan Videos）の整理
どのプレイリストにも属していない動画（Orphan Videos）を一括検索し、履歴に基づいて自動的にプレイリストへ割り当てます。

```bash
# 孤立動画（どのプレイリストにも入っていない動画）を検出
yt-up playlist orphans
yt-up playlist orphans --offline             # キャッシュのみで判定 (0 units)
yt-up playlist orphans --fix --max-items 50  # 50件だけ割り当てる
```

- `--offline`: APIを一切叩かず、キャッシュのみで判定します（0 units）。`--fix` とは併用できません。
- `--max-items`: 1回の実行で処理する最大件数を指定します（既定: 本日の残り予算から自動算出）。
- `--refresh`: キャッシュを無視してAPIから取得し直します。

`--fix` で割り当てに成功した動画はキャッシュと履歴（`playlist_synced`）の両方に即座に記録されるため、同じコマンドを再実行すると残りから再開します。すでに追加済みと記録されている動画は再処理されません。

> **注意:** クォータの残量が足りず「本日の推定残量では1件も処理できません」と表示される場合、`settings.yaml` の `quota.daily_limit` が実際の GCP 上限より小さい可能性があります。下の[クォータ設定](#クォータとキャッシュの設定)を確認してください。

#### 重複プレイリストの統合
プレイリスト一覧のページネーション不備により過去に生成された、同名の重複プレイリストを検出・統合します。

```bash
# 同名の重複プレイリストを検出・統合
yt-up playlist dedupe                        # 検出のみ (約 11 units)
yt-up playlist dedupe --fix --max-items 50
```

`--fix` を付けると、各重複グループの最古のプレイリストを「正」として動画を集約し、空になった重複プレイリストを削除します。

検出のみ（`--fix` なし）でも、プレイリスト一覧の取得に `playlists.list` が必要なため 0 units にはなりません（1ページ50件なので、プレイリストが544個なら約 11 units）。

- `--max-items`: 1回の実行で移動する最大動画数を指定します（既定: 50。ただし本日の残り予算を超えては実行されません。プレイリストの削除も予算を消費するため、打ち切り判定に含まれます）。
- `-y / --yes`: 確認プロンプトを省略します。

移動に失敗した動画（削除済み・非公開の可能性があるもの）は実行の最後にまとめて報告されます。該当動画を含むグループは、再実行しても同じ失敗を繰り返してクォータだけ消費するため、YouTube 上で状態を確認してください。

### 6. リトライ (Retry)
過去にアップロードに失敗したファイルを抽出し、再試行します。

```bash
yt-up retry

# フィルター付きリトライ
yt-up retry --limit 5                  # 最大5件まで
yt-up retry --since "2026-01-01"       # 指定日以降の失敗のみ
yt-up retry --error quota              # エラーメッセージでフィルタ
```

- **プレイリストの自動復元**: アップロード失敗時に、追加予定だったプレイリスト名が履歴に保存されています。`retry` コマンドは自動的にそのプレイリストへ追加を試みます。
- `--playlist / -p`: 履歴に保存されたプレイリスト名を無視し、指定したプレイリストへ強制的に追加したい場合に使用します。

### 7. 動画管理 (Video Management)
アップロード済み動画の一覧表示や設定変更を行います。

```bash
# 動画一覧
yt-up video list                       # 全動画一覧
yt-up video list --status private      # 公開状態でフィルタ

# 公開設定変更
yt-up video update-privacy <VIDEO_ID> public
yt-up video update-privacy all unlisted --playlist "MyPlaylist"

# メタデータ更新
yt-up video update-meta <VIDEO_ID> --title "New Title"

# サムネイル更新
yt-up video update-thumbnail <VIDEO_ID> ./thumb.jpg

# 動画削除
yt-up video delete-video <VIDEO_ID> -y
```

### 8. 履歴管理 (History)
アップロード履歴の確認・エクスポート・インポートを行います。

```bash
# 履歴一覧
yt-up history                          # 全件表示
yt-up history --status success         # 成功のみ
yt-up history --limit 10              # 最新10件

# 履歴削除
yt-up history delete --path ./video.mp4
yt-up history delete --hash <FILE_HASH>

# エクスポート / インポート
yt-up history export --output backup.json
yt-up history export --format csv --output backup.csv
yt-up history import backup.json
```

### 9. 同期チェック (Sync)
ローカル履歴とYouTube上の動画を比較し、差分を表示します。

```bash
yt-up sync                             # 差分レポート
yt-up sync --fix                       # ローカル専用レコードを自動削除
yt-up sync --fix -y                    # 確認なしで実行
```

### 10. Quota 確認 (Quota)
YouTube APIの本日のクォータ使用状況を確認します。

```bash
yt-up quota
```

## Quota (API割り当て) について

YouTube Data API には1日あたりの使用制限（Quota）があります。デフォルトは **10,000 ユニット/日** です。
動画1本のアップロードに約 1,600 ユニット消費するため、デフォルトでは1日6本程度しかアップロードできません。

大量の動画をアップロードする場合は、この上限を引き上げる申請が必要です。
詳しい手順については [docs/QUOTA_INCREASE.md](docs/QUOTA_INCREASE.md) を参照してください。

各操作の消費ユニット:

| 操作 | units |
|---|---|
| 動画のアップロード (`videos.insert`) | 1,600 |
| プレイリストへの追加 (`playlistItems.insert`) | 50 |
| プレイリストの作成・削除 | 50 |
| 一覧の取得 (`*.list`、1ページ50件) | 1 |

`playlist orphans --fix` は1本あたり 50 units、`playlist dedupe --fix` は
動画1本の移動あたり 100 units（`playlistItems.insert` + `playlistItems.delete`）
を消費します。`--max-items` で1回の処理件数を制限でき、クォータを使い切った
場合は自動的に中断して残件数を報告します。翌日に同じコマンドを再実行すると
残りから再開します。

## ライセンス
MIT License
