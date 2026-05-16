# AGENTS.md

> すべてのAIエージェント（Claude Code, GitHub Copilot, Cursor等）が参照するプロジェクトルール。

## プロジェクト概要

- **プロジェクト名**: AI受発注自動一元管理システム
- **チーム**: ASKNOI_AI木曜会
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
| LLM/Embedding | Azure AI Foundry（GPT-4o, text-embedding-3-small） |
| オーケストレーション | Semantic Kernel 1.28（Python SDK） |
| ドキュメントDB | Azure Cosmos DB Serverless（受注・パターン学習・セッション） |
| リレーショナルDB | Azure SQL Database Basic（マスタ・在庫） |
| 検索 | Azure AI Search Basic（あいまいマッチング + ベクトル検索） |
| アプリ実行 | Azure Container Apps（FastAPI + ダッシュボード） |
| コンテナレジストリ | Azure Container Registry |
| 認証 | Microsoft Entra ID |
| 秘密管理 | Azure Key Vault（RBAC認可） |
| CI/CD | GitHub Actions → ACR → Container Apps |

## デプロイ済み環境

| リソース | 名前 | URL/エンドポイント |
|---|---|---|
| リソースグループ | `rg-orderai-dev` | Japan East |
| Container Apps API | `ca-api-orderai-dev` | `https://ca-api-orderai-dev.thankfulstone-903cb4eb.japaneast.azurecontainerapps.io` |
| ダッシュボード | 同上 | 上記URL `/dashboard/` |
| ACR | `ca61bef3ed27acr` | `ca61bef3ed27acr.azurecr.io` |
| Cosmos DB | `cosmos-orderai-dev` | DB: `orders`, `intelligence` |
| Azure SQL | `sql-orderai-dev` | DB: `db-orderai-dev` |
| OpenAI | `ai-orderai-dev` | GPT-4o + text-embedding-3-small |
| Speech | `ai-orderai-dev-speech` | |
| AI Search | `search-orderai-dev` | |
| Key Vault | `kv-orderai-dev` | RBAC認可 |

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

`ca-api-orderai-dev` に以下の環境変数が設定済み:
`COSMOS_CONNECTION_STRING`, `SQL_CONNECTION_STRING`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_CHANNEL_ID`, `ACS_CONNECTION_STRING`, `ACS_PHONE_NUMBER`, `ACS_CALLBACK_BASE_URL`, `SPEECH_SERVICE_ENDPOINT`, `SPEECH_SERVICE_KEY`

## APIエンドポイント

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/` | ダッシュボードへリダイレクト |
| GET | `/api/health` | ヘルスチェック |
| POST | `/api/line-webhook` | LINE Webhook受信（署名検証付き） |
| POST | `/api/phone-webhook` | ACS Call Automation Webhook受信（電話チャネル） |
| GET | `/api/orders?tenant_id=T-001&delivery_date=YYYY-MM-DD` | 受注一覧（配送日指定） |
| GET | `/api/orders/{order_id}?tenant_id=T-001` | 受注詳細 |
| GET | `/api/products?tenant_id=T-001` | 商品マスタ一覧 |
| GET | `/api/inventory?tenant_id=T-001` | 在庫一覧（全品目） |
| GET | `/api/inventory/{product_id}?required_qty=0&tenant_id=T-001` | 在庫照会 |
| GET | `/api/customers?tenant_id=T-001` | 顧客一覧 |
| PUT | `/api/customers/{customer_id}?tenant_id=T-001` | 顧客更新（LINE User ID紐付け等） |

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

## コーディング規約

### 全般
- Python 3.12+、型ヒント必須（`from __future__ import annotations`）
- フォーマッタ: Ruff（`ruff format` + `ruff check`）
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
- ダッシュボード: `src/dashboard/` を `/dashboard` にマウント（StaticFiles）
- LINE Webhook: `POST /api/line-webhook` → `LineWebhookHandler` → `OrderOrchestrator`
- Learning Service: バックグラウンドタスク（非Agent）

### CI/CD
- `.github/workflows/deploy-api.yml`: `main` ブランチへの push で自動デプロイ
- トリガー対象: `src/**`, `Dockerfile`, `requirements.txt`
- GitHub Secret: `AZURE_CREDENTIALS`（サービスプリンシパル JSON）
- フロー: ACR Build → Push（SHA tag + latest）→ Container Apps Update → Health Check

## セキュリティルール

- 秘密情報（APIキー・接続文字列）は `.env` で管理、絶対にコミットしない
- 本番では Azure Key Vault を使用
- pre-commit フックが `.githooks/` に設定済み（`git config core.hooksPath .githooks`）

## ディレクトリ構成

```
src/
├── api/                          # FastAPI アプリケーション
│   └── main.py                   # エントリポイント（Webhook・REST API・静的ファイル配信）
├── agents/                       # Agent定義
│   ├── definitions.py            # 各Agent の Instructions（日本語プロンプト）
│   └── orchestrator.py           # OrderOrchestrator（SK Agent → Plugin呼び出し）
├── plugins/                      # Semantic Kernel Plugin
│   ├── intake_plugin.py          # 顧客特定・商品正規化・パターン照合
│   ├── inventory_plugin.py       # 在庫確認・代替品提案・在庫引当
│   ├── exception_plugin.py       # 数量異常検知・単位異常検知
│   └── communication_plugin.py   # LINE reply/push メッセージ送信
├── connectors/
│   ├── interfaces/               # Protocol定義（6インターフェース）
│   │   ├── order_repository.py   # IOrderRepository
│   │   ├── session_repository.py # ISessionRepository
│   │   ├── order_intelligence_store.py  # IOrderIntelligenceStore
│   │   ├── product_master.py     # IProductMaster
│   │   ├── customer_repository.py # ICustomerRepository
│   │   └── inventory_service.py  # IInventoryService
│   ├── adapters/                 # 実装
│   │   ├── cosmos_order_repository.py     # Cosmos DB → orders
│   │   ├── cosmos_session_repository.py   # Cosmos DB → sessions（TTL付き）
│   │   ├── cosmos_intelligence_store.py   # Cosmos DB → patterns + profiles
│   │   ├── sql_product_master.py          # Azure SQL → products（LIKE検索）
│   │   ├── sql_customer_repository.py     # Azure SQL → customers
│   │   ├── sql_inventory_service.py       # Azure SQL → inventory
│   │   └── registry.py                    # 全Adapterの登録
│   ├── factory.py                # ConnectorFactory（テナント設定→Adapter解決）
│   └── context.py                # TenantContext（テナント単位の依存注入コンテナ）
├── services/
│   ├── line_handler.py           # LINE Webhook処理（署名検証・セッション管理）
│   ├── learning_service.py       # パターン記録・顧客プロファイル更新
│   └── tenant_resolver.py        # テナント解決（LINE→テナント紐付け）
├── models/                       # Pydantic データモデル
│   ├── order.py                  # Order, OrderItem, OrderStatus, OrderSource, etc.
│   ├── customer.py               # Customer, CustomerDeliveryPreference
│   ├── product.py                # Product, UnitType
│   ├── picking.py                # PickingList, PickingItem
│   ├── intelligence.py           # OrderPattern, CustomerOrderProfile, ProductStats
│   ├── session.py                # OrderSession
│   └── tenant.py                 # TenantConfig, ConnectorConfig
└── dashboard/                    # フロントエンド（HTML + Tailwind + Chart.js）
    ├── index.html                # SPA メインページ
    └── app.js                    # 受注一覧・統計・詳細モーダル

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
└── docs.yml                      # GitHub Pages（MkDocs）

Dockerfile                        # Python 3.12 + ODBC Driver 18 + requirements
requirements.txt                  # fastapi, semantic-kernel, azure-cosmos, aioodbc, httpx, openai
```

## Azure SQL スキーマ

投入済みテーブル（`infra/sql/init-schema.sql`）:

| テーブル | 行数 | 用途 |
|---|---|---|
| `tenants` | 2 | テナント管理 |
| `customers` | 10 | 顧客マスタ（LINE User ID紐付け対応） |
| `products` | 17 | 商品マスタ（温度帯・不定貫フラグ付き） |
| `product_aliases` | 0 | 商品名エイリアス（表記ゆれ対応） |
| `inventory` | 17 | 在庫（quantity - reserved_qty = 有効在庫） |
| `delivery_routes` | 12 | 配送ルート定義 |
| `connector_registry` | 0 | Connector設定（将来用） |

## Cosmos DB コンテナ

| データベース | コンテナ | パーティションキー | 用途 |
|---|---|---|---|
| `orders` | `order-documents` | `/id` | 受注ドキュメント |
| `orders` | `order-sessions` | `/id` | 会話セッション（TTL: 7200秒） |
| `orders` | `picking-lists` | `/id` | ピッキングリスト |
| `intelligence` | `order-patterns` | `/customer_id` | 発注パターン学習 |
| `intelligence` | `customer-profiles` | `/customer_id` | 顧客発注プロファイル |
