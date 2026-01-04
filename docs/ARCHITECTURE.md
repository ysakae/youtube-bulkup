# アーキテクチャ設計書 (Architecture Guide)

`youtube-bulkup` のシステムアーキテクチャ、主要コンポーネント、およびデータフローについて解説します。

## 1. プロジェクト概要

本ツールは、ローカルディレクトリ内の動画ファイルを走査し、メタデータを自動生成した上で YouTube Data API を介して一括アップロードを行う CLI アプリケーションです。
Python で実装されており、`typer` による CLI インターフェースと `rich` によるリッチなコンソール出力を特徴としています。

## 2. ディレクトリ構造

主要なディレクトリとファイルの役割は以下の通りです。

```text
youtube-bulkup/
├── .github/          # GitHub Actions ワークフロー定義
├── docs/             # 開発者向けドキュメント
├── src/              # ソースコード本体
│   ├── commands/     # CLIコマンド定義 (auth, upload, history...)
│   ├── lib/          # 共通モジュール・コアロジック
│   │   ├── auth/     # 認証・プロファイル管理 (auth.py, profiles.py)
│   │   ├── core/     # 設定・ログ (config.py, logger.py)
│   │   ├── data/     # データ永続化 (history.py)
│   │   └── video/    # 動画処理 (metadata.py, scanner.py, uploader.py)
│   ├── services/     # ビジネスロジック (upload_manager.py)
│   └── main.py       # アプリケーションエントリーポイント
├── tests/            # pytest によるテストコード (srcと同様の構成)
├── client_secrets.json # GCP OAuth クライアント情報 (ユーザーが配置)
├── settings.yaml     # ユーザー設定ファイル
└── tokens/           # 認証トークン保存ディレクトリ
```

## 3. データフロー

アプリケーションの主な処理フローは以下の通りです。

```mermaid
graph TD
    User[ユーザー] -->|コマンド実行| CLI["src/main.py"]
    CLI --> Commands["src/commands/*"]
    Commands --> Service["src/services/upload_manager.py"]
    
    Commands -.-> Auth["src/lib/auth"]
    Auth -->|認証| YoutubeAPI[Google YouTube API]
    
    Service --> Scanner["src/lib/video/scanner.py"]
    Scanner -->|動画ファイルリスト| Metadata["src/lib/video/metadata.py"]
    
    Metadata -->|"ファイル解析 (hachoir)"| FileInfo["動画属性 (日時等)"]
    FileInfo -->|整形| UploadMeta[アップロード用メタデータ]
    
    Service --> Uploader["src/lib/video/uploader.py"]
    Uploader -->|アップロード| YoutubeAPI
    Uploader -->|進捗表示| UI[Rich Console]
    
    Uploader -->|結果記録| History["src/lib/data/history.py"]
    History --> HistoryFile[upload_history.json]
```

## 4. 主要コンポーネント詳細

### 4.1 CLI エントリーポイント (`src.main`, `src.commands`)
- `src.main` は `src.commands` 配下の各モジュールを `typer` アプリケーションとして統合します。
- `auth`, `upload` などのコマンドロジックは `src.commands` パッケージに分離されています。

### 4.2 認証モジュール (`src.lib.auth`)
- `google-auth-oauthlib` を使用して OAuth 2.0 フローを処理します。
- `src.lib.auth.profiles` で複数プロファイル（トークン）の管理を行います。

### 4.3 ビジネスロジック (`src.services`)
- `src.services.upload_manager` がアップロードプロセス全体のオーケストレーション（スキャン、重複チェック、メタデータ生成、アップロード）を担当します。

### 4.4 動画処理モジュール (`src.lib.video`)
- **Scanner (`scanner.py`)**: ディレクトリ走査と動画ファイル検出を行います。
- **Metadata (`metadata.py`)**: `hachoir` を用いて動画ファイルのメタデータを抽出し、アップロード用に整形します。
- **Uploader (`uploader.py`)**: YouTube Data API v3 をラップし、リジューム可能なアップロードとリトライ処理を提供します。

### 4.5 データ管理 (`src.lib.data`)
- **History (`history.py`)**: `tinydb` を利用してアップロード履歴を管理します。重複排除や再試行ロジックの基盤となります。

### 4.6 コアモジュール (`src.lib.core`)
- **Config (`config.py`)**: アプリケーション設定の読み込み。
- **Logger (`logger.py`)**: 統一されたロギング設定。
