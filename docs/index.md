# foogent — AI受発注自動一元管理システム

> ASKNOI_AI木曜会 / Microsoft Agent Hackathon 2026

食品卸・食材メーカーの受注担当者が抱える「注文チャネルの分散・手動転記・集計負荷」を解消する
**マルチテナント対応 AI Agent SaaS**。

電話・LINE・メールから届く注文を **複数の専門 AI Agent が協調して** 自動で構造化・一覧化し、
在庫照合から受注確定・返信までを自動化します。

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [図解フロー](visual-flows.md) | アーキテクチャ・ペルソナ利用シナリオ・ソフトウェア処理フロー |
| [アーキテクチャ概要](architecture-overview.md) | システム全体の俯瞰・レイヤー構成・Azureサービス一覧 |
| [マルチエージェント設計](multi-agent-design.md) | Agent一覧・責務・フロー例・ツール定義・Learning Service |
| [Connector層・マルチテナント](connector-design.md) | Connector層・テナント別差し替え・マルチテナント設計 |
| [データフロー](data-flow.md) | チャネル別データフロー・セッション管理・スケール戦略 |
| [LINE会話履歴参照設計](line-conversation-memory.md) | LINEの直近会話履歴・確認待ちドラフトをAgentに渡す設計 |
| [メールチャネル設計](email-channel-design.md) | Microsoft Graph によるメール受信・返信・セッション管理・実装タスク |
| [デプロイ分割設計](deployment-split.md) | API・Frontend・Docsを分けたチーム開発向けCI/CD構成 |
| [MVPスコープ](mvp-scope.md) | MVPスコープ・ユーザー体験シナリオ・非機能要件 |
| [セキュリティ](security.md) | セキュリティガイド |

## 技術スタック

| カテゴリ | 技術 |
|---|---|
| Agent基盤 | Azure AI Agent Service |
| LLM/Embedding | Azure AI Foundry（gpt-5.4-mini, text-embedding-3-small） |
| オーケストレーション | Semantic Kernel（Python SDK） |
| ドキュメントDB | Azure Cosmos DB |
| リレーショナルDB | Azure SQL Database |
| 検索 | Azure AI Search |
| サーバーレス | Azure Functions |
| API実行 | Azure Container Apps |
| Frontend配信 | Azure Storage Static Website |
| 認証 | Microsoft Entra ID |
| 秘密管理 | Azure Key Vault |
