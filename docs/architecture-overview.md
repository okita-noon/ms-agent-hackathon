# アーキテクチャ概要

> 詳細設計は各ドキュメントを参照。本ファイルはシステム全体の俯瞰図。

## システム概要

食品卸・食材メーカーの受注担当者が抱える「注文チャネルの分散・手動転記・集計負荷」を解消する
**マルチテナント対応 AI Agent SaaS**。

LINE・FAX・ECサイト・電話・メールから届く注文を **複数の専門 AI Agent が協調して** 自動で構造化・一覧化し、
在庫照合から受注確定・ピッキングリスト生成・返信までを自動化する。

**SaaS設計方針**: 顧客（テナント）ごとにデータ層・外部連携を差し替え可能とし、
デモ環境の即時構築から、既存の顧客業務システム（ERP・在庫DB・受注API）への接続まで対応する。

## レイヤー構成

```
① 受注チャネル（入力層）
   【MVP】LINE(Webhook) / 電話(ACS Call Automation + AI Speech)
   【将来】FAX(OCR→テキスト化) / ECサイト(API) / メール(Graph API) / 手入力(ダッシュボード)

② 受信処理・セッション管理層
   Azure Container Apps（API/Webhook受信・テナント解決・セッション判定・Agent呼び出し）
   ※本番スケール時に Service Bus を挟む（docs/data-flow.md 7.5 参照）

③ マルチエージェント処理層
   Orchestrator / Intake / Inventory / Communication / Exception (Agent)
   + Learning Service (非Agent・Container Apps 内バックグラウンドタスク)
   → 詳細: docs/multi-agent-design.md

④ Connector層（テナント別差し替え可能）
   共通Interface → テナント設定で Adapter を動的解決
   → 詳細: docs/connector-design.md

⑤ データ層（テナント分離）
   Cosmos DB（受注・パターン学習・セッション） / Azure SQL（マスタ・在庫）
   Azure AI Search（商品/顧客あいまい検索 + パターンEmbeddingベクトル検索）

⑥ 出力・UI層
   ダッシュボード(Container Apps) / LINE自動返信 / 管理コンソール
```

## 使用 Azure サービス一覧

| レイヤー | サービス | 用途 |
|---|---|---|
| **受注チャネル** | | |
| 電話着信 | Azure Communication Services (Call Automation) | 電話着信の受付・音声ストリーム取得 |
| 音声文字起こし | Azure AI Speech | 音声ストリームのリアルタイムテキスト化 |
| LINE連携 | LINE Messaging API + Azure Container Apps | Webhook受信・返信 |
| メール受信 | Microsoft Graph API (Office 365) | メールボックス監視（Change Notifications） |
| メール送信 | Azure Communication Services | 受注確認・確認質問メールの送信 |
| **AI Agent** | | |
| Agent基盤 | Azure AI Agent Service | マルチAgent実行・Thread管理・会話セッション |
| LLM・Embedding | Azure AI Foundry | GPT-4o（意図判定・情報抽出・返信生成）、text-embedding-3-small（パターン類似検索） |
| オーケストレーション | Semantic Kernel | Plugin管理・Agent間連携 |
| 商品/顧客検索 | Azure AI Search | 商品名・顧客名のあいまいマッチング + パターンEmbeddingベクトル検索 |
| **データ層** | | |
| Platform DB | Azure SQL Database | テナント管理・設定・Connectorレジストリ |
| 受注データ | Azure Cosmos DB | 受注ドキュメント・処理ログ（テナント別） |
| 発注パターン学習 | Azure Cosmos DB | Order Intelligence Store（パターン・顧客プロファイル） |
| セッション管理 | Azure Cosmos DB | LINE/メール会話セッション（TTL付き自動失効） |
| マスタ/在庫 | Azure SQL Database | 商品・顧客・在庫マスタ（テナント別） |
| ファイル保管 | Azure Blob Storage | 音声/メール原本のバックアップ |
| **実行基盤** | | |
| アプリ実行 | Azure Container Apps | ダッシュボード・API・Webhook受信・イベント駆動処理 |
| コンテナレジストリ | Azure Container Registry | コンテナイメージ管理 |
| **セキュリティ** | | |
| 認証 | Microsoft Entra ID | SSO・テナント別権限管理 |
| 秘密管理 | Azure Key Vault | 接続文字列・APIキー管理 |
| オンプレ接続 | Azure Relay | 顧客既存システムとのハイブリッド接続 |

## DB使い分けの方針

- **Cosmos DB**: 受注ドキュメント・パターン学習・セッション（スキーマレス + TTL + Change Feed 向き）
- **Azure SQL**: マスタデータ・在庫（リレーショナル整合性・JOIN・トランザクション向き）

## ドキュメント構成

| ファイル | 内容 |
|---|---|
| `docs/architecture-overview.md` | 本ファイル。全体俯瞰 |
| `docs/multi-agent-design.md` | Agent一覧・責務・フロー例・ツール定義・Learning Service |
| `docs/connector-design.md` | Connector層・テナント別差し替え・マルチテナント設計 |
| `docs/data-flow.md` | チャネル別データフロー・セッション管理・スケール戦略 |
| `docs/mvp-scope.md` | MVPスコープ・ユーザー体験シナリオ・非機能要件 |
