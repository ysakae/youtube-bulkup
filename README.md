# YouTube Bulk Uploader (youtube-up-agy)

大量の動画ファイルをYouTubeへ効率的に一括アップロードするためのPython製CLIツールです。
コンテンツクリエイターや企業の運用負荷を軽減するために設計されています。

## 主な機能

- **🚀 一括アップロード**: ディレクトリ内の動画を自動検出し、並行してアップロードします。
- **🔄 重複検知**: ファイルハッシュを確認し、既にアップロード済みの動画は自動的にスキップします。
- **🤖 AIメタデータ生成 (Optional)**: Gemini APIを利用して、ファイル名から最適なタイトル・説明・タグを自動生成します。
- **🛡️ 堅牢な再開機能**: ネットワーク切断時の一時停止・再開（レジューム）や、指数バックオフによるリトライ処理を完備。
- **📊 リッチな進捗表示**: アップロード状況をリアルタイムに美しく表示します。

## 前提条件

- **Python 3.10+**
- **Google Cloud Platform (GCP) プロジェクト**
    - YouTube Data API v3 の有効化
    - OAuth 2.0 クライアントIDの作成 (`client_secrets.json` の取得)

## インストール

1. **リポジトリのクローン**
   ```bash
   git clone https://github.com/ysakae/youtube-up-agy.git
   cd youtube-up-agy
   ```

2. **セットアップ**
   `venv`（仮想環境）の利用を推奨します。
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
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

ai:
  enabled: false       # AI機能を有効にする場合は true
  model: "gemini-pro"
```

### AI機能の有効化
AIによるメタデータ生成を利用する場合は、`settings.yaml` で `ai.enabled: true` に設定し、環境変数にAPIキーをセットしてください。

```bash
export GEMINI_API_KEY="your_api_key_here"
```

## 使い方

### 1. 認証 (初回のみ)
YouTubeアカウントとの連携を行います。
```bash
yt-up auth
# または
python -m src.main auth
```

### 2. ドライラン (動作確認)
実際のアップロードを行わずに、対象ファイルや生成されるメタデータを確認します。
```bash
yt-up upload ./my_videos --dry-run
```

### 3. 一括アップロード実行
```bash
yt-up upload ./my_videos --workers 2
```
- `--workers`: 並行アップロード数（YouTube APIのクォータにご注意ください）。

## クォータについて
YouTube Data APIのデフォルトクォータは1日あたり10,000ユニットです。
動画1本のアップロードには約1,600ユニット消費するため、1日あたり約6本が上限となります。
大量にアップロードする場合は、GCPコンソールからクォータの引き上げ申請を行ってください。

## ライセンス
MIT License
