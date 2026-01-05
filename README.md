# YouTube Bulk Uploader (youtube-bulkup)

大量の動画ファイルをYouTubeへ効率的に一括アップロードするためのPython製CLIツールです。
コンテンツクリエイターや企業の運用負荷を軽減するために設計されています。

## 主な機能

- **🚀 一括アップロード**: ディレクトリ内の動画を自動検出し、並行してアップロードします。
- **📺 プレイリスト対応**: アップロード時にプレイリスト名を指定可能。指定がない場合はディレクトリ名から自動的にプレイリストを作成・追加します。
- **🔄 重複検知**: ファイルハッシュを確認し、既にアップロード済みの動画は自動的にスキップします。
- **📂 自動メタデータ設定**: フォルダ名とファイル情報からタイトル・説明・タグを自動生成します。また、ビデオファイル自身のメタデータ（撮影日時など）を抽出し、YouTubeに反映します。
- **🛡️ 堅牢な再開機能**: ネットワーク切断時の一時停止・再開（レジューム）や、指数バックオフによるリトライ処理を完備。
- **📊 リッチな進捗表示**: アップロード状況をリアルタイムに美しく表示します。

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
   `venv`（仮想環境）の利用を推奨します。
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   # pipをアップグレード（重要：ビルドツール対応のため）
   pip install --upgrade pip
   pip install -e .
   ```

3. **認証情報の配置**
   GCPコンソールからダウンロードした `client_secrets.json` をプロジェクトのルートディレクトリに配置してください。

## 設定

`settings.yaml` で挙動をカスタマイズできます。

```yaml
auth:
  # 認証ファイルのパス
  client_secrets_file: "client_secrets.json"
  token_file: "token.pickle"

upload:
  chunk_size: 4194304  # 4MB (ネットワーク環境に応じて調整)
  retry_count: 5       # 失敗時の最大リトライ回数
  privacy_status: "private" # private, public, unlisted


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

### 5. リトライ (Retry)
過去にアップロードに失敗したファイルを抽出し、再試行します。

```bash
yt-up retry
```

- **プレイリストの自動復元**: アップロード失敗時に、追加予定だったプレイリスト名が履歴に保存されています。`retry` コマンドは自動的にそのプレイリストへ追加を試みます。
  - 履歴にプレイリスト情報がない場合（古いバージョンの履歴など）、**フォルダ名** がデフォルトとして使用されます。
- `--playlist / -p`: 履歴に保存されたプレイリスト名を無視し、指定したプレイリストへ強制的に追加したい場合に使用します。

## Quota (API割り当て) について

YouTube Data API には1日あたりの使用制限（Quota）があります。デフォルトは **10,000 ユニット/日** です。
動画1本のアップロードに約 1,600 ユニット消費するため、デフォルトでは1日6本程度しかアップロードできません。

大量の動画をアップロードする場合は、この上限を引き上げる申請が必要です。
詳しい手順については [docs/QUOTA_INCREASE.md](docs/QUOTA_INCREASE.md) を参照してください。

## ライセンス
MIT License
```
