# YouTube Data API クォータ引き上げ申請ガイド

`youtube-bulkup` を使用して大量の動画をアップロードする場合、YouTube Data API のデフォルト割り当て（Quota）では不足する可能性があります。

## 引き上げの対象となる2つの割り当て

GCP コンソールの割り当てページで確認できるとおり、関係する枠は**独立した2つ**です。どちらがボトルネックかによって、申請すべき項目が変わります。

| 項目 | 既定値 | 何が消費するか | 対応する設定 |
|---|---|---|---|
| **Queries per day** | 10,000 units/日 | プレイリストへの追加・作成・削除（各 50 units）、一覧取得（1 unit）など | `quota.daily_limit` |
| **Video Uploads per day** | 100 本/日 | 動画のアップロード（`videos.insert`） | `quota.daily_video_uploads` |

> [!IMPORTANT]
> 動画のアップロードは **`Queries per day` を消費しません。** 公式ドキュメントには `videos.insert` = 1,600 units と記載されていますが、実際の GCP プロジェクトでは本数ベースの `Video Uploads per day` でカウントされます（1,600 units 換算なら7本で 10,000 units を超えるはずのところ、実測では1日 100 本前後のアップロードが成功しています）。
>
> - **1日に100本より多くアップロードしたい** → `Video Uploads per day` を申請する
> - **`playlist orphans --fix` / `dedupe --fix` の1日あたりの処理件数を増やしたい** → `Queries per day` を申請する（1件あたり 50〜100 units）

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
   引き上げたい項目を探します。

   - プレイリスト操作の余裕を増やしたい場合: **Queries per day**（1日あたりのクエリ数）
   - 1日のアップロード本数を増やしたい場合: **Video Uploads per day**（1日あたりの動画アップロード数）

   目的の項目の「すべて」または「Global」リージョンのチェックボックスを選択し、画面上部の「割り当てを編集 (EDIT QUOTAS)」をクリックします。両方を引き上げたい場合は、それぞれ個別に申請します。

5. **申請フォームの入力**
   右側にパネルが表示されます。
   - **新しい上限**: 希望する数値を入力します（例: `100000` など）。
   - **リクエストの説明 (Justification)**: なぜ増加が必要なのかを英語で説明します。

   > [!TIP]
   > 個人利用のツールであることを明記し、スパム行為ではないことを伝えるとスムーズです。

   **記入例 (Video Uploads per day):**
   > I am developing and using a personal CLI tool to back up my own video archives to my YouTube channel. The current limit of 100 video uploads per day is not enough for my backlog of about 10,000 archived videos. I request an increase to 500 uploads per day. This application is for internal use only and not distributed to public users.

   **記入例 (Queries per day):**
   > I am developing and using a personal CLI tool to back up my own video archives to my YouTube channel. In addition to uploading, the tool organizes videos into playlists (playlistItems.insert, 50 units each), which consumes the daily query quota. The current limit of 10,000 units allows only about 180 playlist assignments per day. I request an increase to 50,000 units. This application is for internal use only and not distributed to public users.

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

### "rateLimitExceeded (Video Uploads per day)" エラーについて (429)
```
reason: 'rateLimitExceeded'
message: "... 'Video Uploads per day' ..."
```

こちらは GCP の割り当て **`Video Uploads per day`（既定 100 本/日）** に到達した場合のエラーです。本ツールはこれを検知してアップロード全体を停止し、残件を報告します。

**対処法**:
- クォータのリセット（太平洋時間の深夜 / 日本時間の16〜17時頃）を待って再実行してください。
- 恒常的に足りない場合は、上記の手順で `Video Uploads per day` の引き上げを申請してください。
- GCP コンソール上の実値が既定と異なる場合は、`settings.yaml` の `quota.daily_video_uploads` を実値に合わせてください（事前の残数見積もりに使われます）。
