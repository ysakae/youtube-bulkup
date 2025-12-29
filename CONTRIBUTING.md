# 開発者向けガイド (Contributing Guide)

`youtube-up-agy` への貢献に関心を持っていただきありがとうございます！

## 環境構築

開発には `venv` の利用を推奨します。

```bash
# クローン
git clone https://github.com/ysakae/youtube-up-agy.git
cd youtube-up-agy

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

## コードスタイル
- **型ヒント**: Pythonの型ヒント (`typing`) を積極的に使用してください。
- **フォーマット**: 基本的にPEP 8に準拠します。
- **ロギング**: `print` ではなく `logging` (src.logger) または `rich.console` を使用してください。

## テスト
現状、自動テストスイートは整備中ですが、以下の手順で動作確認を行ってください。

1. `test_videos` ディレクトリなどにダミー動画を作成。
2. `--dry-run` オプションでスキャナーとAI生成ロジックを確認。
```bash
python -m src.main upload test_videos --dry-run
```
