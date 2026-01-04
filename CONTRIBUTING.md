# 開発者向けガイド (Contributing Guide)

`youtube-bulkup` への貢献に関心を持っていただきありがとうございます！

## 環境構築

開発には `venv` の利用を推奨します。

```bash
# クローン
git clone https://github.com/ysakae/youtube-bulkup.git
cd youtube-bulkup

# 仮想環境作成と有効化
python3 -m venv .venv
source .venv/bin/activate

# 依存関係インストール (開発用にeditable install推奨)
pip install -e .
```

## 開発フロー (GitHub Flow)

1. `main` ブランチから機能ごとのブランチを作成 (`feat/xxx` や `fix/xxx`)。
2. コードを変更・コミット。
3. 検証（ドライラン推奨）。
4. PushしてPull Requestを作成。

## ドキュメント

開発に着手する前に、以下のドキュメントにも目を通してください。

- **[アーキテクチャ概要 (Architecture)](docs/ARCHITECTURE.md)**: システム全体の構成とデータフローについて。
- **[メタデータ生成仕様 (Metadata Spec)](docs/METADATA_SPEC.md)**: 動画メタデータの自動生成ルール詳細について。

## コードスタイル
- **型ヒント**: Pythonの型ヒント (`typing`) を積極的に使用してください。
- **フォーマット**: 基本的にPEP 8に準拠します。プロジェクトでは `ruff` を使用しています。
- **ロギング**: `print` ではなく `logging` (src.logger) または `rich.console` を使用してください。

### Lintの実行
```bash
# フォワーマットチェック
ruff check .

# 自動修正
ruff check --fix .
```

## テスト
`pytest` を使用した包括的なテストスイートが整備されています（カバレッジ目標：90%以上）。

### ユニットテストの実行
```bash
pytest
```

### カバレッジの計測
```bash
pytest --cov=src tests/
```

### 動作確認 (ドライラン)
1. `test_videos` ディレクトリなどにダミー動画を作成。
2. `--dry-run` オプションでスキャナーとメタデータ生成ロジックを確認。
```bash
python -m src.main upload test_videos --dry-run
```
