# プロジェクト進捗状況

> 最終更新: 2026-05-24（メール返信テンプレート化・設定JSON分離・受注No付与）

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
- [x] データモデル（8 Pydantic モデル）
- [x] Connector インターフェース（7 Protocol）
- [x] Cosmos DB アダプタ（受注・セッション・メッセージ履歴・パターン学習）
- [x] Azure SQL アダプタ（商品・顧客・在庫）
- [x] Semantic Kernel Plugin（Intake・Inventory・Exception・Communication）
- [x] Agent 定義 + Orchestrator（gpt-5.4-mini 連携）
- [x] LINE Webhook ハンドラ（署名検証・セッション管理・会話履歴保存）
- [x] 電話 Webhook ハンドラ（ACS Call Automation・音声認識・TTS応答）
- [x] 電話番号取得前のデモ受注API（`POST /api/phone-demo/message`、音声認識済みテキストをPhoneチャネル処理へ注入）
- [x] 電話/LINEの在庫問い合わせ応答（受注・引当を行わず `IInventoryService.check` で回答）
- [x] チャネル×ユーザー単位の非同期ロック（並行処理の安全性）
- [x] Learning Service（パターン記録・プロファイル更新）
- [x] テナント解決サービス（LINE/電話→テナント紐付け）
- [x] 認証（ID/パスワード + Microsoft SSO、JWT発行）
- [x] FastAPI アプリ（REST API 10エンドポイント）
- [x] 受注→会話セッション紐付け（Order.session_id）
- [x] 会話メッセージ取得API（`GET /api/orders/{id}/messages`）
- [x] 受注ステータス分離（未処理 / 要対応 の自動判定）
- [x] LINE返信ポリシー（会社名呼びかけ・汎用締め文の抑制、配達日/配達時間の確認）
- [x] Dashboard Agent サービス（Exception Triage：Z-score 数量異常 / 単位異常 / 在庫不足 / 要対応）
- [x] Resolution Agent プレビュー API（推奨アクション・顧客向け文面・確認待ち）
- [x] `/api/agent/features`, `/api/agent/exceptions`, `/api/agent/resolutions/preview` の REST API
- [x] 受注ステータスを5種に整理（要対応 / 受注済み / 配送中 / 完了 / キャンセル）。旧 `未処理`・`製造` は `受注済み`、旧 `配送` は `配送中`、旧 `返信待ち` は `要対応` に統合・自動マッピング（#64）
- [x] 受注メモ欄（`Order.memo`）と更新 API `PUT /api/orders/{order_id}/memo`（#69）
- [x] 顧客に納品グループ（`Customer.delivery_lead_time` = 当日 / 翌日 / 中1日 / 中2日）を追加。SQL スキーマも `infra/sql/003-add-delivery-lead-time.sql` で拡張（#65）
- [x] 配送予定日の自動確定（顧客リードタイム・締め時間・定休日・臨時休業を考慮）。幅でなく確定日を受注確定メッセージに含める（#82）
- [x] 休眠顧客への販促営業メッセージ自動送信サービス（`src/services/dormant_customer_service.py`）。テンプレート3パターン × 変数埋め込み、LINE プッシュ・メール両チャネル対応、dry_run 可。テンプレートは `_templates/` で外部管理
- [x] メールチャネル（Graph API Webhook）で注文メールを受信・AI処理・自動返信（`src/services/email_handler.py`）
- [x] メール返信をビジネスメール形式に整形。テンプレート（`_templates/メール返信_*.txt`）+ 設定JSON（`_templates/メール設定.json`）で管理。署名・件名ルールを設定JSONに一元化
- [x] 受注No をメール本文（`ご注文を承りました。（受注No: ORD-xxx）`）と件名（`Re: 件名 【受注No: ORD-xxx】`）に自動付与
- [x] 未登録メールアドレスのデモモード（`EMAIL_DEMO_MODE=true` + `EMAIL_DEMO_CUSTOMER_ID` で切替可能。既存の未登録対応は維持）

### フロントエンド
- [x] ダッシュボード（React + Vite + Tailwind）
  - ログイン画面（ID/パスワード + Microsoft SSO）
  - サイドバーナビゲーション（受注・在庫・顧客・分析）
  - 受注一覧を起動時のデフォルト画面に。統計カード・ドーナツチャートは「分析」タブへ分離（#63）
  - 受注一覧テーブル（日付選択・ステータスバッジ・温度帯表示）
  - 受注一覧の最終処理時刻表示
  - 受注ステータスは5種類（要対応 / 受注済み / 配送中 / 完了 / キャンセル）。旧ステータスは表示時に自動正規化
  - 受注詳細モーダル（注文会話履歴チャット表示・メモ編集欄付き）
  - Dashboard Agent サイドパネル（Exception Case 一覧・Resolution プレビュー・推奨アクション表示・表示切り替え）
  - 顧客一覧（常設編集ボタン・納品グループ列）
  - 顧客編集モーダル（納品グループ選択追加）
  - プロフィールドロップダウン（ログアウト）
  - API未接続時のデモデータフォールバック
  - ログイン画面用の濃色ロゴを追加し、白背景でも `foogent` が読めるように改善
  - 保存済みJWTから即時にログイン状態を復元し、`/api/auth/me` 検証をバックグラウンド化。ページ単位の遅延ロードとMicrosoft SSOライブラリの動的読み込みでログイン後の起動待ちを短縮

### CI/CD
- [x] `deploy-api.yml`: main push → ACR Build → Container Apps Deploy → Health Check
- [x] `deploy-frontend.yml`: main push → Vite Build → Storage Static Website Upload
- [x] `test.yml`: PR → ruff check/format + pytest

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
| ピッキングリストPDF生成 | 2h | `src/models/picking.py` のモデルは定義済み。PDF生成ロジック + API エンドポイント追加 |
| ダッシュボードにリアルタイム更新 | 1h | WebSocket or SSE で新規受注の自動反映 |

### Could

| タスク | 見積もり | 備考 |
|---|---|---|
| pytest テストスイート拡充 | 2h | 基本テストはCI済み。E2E・統合テストの追加 |
| 管理コンソール | 4h | テナント設定・商品マスタ編集UI |

## 既知の問題

1. **SQL アダプタの `product_aliases` 未活用**: `SqlProductMaster.fuzzy_match` は `product_aliases` テーブルも検索するが、テーブルにデータがない。商品エイリアスを投入すると表記ゆれ対応が改善する
2. **`aioodbc` の ODBC ドライバ**: Dockerfile で `msodbcsql18` をインストールしているが、SQL接続文字列のフォーマットが `pymssql` 形式（Key Vault格納値）。Container Apps 上での `aioodbc` 接続は未テスト。問題があれば `pymssql` ベースのアダプタに差し替える
3. **Container Apps のスケール設定**: 審査期間中の体感速度を優先し、APIは min=1, max=5 で常時1台を維持する。アイドル時コストは増えるが、ログイン後初回API・Webhookのコールドスタートを避ける
4. **LINE reply token の有効期限**: LINE の `replyToken` は30秒で失効。Agent処理に時間がかかる場合は `push` メッセージにフォールバックする必要がある
5. **`infra/modules/functions.bicep`**: Azure Functions は不使用（VM quota制約で断念）。ファイルは残存しているが `main.bicep` からの参照は削除済み

## ローカル開発

```bash
# 環境変数（.env に設定）
COSMOS_CONNECTION_STRING=...
SQL_CONNECTION_STRING=...
AZURE_OPENAI_ENDPOINT=https://ai-orderai-dev2.openai.azure.com/
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
az acr login --name acrorderaidev2
docker tag orderai-api:latest acrorderaidev2.azurecr.io/orderai-api:latest
docker push acrorderaidev2.azurecr.io/orderai-api:latest

# Container Apps 更新
az containerapp update --name ca-api-orderai-dev2 --resource-group rg-orderai-dev2 --image acrorderaidev2.azurecr.io/orderai-api:latest
```

## デモシナリオ（ハッカソン審査用）

`docs/mvp-scope.md` のシナリオ1〜4を実演:

1. **通常注文**: LINEで「りんご10箱、バナナ20kg」→ 自動受注確定 → ダッシュボードに即反映
2. **曖昧表現の学習**: 初回「ツナ缶100g」→ 確認質問 → 2回目以降は自動解釈
3. **誤発注検知**: 「トマト150kg」（普段15kg）→ 異常検知 → 確認質問
4. **いつもの注文**: 「いつものお願い」→ 学習済みパターンで自動確定
