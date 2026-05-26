# AGENTS.md

> すべてのAIエージェント（Claude Code, GitHub Copilot, Cursor等）が参照するプロジェクトルール。

## プロジェクト概要

- **プロジェクト名**: foogent（AI受発注自動一元管理システム）
- **チーム**: AINOK
- **ハッカソン**: Microsoft Agent Hackathon 2026
- **提出締切**: 2026-06-01
- **審査期間**: 2026-06-02 ~ 2026-06-18（デプロイ維持必須）
- **言語**: Python 3.12+（バックエンド）、HTML/JS（ダッシュボード）

## システム概要

食品卸・食材メーカー向けのマルチテナント対応 AI Agent SaaS。
電話・LINEからの注文を複数の専門AI Agentが協調して自動処理する。

**6層構成**: 受注チャネル → 受信処理 → マルチエージェント処理 → Connector層 → データ層 → 出力・UI層

## 技術スタック

| カテゴリ | 技術 |
|---|---|
| Agent基盤 | Azure AI Agent Service |
| LLM/Embedding | Azure AI Foundry（gpt-5.4-mini, text-embedding-3-small） |
| オーケストレーション | Semantic Kernel 1.28（Python SDK） |
| ドキュメントDB | Azure Cosmos DB Serverless（受注・パターン学習・セッション） |
| リレーショナルDB | Azure SQL Database Basic（マスタ・在庫） |
| 検索 | Azure AI Search Basic（あいまいマッチング + ベクトル検索） |
| API実行 | Azure Container Apps（FastAPI） |
| Frontend配信 | Azure Storage Static Website（React/Vite ダッシュボード） |
| コンテナレジストリ | Azure Container Registry |
| 認証 | Microsoft Entra ID |
| 秘密管理 | Azure Key Vault（RBAC認可） |
| CI/CD | GitHub Actions → ACR → Container Apps |

## デプロイ済み環境

| リソース | 名前 | URL/エンドポイント |
|---|---|---|
| リソースグループ | `rg-orderai-dev2` | Japan East |
| Container Apps API | `ca-api-orderai-dev2` | `https://ca-api-orderai-dev2.mangoground-6945bb56.japaneast.azurecontainerapps.io` |
| ダッシュボード | `storderaidev2` Static Website | `https://storderaidev2.z11.web.core.windows.net/dashboard/` |
| ACR | `acrorderaidev2` | `acrorderaidev2.azurecr.io` |
| Cosmos DB | `cosmos-orderai-dev2` | DB: `orders`, `intelligence` |
| Azure SQL | `sql-orderai-dev2` | DB: `db-orderai-dev2` |
| OpenAI | `ai-orderai-dev2` | gpt-5.4-mini + text-embedding-3-small |
| Speech | `ai-orderai-dev2-speech` | |
| AI Search | `search-orderai-dev2` | |
| Key Vault | `kv-orderai-dev2` | RBAC認可 |

### Key Vault シークレット一覧

| シークレット名 | 用途 |
|---|---|
| `cosmos-connection-string` | Cosmos DB接続文字列 |
| `sql-connection-string` | Azure SQL接続文字列 |
| `ai-services-key` | OpenAI APIキー |
| `ai-search-key` | AI Search管理キー |
| `speech-service-key` | Speech Servicesキー |
| `acs-connection-string` | ACS接続文字列 |
| `line-channel-id` | LINE Channel ID |
| `line-channel-secret` | LINE Channel Secret |
| `line-channel-access-token` | LINE Channel Access Token |

### Container Apps 環境変数

`ca-api-orderai-dev2` に以下の環境変数が設定済み:

**基盤**
`COSMOS_CONNECTION_STRING`, `SQL_CONNECTION_STRING`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, `AZURE_OPENAI_DEPLOYMENT_NAME`, `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_CHANNEL_ID`, `ACS_CONNECTION_STRING`, `ACS_PHONE_NUMBER`, `ACS_CALLBACK_BASE_URL`, `SPEECH_SERVICE_ENDPOINT`, `SPEECH_SERVICE_KEY`, `SPEECH_SERVICE_REGION`, `FRONTEND_ORIGINS`, `FRONTEND_URL`

**電話同期応答**
| 変数名 | 必須 | 説明 |
|---|---|---|
| `PHONE_SYNC_AI_ENABLED` | 任意 | `true` で電話中に Phone Order Agent + 同期在庫確認で返答（既定 `true`） |
| `PHONE_SYNC_AI_TIMEOUT_SECONDS` | 任意 | 電話中の同期AI応答の最大待機秒数（既定 `20`） |
| `PHONE_BACKGROUND_VALIDATION_ENABLED` | 任意 | 同期返答後に既存マルチAgentで正式検証・登録を非同期実行（既定 `true`） |

**Dashboard Agent**（詳細は `docs/multi-agent-design.md` の「ダッシュボード連携」節）
| 変数名 | 必須 | 説明 |
|---|---|---|
| `DASHBOARD_AGENT_ENABLED` | 任意 | `true` で Dashboard Agent 機能を有効化（既定 `false`） |
| `DASHBOARD_EXCEPTION_TRIAGE_ENABLED` | 任意 | Exception Triage の表示制御。既定は有効 |
| `DASHBOARD_RESOLUTION_AGENT_ENABLED` | 任意 | Resolution プレビュー API の表示制御。既定は有効 |
| `DASHBOARD_RESOLUTION_EXECUTE_ENABLED` | 任意 | プレビュー承認後の自動送信の許可（既定 `false`、デモ中は手動運用） |
| `DASHBOARD_AGENT_DEMO_MODE` | 任意 | デモ用挙動を切り替えるフラグ |

**認証・セキュリティ**（詳細は `docs/auth-setup.md`）
| 変数名 | 必須 | 説明 |
|---|---|---|
| `JWT_SECRET_KEY` | ✅ | JWT 署名鍵。`secrets.token_urlsafe(48)` で生成 |
| `JWT_ISSUER` | 任意 | デフォルト `orderai-api` |
| `JWT_AUDIENCE` | 任意 | デフォルト `orderai-dashboard` |
| `AUTH_COOKIE_SECURE` | 任意 | 認証 Cookie の `Secure` 属性。既定 `true`（ローカルHTTP検証時のみ `false`） |
| `AUTH_COOKIE_SAMESITE` | 任意 | 認証 Cookie の `SameSite` 属性。静的サイト/API別ドメイン運用のため既定 `none` |
| `AZURE_AD_ALLOWED_TENANTS` | SSO 使用時必須 | Microsoft Entra `tid` のカンマ区切り allowlist。未設定だと全 SSO ログイン拒否 |
| `AZURE_AD_ALLOWED_DOMAINS` | 任意 | email/UPN ドメインの追加 allowlist（小文字） |
| `ENTRA_CLIENT_ID` | SSO 使用時必須 | Entra アプリ登録のクライアント ID |
| `REGISTRATION_ENABLED` | 任意 | `true` でセルフ登録解放（デフォルト無効） |
| `REGISTRATION_INVITE_TOKEN` | 登録有効時必須 | `X-Invite-Token` ヘッダで照合する招待トークン |
| `EVENTGRID_WEBHOOK_KEY` | Phone 使用時必須 | EventGrid サブスクリプション URL の `?code=...` または `X-EventGrid-Webhook-Key` ヘッダで送られる共有鍵 |
| `LINE_FALLBACK_CUSTOMER_ID` | 任意 | LINE 未登録ユーザーからのメッセージ受信時にマップするフォールバック顧客 ID（未設定時は顧客一覧の先頭を使用） |

## APIエンドポイント

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/` | ダッシュボードへリダイレクト |
| GET | `/api/health` | ヘルスチェック |
| POST | `/api/auth/login` | ID/パスワード認証（HttpOnly CookieでJWT発行） |
| POST | `/api/auth/microsoft` | Microsoft SSO認証（HttpOnly CookieでJWT発行） |
| POST | `/api/auth/logout` | 認証 Cookie を削除 |
| GET | `/api/auth/me` | 認証ユーザー情報取得 |
| POST | `/api/line-webhook` | LINE Webhook受信（署名検証付き） |
| POST | `/api/email-webhook` | Microsoft Graph Change Notifications受信（メールチャネル） |
| POST | `/api/phone-webhook` | ACS Call Automation Webhook受信（電話チャネル） |
| POST | `/api/phone-demo/message` | 電話番号取得前のデモ用。音声認識済みテキストを電話チャネルとして受注処理（EventGrid共有鍵必須） |
| GET | `/api/speech-token` | Azure Speech SDK用の短寿命認証トークン発行（JWT認証） |
| POST | `/api/web-phone/greeting` | Web電話：通話開始・挨拶TTS音声返却（JWT認証） |
| POST | `/api/web-phone/message` | Web電話：テキストを電話チャネルとして注入、`with_audio=true`でTTS音声付き（JWT認証） |
| POST | `/api/web-phone/disconnect` | Web電話：通話切断（JWT認証） |
| GET | `/api/orders?tenant_id=T-001&delivery_date=YYYY-MM-DD` | 受注一覧（配送日指定） |
| GET | `/api/orders/events` | 受注更新の Server-Sent Events（Cookie認証） |
| GET | `/api/orders/{order_id}?tenant_id=T-001` | 受注詳細 |
| GET | `/api/products?tenant_id=T-001` | 商品マスタ一覧 |
| GET | `/api/inventory?tenant_id=T-001` | 在庫一覧（全品目） |
| GET | `/api/inventory/{product_id}?required_qty=0&tenant_id=T-001` | 在庫照会 |
| GET | `/api/customers?tenant_id=T-001` | 顧客一覧 |
| GET | `/api/orders/{order_id}/messages?tenant_id=T-001` | 受注に紐づく会話メッセージ一覧 |
| PUT | `/api/orders/{order_id}/memo?tenant_id=T-001` | 受注メモ更新（特殊対応・アレルギー・ギフト包装等） |
| PUT | `/api/customers/{customer_id}?tenant_id=T-001` | 顧客更新（LINE User ID紐付け・納品グループ等） |
| GET | `/api/agent/features` | Dashboard Agent 機能フラグ（dashboard_agent/exception_triage/resolution_agent/resolution_execute/demo_mode） |
| GET | `/api/agent/exceptions?delivery_date=YYYY-MM-DD` | 配送日単位の Exception Case 一覧（Z-score 数量異常・単位異常・在庫不足・要対応） |
| POST | `/api/agent/resolutions/preview` | Resolution Agent によるプレビュー（推奨アクション・顧客向け文面） |

## アーキテクチャドキュメント

実装前に必ず該当ドキュメントを読むこと。

| ファイル | 内容 |
|---|---|
| `docs/architecture-overview.md` | 全体俯瞰・レイヤー構成・Azureサービス一覧 |
| `docs/multi-agent-design.md` | Agent一覧・責務・フロー例・ツール定義・Learning Service |
| `docs/connector-design.md` | Connector層・テナント別差し替え・マルチテナント設計 |
| `docs/data-flow.md` | チャネル別データフロー・セッション管理・スケール戦略 |
| `docs/mvp-scope.md` | MVPスコープ・ユーザー体験シナリオ・非機能要件 |
| `docs/business-domain.md` | 業務ドメイン定義（温度帯・配送体系・不定貫・ピッキング分割） |
| `docs/line-order-branching.md` | LINE受発注の主要分岐、会話テンプレート、要件整理 |

## ドキュメント更新ルール（必須）

アプリケーションを変更したら、**同じ PR 内で**関連ドキュメントも必ず更新すること。
業務フローや会話分岐の前提を整理した場合は、`docs/line-order-branching.md` も更新対象に含めること。

| 変更内容 | 更新対象ドキュメント |
|---|---|
| API エンドポイント追加・変更 | `AGENTS.md` のAPIエンドポイント表 |
| データモデル変更（フィールド追加等） | `docs/data-flow.md`, 該当する `docs/*.md` |
| 新機能の実装完了 | `STATUS.md` の実装済みセクション |
| Connector Interface / Adapter 追加 | `AGENTS.md` のディレクトリ構成, `docs/connector-design.md` |
| 環境変数追加 | `AGENTS.md` の Container Apps 環境変数セクション |
| Cosmos DB コンテナ / SQL テーブル追加 | `AGENTS.md` のスキーマセクション |
| フロントエンド画面追加・変更 | `STATUS.md` のフロントエンドセクション |

## コーディング規約

### 全般
- Python 3.12+、型ヒント必須（`from __future__ import annotations`）
- フォーマッタ: Ruff（`ruff format` + `ruff check`、`pyproject.toml` の `line-length = 120` に準拠）
- テスト: pytest + pytest-asyncio
- 非同期: async/await を基本とする

### Semantic Kernel Plugin
- 各Agentのツールは `src/plugins/` に配置
- `@kernel_function` デコレータで定義
- コンストラクタで `TenantContext` を受け取り、`self._ctx.get_connector("I...名")` でアダプタ取得
- DB/APIへの直接アクセスは禁止 → 必ず Connector Interface 経由

### Connector パターン
- インターフェースは `src/connectors/interfaces/` に Protocol で定義
- アダプタ実装は `src/connectors/adapters/` に配置
- `src/connectors/adapters/registry.py` の `register_all_adapters()` で登録
- `ConnectorFactory` がテナント設定に基づいてランタイムで解決
- 新しいテナントのDB/API接続 → 既存Interfaceに対する新Adapterを追加

### Container Apps
- FastAPI アプリ: `src/api/main.py`（`uvicorn src.api.main:app`）
- LINE Webhook: `POST /api/line-webhook` → `LineWebhookHandler` → `OrderOrchestrator`
- Learning Service: バックグラウンドタスク（非Agent）

### Frontend
- React/Vite アプリ: `frontend/`
- 配信先: Azure Storage Static Website `/dashboard/`
- API接続先: `VITE_API_BASE_URL`

### CI/CD
- `.github/workflows/deploy-api.yml`: `main` ブランチへの push でAPIを自動デプロイ
- トリガー対象: `src/**`, `Dockerfile`, `requirements.txt`
- `.github/workflows/deploy-frontend.yml`: `main` ブランチへの push でFrontendを自動デプロイ
- トリガー対象: `frontend/**`
- `.github/workflows/docs.yml`: `main` ブランチへの push でDocsを自動デプロイ
- トリガー対象: `docs/**`, `mkdocs.yml`
- GitHub Secret: `AZURE_CREDENTIALS`（サービスプリンシパル JSON）
- APIフロー: ACR Build → Push（SHA tag + latest）→ Container Apps Update → Health Check
- Frontendフロー: Vite Build → Storage Static Website Upload

## セキュリティルール

- 秘密情報（APIキー・接続文字列）は `.env` で管理、絶対にコミットしない
- 本番では Azure Key Vault を使用
- pre-commit フックが `.githooks/` に設定済み（`git config core.hooksPath .githooks`）

## ディレクトリ構成

```
src/
├── api/                          # FastAPI アプリケーション
│   ├── main.py                   # エントリポイント（Webhook・REST API）
│   └── dashboard_agent.py        # /api/agent/* ルータ（Dashboard Agent）
├── agents/                       # Agent定義
│   ├── definitions.py            # 各Agent の Instructions（日本語プロンプト）
│   └── orchestrator.py           # OrderOrchestrator（SK Agent → Plugin呼び出し）
├── plugins/                      # Semantic Kernel Plugin
│   ├── intake_plugin.py          # 顧客特定・商品正規化・パターン照合
│   ├── inventory_plugin.py       # 在庫確認・代替品提案・在庫引当
│   ├── exception_plugin.py       # 数量異常検知・単位異常検知
│   └── communication_plugin.py   # LINE reply/push メッセージ送信
├── auth/                         # 認証モジュール
│   ├── endpoints.py              # /api/auth/* エンドポイント（login, microsoft, me）
│   ├── dependencies.py           # FastAPI 依存注入（get_tenant_id）
│   ├── service.py                # ユーザー検証・JWT発行
│   ├── microsoft.py              # Microsoft SSO トークン検証
│   └── models.py                 # AuthUser, LoginRequest 等
├── connectors/
│   ├── interfaces/               # Protocol定義（7インターフェース）
│   │   ├── order_repository.py   # IOrderRepository
│   │   ├── session_repository.py # ISessionRepository
│   │   ├── message_history_repository.py # IMessageHistoryRepository
│   │   ├── order_intelligence_store.py  # IOrderIntelligenceStore
│   │   ├── product_master.py     # IProductMaster
│   │   ├── customer_repository.py # ICustomerRepository
│   │   └── inventory_service.py  # IInventoryService
│   ├── adapters/                 # 実装
│   │   ├── cosmos_order_repository.py     # Cosmos DB → orders
│   │   ├── cosmos_session_repository.py   # Cosmos DB → sessions（TTL付き）
│   │   ├── cosmos_message_history_repository.py # Cosmos DB → message-history
│   │   ├── cosmos_intelligence_store.py   # Cosmos DB → patterns + profiles
│   │   ├── sql_product_master.py          # Azure SQL → products（LIKE検索）
│   │   ├── sql_customer_repository.py     # Azure SQL → customers
│   │   ├── sql_inventory_service.py       # Azure SQL → inventory
│   │   └── registry.py                    # 全Adapterの登録
│   ├── factory.py                # ConnectorFactory（テナント設定→Adapter解決）
│   └── context.py                # TenantContext（テナント単位の依存注入コンテナ）
├── services/
│   ├── line_handler.py           # LINE Webhook処理（署名検証・セッション管理）
│   ├── phone_handler.py          # 電話 Webhook処理（ACS Call Automation、同期AI在庫確認、非同期正式検証）
│   ├── email_handler.py          # Email Webhook処理（正規化・セッション管理）
│   ├── channel_locks.py          # チャネル×ユーザー単位の非同期ロック
│   ├── line_template_renderer.py # LINE返信テンプレート描画
│   ├── learning_service.py       # パターン記録・顧客プロファイル更新
│   ├── dashboard_agent.py        # Dashboard Agent サービス（Exception Triage / Resolution プレビュー）
│   └── tenant_resolver.py        # テナント解決（LINE/電話→テナント紐付け）
├── models/                       # Pydantic データモデル
│   ├── order.py                  # Order, OrderItem, OrderStatus, OrderSource, etc.
│   ├── customer.py               # Customer, CustomerDeliveryPreference
│   ├── product.py                # Product, UnitType
│   ├── picking.py                # PickingList, PickingItem
│   ├── intelligence.py           # OrderPattern, CustomerOrderProfile, ProductStats
│   ├── message_history.py        # MessageHistory（会話メッセージ履歴）
│   ├── session.py                # OrderSession
│   └── tenant.py                 # TenantConfig, ConnectorConfig
frontend/                         # React/Vite ダッシュボード
├── src/                           # 画面・認証・APIクライアント
├── package.json                   # npm scripts
└── vite.config.ts                 # /dashboard/ base・dev proxy

infra/
├── main.bicep                    # Bicep メインテンプレート
├── main.bicepparam               # パラメータファイル（dev環境）
├── deploy.sh                     # デプロイスクリプト
├── modules/                      # Bicep モジュール（13ファイル）
├── sql/
│   └── init-schema.sql           # SQLスキーマ + デモデータ（投入済み）
└── seed/                         # Cosmos DBシードデータ・サンプルCSV

.github/workflows/
├── deploy-api.yml                # CI/CD: main push → ACR → Container Apps
├── deploy-frontend.yml           # CI/CD: main push → Storage Static Website
└── docs.yml                      # GitHub Pages（MkDocs）

Dockerfile                        # Python 3.12 + ODBC Driver 18 + requirements
requirements.txt                  # fastapi, semantic-kernel, azure-cosmos, aioodbc, httpx, openai
```

## Azure SQL スキーマ

投入済みテーブル（`infra/sql/init-schema.sql`）:

| テーブル | 行数 | 用途 |
|---|---|---|
| `tenants` | 2 | テナント管理 |
| `customers` | 10 | 顧客マスタ（LINE User ID紐付け・納品グループ `delivery_lead_time` 対応） |
| `products` | 17 | 商品マスタ（温度帯・不定貫フラグ付き） |
| `product_aliases` | 0 | 商品名エイリアス（表記ゆれ対応） |
| `inventory` | 17 | 在庫（quantity - reserved_qty = 有効在庫） |
| `delivery_routes` | 12 | 配送ルート定義 |
| `connector_registry` | 0 | Connector設定（将来用） |
| `users` | - | ダッシュボードユーザー認証（`infra/sql/002-add-users.sql`） |

## Cosmos DB コンテナ

| データベース | コンテナ | パーティションキー | 用途 |
|---|---|---|---|
| `orders` | `order-documents` | `/id` | 受注ドキュメント |
| `orders` | `order-sessions` | `/id` | 会話セッション（TTL: 7200秒） |
| `orders` | `picking-lists` | `/id` | ピッキングリスト |
| `intelligence` | `order-patterns` | `/customer_id` | 発注パターン学習 |
| `orders` | `message-history` | `/id` | 会話メッセージ履歴（LINE/電話） |
| `intelligence` | `customer-profiles` | `/customer_id` | 顧客発注プロファイル |
