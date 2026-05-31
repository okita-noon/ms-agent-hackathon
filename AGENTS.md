# AGENTS.md

> すべてのAIエージェント（Claude Code, GitHub Copilot, Cursor等）が参照するプロジェクトルール。

## AI エージェント共通ルール（必須）

### セッション開始時
- 別作業は別セッションで扱う前提のため、各AIエージェントは**編集前に専用 git worktree を用意してそこで作業する**
- 既存の通常 checkout（例: `/Users/okita/dev/ms-agent-hackathon`）や他エージェントの worktree 上で、直接編集・commit・push してはならない
- Codex は `.codex/worktrees/<task-slug>`、Claude Code は `.claude/worktrees/<task-slug>` を標準の worktree 配置先とする
- worktree は `origin/main` から作成し、ブランチ名はエージェント名を prefix にする（例: `codex/login-copy-update`, `claude/exception-modal`）
- worktree 作成には `scripts/new_agent_worktree.sh <agent> <task-slug>` を使う。例: `scripts/new_agent_worktree.sh codex login-copy-update`
- 既に専用 worktree 内にいる場合のみ、その worktree を継続利用してよい
- 未コミット変更がある場合は勝手に破棄せず、ユーザー変更か前回作業かを確認してから進める

### Pull Request 作成前チェック
PR を作成する前に以下を**必ず**実行し、全てパスすることを確認する:
1. `ruff check src/ tests/` — lint エラーがないこと
2. `ruff format --check src/ tests/` — フォーマット違反がないこと
3. `git fetch origin main && git merge origin/main --no-commit --no-ff` でコンフリクトがないこと（確認後 `git merge --abort`）
4. **上記1〜3の実行と結果確認が終わるまで、PRを作成してはならない**

### Push 前チェック
- 現在のブランチに紐づく PR が既にマージ済みの場合、同じブランチに push してはいけない
- 新しいブランチを切り、新規 PR として作成すること

## プロジェクト概要

- **プロジェクト名**: foogent（AI受発注自動一元管理システム）
- **チーム**: AINOK
- **ハッカソン**: Microsoft Agent Hackathon 2026
- **提出締切**: 2026-06-01
- **審査期間**: 2026-06-02 ~ 2026-06-18（デプロイ維持必須）
- **言語**: Python 3.12+（バックエンド）、TypeScript/React（ダッシュボード）

## システム概要

食品卸・食材メーカー向けのマルチテナント対応 AI Agent SaaS。
電話・LINE・メールからの注文を複数の専門AI Agentが協調して自動処理する。

**6層構成**: 受注チャネル → 受信処理 → マルチエージェント処理 → Connector層 → データ層 → 出力・UI層

## 技術スタック

| カテゴリ | 技術 |
|---|---|
| Agent基盤 | Semantic Kernel（ChatCompletionAgent） |
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
| ダッシュボード | `storderaidev2` Static Website | `https://storderaidev2.z11.web.core.windows.net/` |
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

**商品検索（AI Search）**
| 変数名 | 必須 | 説明 |
|---|---|---|
| `AI_SEARCH_ENDPOINT` | 任意 | Azure AI Search エンドポイント（例: `https://search-orderai-dev2.search.windows.net`）。設定時は AI Search で商品名の表記ゆれ検索を行う。未設定時は SQL LIKE にフォールバック |
| `AI_SEARCH_KEY` | 任意 | Azure AI Search 管理キー。`AI_SEARCH_ENDPOINT` と両方設定で AI Search が有効 |

**電話同期応答**
| 変数名 | 必須 | 説明 |
|---|---|---|
| `PHONE_SYNC_AI_TIMEOUT_SECONDS` | 任意 | 電話中の同期AI応答の最大待機秒数（既定 `20`） |

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
| `JWT_EXPIRE_HOURS` | 任意 | JWT トークンの有効期間（時間）。既定 `24` |

**LINE Tester**
| 変数名 | 必須 | 説明 |
|---|---|---|
| `LINE_TESTER_PUBLIC_ENABLED` | 任意 | LINE Tester ページの有効/無効。既定 `true` |
| `LINE_TESTER_TENANT_ID` | 任意 | LINE Tester で使用するテナント ID。既定 `T-001` |
| `LINE_TESTER_ACCESS_CODE` | 任意 | LINE Tester ページのアクセスコード。既定 `test` |

**メールチャネル（Graph API）**
| 変数名 | 必須 | 説明 |
|---|---|---|
| `GRAPH_CLIENT_ID` | メール使用時必須 | Microsoft Graph アプリ登録のクライアント ID |
| `GRAPH_CLIENT_SECRET` | メール使用時必須 | Microsoft Graph アプリ登録のクライアントシークレット |
| `GRAPH_TENANT_ID` | メール使用時必須 | Microsoft Entra テナント ID |
| `GRAPH_MAILBOX_USER_ID` | メール使用時必須 | Graph API で監視するメールボックスのユーザー ID |
| `GRAPH_MAILBOX_ADDRESS` | 任意 | メールボックスのメールアドレス。既定 `order@example.com` |
| `GRAPH_WEBHOOK_URL` | メール使用時必須 | Graph Change Notifications の Webhook URL |
| `GRAPH_WEBHOOK_CLIENT_STATE` | 任意 | Graph Webhook の検証用 clientState。既定 `orderai-webhook` |
| `GRAPH_DELEGATED_ACCESS_TOKEN` | 委任フロー時 | Graph 委任認証のアクセストークン |
| `GRAPH_DELEGATED_REFRESH_TOKEN` | 委任フロー時 | Graph 委任認証のリフレッシュトークン |
| `GRAPH_DELEGATED_SCOPE` | 任意 | Graph 委任認証のスコープ |
| `EMAIL_EXTERNAL_ROUTE_MODE` | 任意 | メール外部送信ルーティング（`graph` / `smtp_first`）。既定 `graph` |
| `EMAIL_INTERNAL_DOMAINS` | 任意 | 内部メールドメインのカンマ区切りリスト |

**SMTP フォールバック**
| 変数名 | 必須 | 説明 |
|---|---|---|
| `SMTP_FALLBACK_HOST` | SMTP使用時 | SMTP サーバーホスト |
| `SMTP_FALLBACK_PORT` | 任意 | SMTP ポート。既定 `587` |
| `SMTP_FALLBACK_USERNAME` | SMTP使用時 | SMTP 認証ユーザー名 |
| `SMTP_FALLBACK_PASSWORD` | SMTP使用時 | SMTP 認証パスワード |
| `SMTP_FALLBACK_FROM_ADDRESS` | 任意 | SMTP 送信元アドレス |
| `SMTP_FALLBACK_STARTTLS` | 任意 | STARTTLS 使用。既定 `true` |

**AI Search**
| 変数名 | 必須 | 説明 |
|---|---|---|
| `AI_SEARCH_ENDPOINT` | AI Search 使用時 | Azure AI Search のエンドポイント URL |
| `AI_SEARCH_KEY` | AI Search 使用時 | Azure AI Search の管理キー |

**Agent 制御**
| 変数名 | 必須 | 説明 |
|---|---|---|
| `USE_MULTI_AGENT` | 任意 | `true` でマルチ Agent 処理を有効化。既定 `true` |

## APIエンドポイント

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/` | ダッシュボードへリダイレクト |
| GET | `/dashboard/{path}` | ダッシュボード SPA（フロントエンド HTML 配信） |
| GET | `/api/health` | ヘルスチェック |
| POST | `/api/auth/login` | ID/パスワード認証（HttpOnly CookieでJWT発行） |
| POST | `/api/auth/register` | セルフ登録（`REGISTRATION_ENABLED=true` + `X-Invite-Token` 必須） |
| POST | `/api/auth/microsoft` | Microsoft SSO認証（HttpOnly CookieでJWT発行） |
| POST | `/api/auth/logout` | 認証 Cookie を削除 |
| GET | `/api/auth/me` | 認証ユーザー情報取得 |
| GET | `/line-tester` | LINE Tester ページ（HTMLレスポンス、アクセスコード認証） |
| POST | `/line-tester/unlock` | LINE Tester アクセスコード認証 |
| GET | `/api/line-tester/customers` | LINE Tester 用顧客一覧 |
| POST | `/api/line-tester/message` | LINE Tester メッセージ送信（LINE チャネルと同一処理パス） |
| POST | `/api/line-webhook` | LINE Webhook受信（署名検証付き） |
| GET/POST | `/api/email-webhook` | Microsoft Graph Change Notifications受信（メールチャネル。GET はサブスクリプション検証用） |
| POST | `/api/phone-webhook` | ACS Call Automation Webhook受信（電話チャネル） |
| POST | `/api/phone-demo/message` | 電話番号取得前のデモ用。音声認識済みテキストを電話チャネルとして受注処理（EventGrid共有鍵必須） |
| GET | `/api/speech-token` | Azure Speech SDK用の短寿命認証トークン発行（Cookie認証） |
| POST | `/api/web-phone/greeting` | 電話発注（Web）：通話開始・挨拶TTS音声返却。`customer_id` で顧客指定可（Cookie認証） |
| POST | `/api/web-phone/message` | 電話発注（Web）：テキストを電話チャネルとして注入、`customer_id` / `with_audio=true` 対応（Cookie認証） |
| POST | `/api/web-phone/disconnect` | 電話発注（Web）：通話切断（Cookie認証） |
| GET | `/api/orders?tenant_id=T-001&delivery_date=YYYY-MM-DD` | 受注一覧（配送日指定） |
| GET | `/api/orders/events` | 受注更新の Server-Sent Events（Cookie認証） |
| GET | `/api/orders/{order_id}?tenant_id=T-001` | 受注詳細 |
| GET | `/api/products?tenant_id=T-001` | 商品マスタ一覧 |
| GET | `/api/products/suggest?q=りん&tenant_id=T-001` | 商品名オートコンプリート（AI Search Suggester。未構成時は空配列） |
| GET | `/api/inventory?tenant_id=T-001` | 在庫一覧（全品目） |
| GET | `/api/inventory/{product_id}?required_qty=0&tenant_id=T-001` | 在庫照会 |
| GET | `/api/customers?tenant_id=T-001` | 顧客一覧 |
| GET | `/api/orders/{order_id}/messages?tenant_id=T-001` | 受注に紐づく会話メッセージ一覧 |
| PUT | `/api/orders/{order_id}/memo?tenant_id=T-001` | 受注メモ更新（特殊対応・アレルギー・ギフト包装等） |
| PUT | `/api/orders/{order_id}/status?tenant_id=T-001` | 受注ステータス更新（要対応→受注済み等。完了/キャンセル状態への戻し以外を許可） |
| PUT | `/api/customers/{customer_id}?tenant_id=T-001` | 顧客更新（LINE User ID紐付け・納品グループ等） |
| GET | `/api/agent/features` | Dashboard Agent 機能フラグ（dashboard_agent/exception_triage/resolution_agent/resolution_execute/demo_mode） |
| GET | `/api/agent/exceptions?delivery_date=YYYY-MM-DD&status=要対応&limit=50&offset=0` | 受注一覧の表示条件に合わせた Exception Case 一覧（Z-score 数量異常・単位異常・在庫不足・要対応）。日付未指定時は現在ページ範囲を対象 |
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
| `docs/line-conversation-memory.md` | LINE会話のセッション管理・注文コンテキスト設計 |
| `docs/dashboard-agent-design.md` | Dashboard Agent（Exception Triage / Resolution）の設計 |
| `docs/email-channel-design.md` | メールチャネルの設計（Graph API Webhook・テンプレート・SMTP フォールバック） |
| `docs/auth-setup.md` | 認証設計（JWT・Microsoft SSO・Cookie・セルフ登録） |
| `docs/deployment-split.md` | デプロイ構成分離（API / Frontend） |
| `docs/debug-log-guide.md` | LINE Tester のデバッグログ表示機能 |
| `docs/phone-testing.md` | 電話チャネルのテスト手順 |
| `docs/security.md` | セキュリティ設計・Key Vault・認証フロー |
| `docs/agent-behavior-testing.md` | Agent 動作テスト手順 |
| `docs/visual-flows.md` | ビジュアルフロー図 |
| `docs/line_QC.md` | LINE QC テスト結果・テストケース定義 |

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
- 配信先: Azure Storage Static Website ルート
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
│   ├── endpoints.py              # /api/auth/* エンドポイント（login, register, microsoft, me）
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
│   │   ├── search_product_master.py       # Azure AI Search → products（あいまい + ベクトル検索）
│   │   ├── sql_customer_repository.py     # Azure SQL → customers
│   │   ├── sql_inventory_service.py       # Azure SQL → inventory
│   │   ├── _sql_util.py                   # SQL接続ユーティリティ
│   │   └── registry.py                    # 全Adapterの登録
│   ├── factory.py                # ConnectorFactory（テナント設定→Adapter解決）
│   └── context.py                # TenantContext（テナント単位の依存注入コンテナ）
├── services/
│   ├── line_handler.py           # LINE Webhook処理（署名検証・セッション管理・未登録顧客自動作成）
│   ├── phone_handler.py          # 電話 Webhook処理（ACS Call Automation、同期AI在庫確認、非同期正式検証）
│   ├── email_handler.py          # Email Webhook処理（正規化・セッション管理・未登録顧客自動作成）
│   ├── channel_locks.py          # チャネル×ユーザー単位の非同期ロック
│   ├── line_template_renderer.py # LINE返信テンプレート描画
│   ├── learning_service.py       # パターン記録・顧客プロファイル更新
│   ├── intent_understanding.py   # 注文会話の Intent 分類（明確ルール + LLM fallback）
│   ├── order_application.py      # 注文状態変更の業務サービス
│   ├── inventory_application.py  # 注文ドラフト単位の在庫確認業務サービス
│   ├── order_memory.py           # 「いつもの」・過去注文参照のドラフト復元
│   ├── dashboard_agent.py        # Dashboard Agent サービス（Exception Triage / Resolution プレビュー）
│   ├── dashboard_events.py       # SSE イベント管理（受注更新のリアルタイム配信）
│   ├── delivery_estimator.py     # 配送予定日の自動推定（リードタイム・締め時間・休日考慮）
│   ├── speech_service.py         # Azure Speech SDK トークン発行
│   ├── order_status_updater.py   # 受注ステータス更新サービス
│   ├── message_history_logger.py # 会話メッセージ履歴の共通保存（LINE/電話/メール）
│   └── tenant_resolver.py        # テナント解決（LINE/電話→テナント紐付け）
├── models/                       # Pydantic データモデル
│   ├── order.py                  # Order, OrderItem, OrderStatus, OrderSource, etc.
│   ├── customer.py               # Customer, CustomerDeliveryPreference
│   ├── product.py                # Product, UnitType
│   ├── picking.py                # PickingList, PickingItem
│   ├── intelligence.py           # OrderPattern, CustomerOrderProfile, ProductStats
│   ├── inbound.py                # InboundMessage（チャネル共通の受信メッセージ）
│   ├── message_history.py        # MessageHistory（会話メッセージ履歴）
│   ├── session.py                # OrderSession
│   └── tenant.py                 # TenantConfig, ConnectorConfig
├── utils/
│   └── business_date.py          # JST業務日計算ユーティリティ
frontend/                         # React/Vite ダッシュボード
├── src/                           # 画面・認証・APIクライアント
├── package.json                   # npm scripts
└── vite.config.ts                 # Vite base・dev proxy

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
| `customers` | 11 | 顧客マスタ（LINE User ID紐付け・納品グループ `delivery_lead_time` 対応。LINE/メール未登録ユーザーは自動作成） |
| `products` | 19 | 商品マスタ（温度帯・不定貫フラグ付き） |
| `product_aliases` | 0 | 商品名エイリアス（表記ゆれ対応） |
| `inventory` | 19 | 在庫（quantity - reserved_qty = 有効在庫） |
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
| `orders` | `message-history` | `/id` | 会話メッセージ履歴（LINE/電話/メール） |
| `intelligence` | `customer-profiles` | `/customer_id` | 顧客発注プロファイル |
