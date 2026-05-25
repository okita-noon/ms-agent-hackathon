# プロジェクト進捗状況

> 最終更新: 2026-05-25（電話同期AI応答・ログインフラッシュ解消・UI改善）

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
- [x] Phone Order Agent による電話同期応答（注文抽出 + `IInventoryService.check` の同期在庫確認 + 20秒タイムアウト時フォールバック + 非同期正式検証）
- [x] 電話/LINEの在庫問い合わせ応答（受注・引当を行わず `IInventoryService.check` で回答）
- [x] チャネル×ユーザー単位の非同期ロック（並行処理の安全性）
- [x] Learning Service（パターン記録・プロファイル更新）
- [x] テナント解決サービス（LINE/電話→テナント紐付け）
- [x] 認証（ID/パスワード + Microsoft SSO、JWT発行）
- [x] FastAPI アプリ（REST API 10エンドポイント）
- [x] 受注→会話セッション紐付け（Order.session_id）
- [x] 会話メッセージ取得API（`GET /api/orders/{id}/messages`）
- [x] 会話履歴を全チャネルで保存（`src/services/message_history_logger.py` で共通化）。従来 LINE のみだった `message-history` への保存を**メール・電話**にも拡張。メールは受注を会話セッションに紐付ける `session_id` も付与し、ダッシュボードの受注詳細でメール／電話のやり取りも表示可能に
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
- [x] メールデモモードの顧客名フォールバック修正（`InboundMessage.customer_name` 追加。Intake Agentに顧客情報を直接渡し、未登録メールでも「None様」ではなくフォールバック顧客名を表示）
- [x] テナント会社名を「AINOKハッカソン食品株式会社」に統一（テナント設定・Agent定義・メール署名設定）
- [x] デモ用顧客 C-011（株式会社Zennハッカソン）追加。未登録メールのデフォルトフォールバック先
- [x] LINE 返信テンプレート基盤（`_templates/line/` + `line_template_renderer.py`）を追加。LINE では受注Noを表示せず、定型返信を優先
- [x] LINE の現在注文コンテキスト（`current_order_id` / `current_order_snapshot`）をセッションとオーケストレータに追加。1顧客1オープン注文前提で追加・変更・取消へ寄せる

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
  - プロフィールアイコンの表示名フォールバックと、デモユーザー表示名補正SQLを追加
  - API未接続時のデモデータフォールバック
  - ログイン画面用の濃色ロゴを追加し、白背景でも `foogent` が読めるように改善
  - 保存済みJWTから即時にログイン状態を復元し、`/api/auth/me` 検証をバックグラウンド化。ページ単位の遅延ロードとMicrosoft SSOライブラリの動的読み込みでログイン後の起動待ちを短縮

### CI/CD
- [x] `deploy-api.yml`: main push → ACR Build → Container Apps Deploy → Health Check
- [x] `deploy-frontend.yml`: main push → Vite Build → Storage Static Website Upload
- [x] `test.yml`: PR → ruff check/format + pytest

## デモデータ（Azure SQL 投入済み）

### テナント

| tenant_id | 名称 | プラン |
|---|---|---|
| T-001 | AINOKハッカソン食品（旧: デモ環境A・食品卸） | demo |
| T-002 | デモ環境B（食材メーカー） | demo |

### 顧客（T-001 配下・11社）

| customer_id | 会社名 | 略称 | 配送ルート | 運送便 | リードタイム | 備考 |
|---|---|---|---|---|---|---|
| C-001 | 株式会社A | A社 | 北関東便 | 自社便 | 翌日 | |
| C-002 | 株式会社B | B社 | 西日本便 | 芦川便 | 中1日 | |
| C-003 | 株式会社C | C社 | 中部便 | 自社便 | 翌日 | |
| C-004 | 株式会社D | D社 | 九州便 | 自社便 | 当日 | |
| C-005 | 株式会社E | E社 | 北海道便 | 芦川便 | 中1日 | |
| C-006 | 株式会社F | F社 | 東北便 | 自社便 | 中2日 | |
| C-007 | 株式会社G | G社 | 関東便 | 自社便 | 翌日 | |
| C-008 | 株式会社H | H社 | 関西便 | 芦川便 | 中1日 | |
| C-009 | 株式会社I | I社 | 中国便 | 自社便 | 当日 | |
| C-010 | 株式会社J | J社 | 四国便 | 自社便 | 中2日 | |
| C-011 | 株式会社Zennハッカソン | Zenn社 | 北関東便 | 自社便 | 翌日 | メールデモモードのフォールバック先（`EMAIL_DEMO_CUSTOMER_ID=C-011`） |

### 商品（T-001 配下・17品）

| product_id | 商品名 | 単位 | 温度帯 | 在庫数 |
|---|---|---|---|---|
| P-001 | りんご | 箱 | 冷蔵 | 50 |
| P-002 | バナナ | kg | 常温 | 200 |
| P-003 | みかん | 個 | 冷凍 | 500 |
| P-004 | ぶどう | 房 | 常温 | 30 |
| P-005 | もも | 箱 | 冷蔵 | 40 |
| P-006 | いちご | パック | 常温 | 100 |
| P-007 | メロン | 玉 | 冷凍 | 15 |
| P-008 | スイカ | 個 | 常温 | 10 |
| P-009 | なし | 個 | 冷蔵 | 60 |
| P-010 | マンゴー | 個 | 冷凍 | 25 |
| P-011 | キウイ | 個 | 常温 | 80 |
| P-012 | さくらんぼ | パック | 冷蔵 | 45 |
| P-013 | いちじく | 箱 | 冷凍 | 20 |
| P-014 | レモン | 個 | 常温 | 70 |
| P-015 | アボカド | 個 | 冷蔵 | 30 |
| P-016 | にんにく | kg | 常温 | 50 |
| P-017 | ブルーベリー | 箱 | 冷凍 | 15 |

### 配送ルート（T-001 配下・12路線）

| route_id | ルート名 | 地域 | 運送便 |
|---|---|---|---|
| R-001 | 北関東便 | 北関東 | 自社便 |
| R-002 | 西日本便 | 西日本 | 芦川便 |
| R-003 | 中部便 | 中部 | 自社便 |
| R-004 | 九州便 | 九州 | 自社便 |
| R-005 | 北海道便 | 北海道 | 芦川便,冷蔵ヤマト便,冷凍ヤマト便 |
| R-006 | 東北便 | 東北 | 自社便,冷凍ヤマト便 |
| R-007 | 関東便 | 関東 | 自社便 |
| R-008 | 関西便 | 関西 | 芦川便 |
| R-009 | 中国便 | 中国 | 自社便 |
| R-010 | 四国便 | 四国 | 自社便 |
| R-011 | 沖縄便 | 沖縄 | 芦川便 |
| R-012 | 北陸便 | 北陸 | 自社便 |

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

1. **SMTP経由のメール送信がGmailでSPAM判定される場合がある**: Container Appsは `EMAIL_EXTERNAL_ROUTE_MODE=smtp_first` でSMTP優先送信済み。SMTP送信自体は成功するが、Gmailがスパム判定することがある。原因候補: subscription大量蓄積（73件→1件に整理済み）で短期間に大量通知が発生しレピュテーション低下、またはメール本文に「None様」等の不自然な表現が含まれている点
2. **Graph webhook subscriptionの蓄積**: subscriptionを作成するだけで削除しない運用だったため73件まで蓄積し、1通のメールに対して数十回webhookが発火していた。2026-05-24に全削除→1件に整理済み。subscription更新ジョブの自動化は未実装
3. **Dockerfileに `_templates/` のCOPY漏れ**: メールテンプレート外部化（#113）後、`COPY _templates/ _templates/` がDockerfileに含まれておらず、メール返信時にFileNotFoundErrorが発生していた。#115で修正済み
4. **~~メールテンプレートの顧客名がNone表示~~（修正済み）**: `InboundMessage.customer_name` を追加し、デモモードフォールバック時にも顧客名を正しく設定。Intake Agentに `known_customer_id` / `known_customer_name` として渡すことで解決
5. **SQL アダプタの `product_aliases` 未活用**: `SqlProductMaster.fuzzy_match` は `product_aliases` テーブルも検索するが、テーブルにデータがない。商品エイリアスを投入すると表記ゆれ対応が改善する
2. **`aioodbc` の ODBC ドライバ**: Dockerfile で `msodbcsql18` をインストールしているが、SQL接続文字列のフォーマットが `pymssql` 形式（Key Vault格納値）。Container Apps 上での `aioodbc` 接続は未テスト。問題があれば `pymssql` ベースのアダプタに差し替える
3. **Container Apps のスケール設定**: APIは min=1, max=5 で常時1台を維持するよう設定済み（2026-05-24適用）。アイドル課金は月$5〜10程度だが、コールドスタートを完全に回避できる
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
