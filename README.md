# Microsoft Agent Hackathon 2026

**チーム:** AINOK_AI木曜会

食品卸・食材メーカーの受注現場を対象に、LINE・電話・メールなど複数チャネルの注文を AI Agent で受け付け、受注処理・在庫確認・確認質問・学習までを一気通貫で支援するプロジェクトです。

## 1. この README の役割

この README は、プロジェクトを再開するときの入口です。

- 何を作っているか
- どこに何があるか
- まず何を読めばよいか
- どう起動するか

を最初に把握できるようにしています。

進捗や残タスクは `STATUS.md`、詳細設計は `docs/` を参照してください。

## 2. まず読むもの

作業再開時は、まず以下の順で確認してください。

1. `CLAUDE.md` - AI 作業ルール
2. `AGENTS.md` - プロジェクト固有ルール・構成・API 一覧
3. `STATUS.md` - 現在の進捗と残タスク
4. 対象領域の `docs/` 配下設計書

関連ドキュメントの公開ページ:

- https://okita-noon.github.io/ms-agent-hackathon/

主要ドキュメント:

- `docs/architecture-overview.md` - 全体構成
- `docs/multi-agent-design.md` - マルチエージェント設計
- `docs/connector-design.md` - Connector 設計
- `docs/data-flow.md` - データフロー
- `docs/mvp-scope.md` - MVP / デモ対象範囲
- `docs/email-channel-design.md` - メール連携設計
- `docs/line-conversation-memory.md` - LINE 会話継続設計
- `docs/dashboard-agent-design.md` - ダッシュボード Agent 設計
- `docs/auth-setup.md` - 認証セットアップ
- `docs/deployment-split.md` - デプロイ分割設計

## 3. いまできること

- LINE webhook 経由で注文メッセージを受信（会話履歴を保持し文脈を維持）
- 電話チャネル（ACS Call Automation）の受信フローを処理
- 電話デモモード（実際の電話番号なしでテスト可能）
- 在庫問い合わせ（「りんごの在庫ある？」等のメッセージに直接回答）
- Semantic Kernel を使った注文解析、異常検知、在庫確認、返信生成
- 配送時間帯の指定（午前中、14時、夕方等の表現を解釈）
- ダッシュボード Agent（異常トリアージ・解決プレビュー）
- Cosmos DB / Azure SQL を使った受注・セッション・学習データ管理
- JWT 認証付き REST API（FastAPI）
- React + Vite ベースのダッシュボード（受注一覧・在庫管理・顧客管理）
- Azure Container Apps / ACR / GitHub Actions を使ったデプロイ
- Azure 予算アラート（コスト上限管理）

未実装や残課題は `STATUS.md` を参照してください。

## 4. システム構成の要点

- **API / Webhook**: FastAPI
- **Agent 実行**: Semantic Kernel
- **LLM**: Azure OpenAI
- **トランザクション / 参照データ**: Azure SQL Database
- **受注・セッション・学習データ**: Azure Cosmos DB
- **UI**: React + Vite
- **デプロイ先**: Azure Container Apps
- **CI/CD**: GitHub Actions

詳細は以下を参照してください。

- `docs/architecture-overview.md`
- `docs/multi-agent-design.md`
- `docs/connector-design.md`
- `docs/data-flow.md`

## 5. ディレクトリ構成・ファイル役割説明

再開時に迷わないよう、主要ディレクトリとファイルの役割を一覧で示します。

```text
ms-agent-hackathon/
├── docs/                                   # 設計書・業務整理・公開ドキュメント群
│   ├── architecture-overview.md            # 全体構成
│   ├── business-domain.md                  # 業務背景と前提
│   ├── connector-design.md                 # Connector / Adapter 設計
│   ├── data-flow.md                        # データフロー
│   ├── email-channel-design.md             # メール連携設計
│   ├── line-conversation-memory.md         # LINE 会話継続設計
│   ├── multi-agent-design.md               # Agent 役割分担と連携
│   ├── mvp-scope.md                        # デモ対象スコープ
│   ├── phone-testing.md                    # 電話チャネル検証メモ
│   ├── dashboard-agent-design.md           # ダッシュボード Agent 設計
│   ├── auth-setup.md                       # 認証セットアップ
│   ├── deployment-split.md                 # デプロイ分割設計
│   ├── agent-behavior-testing.md           # Agent 動作テスト
│   ├── security.md                         # セキュリティ補足
│   ├── visual-flows.md                     # 図解系ドキュメント
│   └── assets/                             # ドキュメント用画像・補助素材
├── src/                                    # バックエンド本体
│   ├── api/
│   │   ├── main.py                         # FastAPI エントリポイント
│   │   └── dashboard_agent.py              # ダッシュボード Agent API
│   ├── agents/
│   │   ├── definitions.py                  # Agent instructions 定義
│   │   └── orchestrator.py                 # Agent 統合実行フロー
│   ├── auth/                               # 認証まわり
│   ├── connectors/
│   │   ├── adapters/                       # Cosmos DB / SQL などの実装
│   │   ├── interfaces/                     # Protocol interface 定義
│   │   ├── context.py                      # TenantContext
│   │   └── factory.py                      # Connector 解決
│   ├── dashboard/                          # 旧ダッシュボード資産
│   ├── models/                             # Pydantic モデル群
│   ├── plugins/                            # Agent が呼ぶ業務機能
│   └── services/                           # LINE / 電話 / 学習などの処理
├── frontend/                               # React + Vite ベースの新ダッシュボード
│   ├── public/                             # 静的ファイル
│   ├── src/
│   │   ├── auth/                           # MSAL 連携
│   │   ├── components/                     # UI 部品
│   │   ├── lib/                            # API 呼び出し・定数・補助処理
│   │   └── pages/                          # 画面単位の実装
│   ├── package.json                        # frontend 依存と npm scripts
│   ├── vite.config.ts                      # Vite 設定
│   └── README.md                           # frontend 単体の補足
├── infra/                                  # Azure デプロイ定義
│   ├── modules/                            # Bicep モジュール
│   ├── seed/                               # シードデータ
│   ├── sql/                                # スキーマ初期化 SQL
│   ├── main.bicep                          # メインテンプレート
│   ├── main.bicepparam                     # デプロイパラメータ
│   └── deploy.sh                           # 補助スクリプト
├── tests/                                  # pytest ベースのテスト
│   ├── test_api.py                         # API テスト
│   ├── test_line_handler.py                # LINE フローのテスト
│   ├── test_orchestrator.py                # Agent 統合処理のテスト
│   ├── test_phone_handler.py               # 電話フローのテスト
│   ├── test_plugins.py                     # Plugin ロジックのテスト
│   └── test_tenant_resolver.py             # テナント解決のテスト
├── articles/                               # 記事草稿や発信用素材
├── images/                                 # 図版・画像
├── scripts/                                # 補助スクリプト
├── .env.example                            # ローカル環境変数の雛形
├── AGENTS.md                               # プロジェクト固有ルール・構成説明
├── CLAUDE.md                               # AI 作業ルール
├── CLAUDE.kio.md                           # 個人用メモ（.gitignore で除外）
├── STATUS.md                               # 進捗・残課題・既知の問題
├── README.md                               # このファイル
├── SECURITY.md                             # セキュリティルール
├── Dockerfile                              # API コンテナビルド定義
├── mkdocs.yml                              # ドキュメントサイト設定
├── pyproject.toml                          # pytest / ruff 設定
└── requirements.txt                        # Python 依存
```

## 6. 変更箇所の探し方

どこを触ればよいか迷ったときの目安です。

- API / Webhook を追加したい -> `src/api/`
- Agent の振る舞いを変えたい -> `src/agents/`, `src/plugins/`
- DB / 外部サービス接続を変えたい -> `src/connectors/`
- LINE / 電話など受信処理を変えたい -> `src/services/`
- モデルを追加したい -> `src/models/`
- ダッシュボードを変えたい -> `frontend/src/`
- Azure 構成を変えたい -> `infra/`
- 設計の前提を確認したい -> `docs/`

## 7. セットアップ

```bash
git clone <このリポジトリのURL>
cd ms-agent-hackathon
git config core.hooksPath .githooks
cp .env.example .env
```

`.env` に必要な値を設定してください。秘密情報はコミットしないでください。

セキュリティルールは必ず `SECURITY.md` を確認してください。

## 8. ローカル起動

### 8.1. API

```bash
pip install -r requirements.txt
uvicorn src.api.main:app --reload --port 8080
```

- Health check: `http://localhost:8080/api/health`
- Dashboard: `http://localhost:8080/dashboard`

### 8.2. Frontend

```bash
cd frontend
npm install
npm run dev
```

ビルド成果物がある場合、FastAPI は `frontend/dist` を優先して `/dashboard` に配信します。

## 9. テスト

```bash
pytest
```

補足:

- Connector のテストは interface ベースで書く
- Agent のテストはモック前提
- pre-commit フックは `.githooks` を使う

## 10. Azure セットアップの入口

Azure 利用が必要な場合の大まかな流れです。

1. Azure CLI を利用可能にする
2. Azure Portal にログインする
3. 必要なテナントへ参加する
4. `Microsoft Entra ID` からテナント ID を確認する
5. CLI ログイン後、利用できるか確認する

詳細な権限や現在の進捗はチーム内連絡に依存するため、都度確認してください。

## 11. デプロイと運用メモ

- `main` ブランチへの push で GitHub Actions が自動デプロイ
- 手動デプロイ時は Docker build -> ACR push -> Container Apps update
- 新しい環境変数を追加した場合、Container Apps 側にも設定が必要

## 12. セキュリティ

- `.env` や秘密情報はコミットしない
- API キー、接続文字列、シークレットは Key Vault または安全な方法で管理する
- 詳細は `SECURITY.md` と `docs/security.md` を参照する
