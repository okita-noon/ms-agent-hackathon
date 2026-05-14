# AGENTS.md

> すべてのAIエージェント（Claude Code, GitHub Copilot, Cursor等）が参照するプロジェクトルール。

## プロジェクト概要

- **プロジェクト名**: AI受発注自動一元管理システム
- **チーム**: ASKNOI_AI木曜会
- **ハッカソン**: Microsoft Agent Hackathon 2026
- **提出締切**: 2026-06-01
- **審査期間**: 2026-06-02 ~ 2026-06-18（デプロイ維持必須）
- **言語**: Python（バックエンド）、TypeScript（フロントエンド）

## システム概要

食品卸・食材メーカー向けのマルチテナント対応 AI Agent SaaS。
電話・LINE・メールからの注文を複数の専門AI Agentが協調して自動処理する。

**6層構成**: 受注チャネル → 受信処理 → マルチエージェント処理 → Connector層 → データ層 → 出力・UI層

## 技術スタック

| カテゴリ | 技術 |
|---|---|
| Agent基盤 | Azure AI Agent Service |
| LLM/Embedding | Azure AI Foundry（GPT-4o, text-embedding-3-small） |
| オーケストレーション | Semantic Kernel（Python SDK） |
| ドキュメントDB | Azure Cosmos DB（受注・パターン学習・セッション） |
| リレーショナルDB | Azure SQL Database（マスタ・在庫） |
| 検索 | Azure AI Search（あいまいマッチング + ベクトル検索） |
| サーバーレス | Azure Functions（Webhook受信・イベント駆動） |
| アプリ実行 | Azure Container Apps（ダッシュボード・API） |
| 認証 | Microsoft Entra ID |
| 秘密管理 | Azure Key Vault |

## アーキテクチャドキュメント

実装前に必ず該当ドキュメントを読むこと。

| ファイル | 内容 |
|---|---|
| `docs/architecture-overview.md` | 全体俯瞰・レイヤー構成・Azureサービス一覧 |
| `docs/multi-agent-design.md` | Agent一覧・責務・フロー例・ツール定義・Learning Service |
| `docs/connector-design.md` | Connector層・テナント別差し替え・マルチテナント設計 |
| `docs/data-flow.md` | チャネル別データフロー・セッション管理・スケール戦略 |
| `docs/mvp-scope.md` | MVPスコープ・ユーザー体験シナリオ・非機能要件 |

## コーディング規約

### 全般
- Python 3.12+、型ヒント必須
- フォーマッタ: Ruff（`ruff format` + `ruff check`）
- テスト: pytest + pytest-asyncio
- 非同期: async/await を基本とする

### Semantic Kernel Plugin
- 各Agentのツールは `src/plugins/` に配置
- `@kernel_function` デコレータで定義
- テナントコンテキスト (`TenantContext`) を引数に受け取る
- DB/APIへの直接アクセスは禁止 → 必ず Connector Interface 経由

### Connector パターン
- インターフェースは `src/connectors/interfaces/` に定義
- アダプタ実装は `src/connectors/adapters/` に配置
- `ConnectorFactory` がテナント設定に基づいてランタイムで解決
- 新しいテナントのDB/API接続を追加する場合は、既存Interface実装のAdapterを追加する

### Azure Functions
- Learning Service は Azure Functions で実装（非Agent）
- Webhook受信（LINE, Graph API通知）も Azure Functions
- Cosmos DB Change Feed トリガーでイベント駆動

## セキュリティルール

- 秘密情報（APIキー・接続文字列）は `.env` で管理、絶対にコミットしない
- 本番では Azure Key Vault を使用
- pre-commit フックが `.githooks/` に設定済み（`git config core.hooksPath .githooks`）
- 詳細は `SECURITY.md` を参照

## ディレクトリ構成（計画）

```
src/
├── agents/           # Agent定義（Orchestrator, Intake, Inventory, Communication, Exception）
├── plugins/          # Semantic Kernel Plugin（IntakePlugin, InventoryPlugin, ExceptionPlugin）
├── connectors/
│   ├── interfaces/   # Protocol定義（IOrderRepository, IInventoryService等）
│   └── adapters/     # 実装（CosmosDB, SQL, ExternalAPI）
├── services/         # Learning Service等の非Agentサービス
├── functions/        # Azure Functions エントリポイント
├── models/           # データモデル（OrderPattern, CustomerOrderProfile等）
└── dashboard/        # フロントエンド（ダッシュボード）
docs/                 # 設計ドキュメント
```
