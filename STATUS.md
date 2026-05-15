# プロジェクト進捗状況

> 最終更新: 2026-05-15

## 実装済み

### インフラ（Azure）
- [x] Bicep テンプレート（13モジュール）作成・デプロイ済み
- [x] Azure SQL スキーマ + デモデータ投入済み（7テーブル）
- [x] Cosmos DB データベース + コンテナ作成済み（5コンテナ）
- [x] Key Vault シークレット設定済み（8件）
- [x] Container Apps 環境変数注入済み
- [x] GitHub Actions CI/CD パイプライン構築済み
- [x] サービスプリンシパル `github-orderai-deploy` 作成済み

### バックエンド
- [x] データモデル（7 Pydantic モデル）
- [x] Connector インターフェース（6 Protocol）
- [x] Cosmos DB アダプタ（受注・セッション・パターン学習）
- [x] Azure SQL アダプタ（商品・顧客・在庫）
- [x] Semantic Kernel Plugin（Intake・Inventory・Exception・Communication）
- [x] Agent 定義 + Orchestrator（GPT-4o 連携）
- [x] LINE Webhook ハンドラ（署名検証・セッション管理）
- [x] Learning Service（パターン記録・プロファイル更新）
- [x] テナント解決サービス（デモ環境用）
- [x] FastAPI アプリ（REST API 6エンドポイント）

### フロントエンド
- [x] ダッシュボード（HTML + Tailwind + Chart.js）
  - 受注一覧テーブル（日付選択・ステータスバッジ・温度帯表示）
  - 統計カード（合計・ステータス別件数）
  - ドーナツチャート（ステータス別・チャネル別）
  - 受注詳細モーダル
  - API未接続時のデモデータフォールバック

### CI/CD
- [x] `deploy-api.yml`: main push → ACR Build → Container Apps Deploy → Health Check

## 未実装（残タスク）

### Must（デモ必須）

| タスク | 優先度 | 見積もり | 備考 |
|---|---|---|---|
| LINE E2Eテスト | 高 | 1h | LINE Developers Console でWebhook URL設定後、実際のLINEメッセージで動作確認 |
| 顧客の LINE User ID 紐付け | 高 | 0.5h | `customers` テーブルの `line_user_id` にLINE User IDを登録（初回メッセージから取得） |
| Orchestrator の Agent 呼び出し改善 | 高 | 2h | 現在は単一ChatCompletionAgent。マルチAgent（Intake→Exception→Inventory→Communication）のチェーン実装 |
| Learning Service 非同期実行 | 中 | 1h | 注文確定後にバックグラウンドで `record_pattern` + `update_customer_profile` を呼ぶ |
| テナント切り替えデモ | 中 | 1h | T-001/T-002 の切り替えUI + `tenant_resolver.py` の複数テナント対応 |

### Should

| タスク | 見積もり | 備考 |
|---|---|---|
| AI Search インデックス作成 | 2h | 現在は SQL LIKE 検索。AI Search にすると「りんご」「リンゴ」「林檎」等の表記ゆれに対応 |
| Embedding ベースのパターン検索 | 2h | `cosmos_intelligence_store.py` の `find_pattern_by_embedding` を AI Search ベクトル検索に置換 |
| 電話チャネル（ACS Call Automation + AI Speech） | 4h | ACS リソースはデプロイ済み。着信→文字起こし→Agent のパイプライン実装が必要 |
| ピッキングリストPDF生成 | 2h | `src/models/picking.py` のモデルは定義済み。PDF生成ロジック + API エンドポイント追加 |
| ダッシュボードにリアルタイム更新 | 1h | WebSocket or SSE で新規受注の自動反映 |

### Could

| タスク | 見積もり | 備考 |
|---|---|---|
| pytest テストスイート | 3h | Connector Interface に対するユニットテスト |
| メールチャネル（Graph API） | 4h | |
| 管理コンソール | 4h | テナント設定・商品マスタ編集UI |

## 既知の問題

1. **SQL アダプタの `product_aliases` 未活用**: `SqlProductMaster.fuzzy_match` は `product_aliases` テーブルも検索するが、テーブルにデータがない。商品エイリアスを投入すると表記ゆれ対応が改善する
2. **`aioodbc` の ODBC ドライバ**: Dockerfile で `msodbcsql18` をインストールしているが、SQL接続文字列のフォーマットが `pymssql` 形式（Key Vault格納値）。Container Apps 上での `aioodbc` 接続は未テスト。問題があれば `pymssql` ベースのアダプタに差し替える
3. **Container Apps のスケール設定**: 現在 min=0, max=5。アイドル時は0にスケールインするため初回リクエストにコールドスタート（数秒）がかかる
4. **LINE reply token の有効期限**: LINE の `replyToken` は30秒で失効。Agent処理に時間がかかる場合は `push` メッセージにフォールバックする必要がある
5. **`infra/modules/functions.bicep`**: Azure Functions は不使用（VM quota制約で断念）。ファイルは残存しているが `main.bicep` からの参照は削除済み

## ローカル開発

```bash
# 環境変数（.env に設定）
COSMOS_CONNECTION_STRING=...
SQL_CONNECTION_STRING=...
AZURE_OPENAI_ENDPOINT=https://ai-orderai-dev.openai.azure.com/
AZURE_OPENAI_KEY=...
LINE_CHANNEL_ID=...
LINE_CHANNEL_SECRET=...
LINE_CHANNEL_ACCESS_TOKEN=...

# 起動
pip install -r requirements.txt
uvicorn src.api.main:app --reload --port 8080

# Docker ビルド（amd64）
docker buildx build --platform linux/amd64 -t orderai-api:latest -f Dockerfile .

# ACR にプッシュ
az acr login --name ca61bef3ed27acr
docker tag orderai-api:latest ca61bef3ed27acr.azurecr.io/orderai-api:latest
docker push ca61bef3ed27acr.azurecr.io/orderai-api:latest

# Container Apps 更新
az containerapp update --name ca-api-orderai-dev --resource-group rg-orderai-dev --image ca61bef3ed27acr.azurecr.io/orderai-api:latest
```

## デモシナリオ（ハッカソン審査用）

`docs/mvp-scope.md` のシナリオ1〜4を実演:

1. **通常注文**: LINEで「りんご10箱、バナナ20kg」→ 自動受注確定 → ダッシュボードに即反映
2. **曖昧表現の学習**: 初回「ツナ缶100g」→ 確認質問 → 2回目以降は自動解釈
3. **誤発注検知**: 「トマト150kg」（普段15kg）→ 異常検知 → 確認質問
4. **いつもの注文**: 「いつものお願い」→ 学習済みパターンで自動確定
