# YouTube Data API クォータ引き上げ申請ガイド

`youtube-bulkup` を使用して大量の動画をアップロードする場合、YouTube Data API のデフォルト割り当て（Quota）である **1日あたり 10,000 ユニット** では不足する可能性があります。
（参考: 動画アップロード1回につき約 1,600 ユニット消費するため、1日あたり約6本のアップロードが上限となります）

制限を引き上げるためには、Google Cloud Platform (GCP) コンソールから申請（Quota Increase Request）を行う必要があります。

## 前提条件

- YouTube Data API v3 が有効化されている GCP プロジェクトがあること。
- プロジェクトの編集者またはオーナー権限を持つアカウントでログインしていること。

## 申請手順

1. **Google Cloud Console にアクセス**
   [Google Cloud Console](https://console.cloud.google.com/) にアクセスし、対象のプロジェクトを選択します。

2. **「IAM と管理」>「割り当て」へ移動**
   左側のメニューから「IAM と管理」>「割り当て (Quotas)」を選択します。

3. **YouTube Data API v3 を検索**
   フィルターに `YouTube Data API v3` と入力し、リストを絞り込みます。
   
4. **対象のクォータを選択**
   **Queries per day**（1日あたりのクエリ数）という項目を探します。
   これの「すべて」または「Global」リージョンのチェックボックスを選択し、画面上部の「割り当てを編集 (EDIT QUOTAS)」をクリックします。

5. **申請フォームの入力**
   右側にパネルが表示されます。
   - **新しい上限**: 希望する数値を入力します（例: `100000` など）。
   - **リクエストの説明 (Justification)**: なぜ増加が必要なのかを英語で説明します。

   > [!TIP]
   > 個人利用のツールであることを明記し、スパム行為ではないことを伝えるとスムーズです。

   **記入例:**
   > I am developing and using a personal CLI tool to backup my own video archives to my YouTube channel. The current limit of 10,000 units allows only about 6 uploads per day (1,600 units per upload). I have a large backlog of videos to upload, so I request an increase to 50,000 units to process about 30 videos per day. This application is for internal use only and not distributed to public users.

6. **送信と審査**
   「次へ」をクリックし、連絡先情報などを確認して送信します。
   通常、数営業日以内に Google からメール等で連絡が来ます。

## コンプライアンス監査について

大幅な引き上げを申請する場合や、アプリケーションが多数のユーザーに利用される場合、**YouTube API Services - Audit（コンプライアンス監査）** が求められることがあります。
その際は、別途案内されるフォームに従って、アプリケーションのスクリーンショットや動作デモ動画、利用規約への準拠状況などを提出する必要があります。

`youtube-bulkup` は現状、個人利用を想定したCLIツールであるため、その旨をしっかり説明することで、簡易的な審査で済む場合が多いですが、Google の判断次第となります。

## トラブルシューティング

### "uploadLimitExceeded" エラーについて (400 Bad Request)
もし以下のようなエラーが発生した場合：
```
reason: 'uploadLimitExceeded'
message: 'The user has exceeded the number of videos they may upload.'
```

これは **APIのクォータ制限（Quota）とは異なります**。
これは YouTube アカウント自体に設定されている「1日あたりの動画アップロード本数制限」です。スパム対策として設定されており、アカウントの信頼度や履歴によって変動しますが、一般的には数本〜数十本程度で制限がかかることがあります。

**対処法**:
- この制限は GCP コンソールからは変更できません。
- **24時間待ってから**再度試してください。
- アカウントの電話番号認証などを済ませると緩和される場合があります。
