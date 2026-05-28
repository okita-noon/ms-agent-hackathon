# Microsoft Agent Hackathon 2026

**チーム:** AINOK_AI木曜会

食品卸・食材メーカーの受注現場を対象に、LINE・電話・メールなど複数チャネルの注文を AI Agent で受け付け、受注処理・在庫確認・確認質問・学習までを一気通貫で支援するプロジェクトです。

## 目次

- [1. この README の役割](#1-この-readme-の役割)
- [2. まず読むもの](#2-まず読むもの)
- [3. いまできること](#3-いまできること)
- [4. システム構成の要点](#4-システム構成の要点)
- [5. 発注側フロント — チャネルとエージェント構成](#5-発注側フロント--チャネルとエージェント構成)
- [6. ディレクトリ構成・ファイル役割説明](#6-ディレクトリ構成ファイル役割説明)
- [7. 変更箇所の探し方](#7-変更箇所の探し方)
- [8. セットアップ](#8-セットアップ)
- [9. ローカル起動](#9-ローカル起動)
- [10. テスト](#10-テスト)
- [11. デバッグ・運用補助スクリプト](#11-デバッグ運用補助スクリプト)
- [12. Azure セットアップの入口](#12-azure-セットアップの入口)
- [13. テナント設定（配送関連）](#13-テナント設定配送関連)
- [14. デプロイと運用メモ](#14-デプロイと運用メモ)
- [15. セキュリティ](#15-セキュリティ)

---

## 1. この README の役割

この README は、プロジェクトを再開するときの入口です。

- 何を作っているか
- どこに何があるか
- まず何を読めばよいか
- どう起動するか

を最初に把握できるようにしています。

進捗や残タスクは `STATUS.md`、詳細設計は `docs/` を参照してください。

[↑ 目次に戻る](#目次)

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
- `docs/line-order-branching.md` - LINE受発注の分岐・会話テンプレ・要件整理
- `docs/line_QC.md` - LINE QC テスト結果ログ
- `docs/dashboard-agent-design.md` - ダッシュボード Agent 設計
- `docs/auth-setup.md` - 認証セットアップ

[↑ 目次に戻る](#目次)

## 3. いまできること

### チャネル受信
- LINE webhook 経由で注文メッセージを受信（会話履歴を保持し文脈を維持）
- メールチャネル（Graph API Webhook）で注文メールを受信・AI処理・自動返信
- 電話チャネル（ACS Call Automation）の受信フローを処理
- 電話デモモード（実際の電話番号なしでテスト可能）
- Web電話デモページ（`/web-phone`）：ブラウザから音声発注のデモが可能

### 注文処理・Agent
- Semantic Kernel を使った注文解析（Intake）・異常検知（Exception）・在庫確認（Inventory）・返信生成（Communication）
- 単位の表記ゆれを自動正規化（「コ」→「個」、「キロ」→「kg」等、数字の直後のみ対象）
- 在庫問い合わせ（「メロンの在庫ある？」等のメッセージに直接回答・受注しない）
- 在庫引当：受注確定時に `reserved_qty` を増加
- 在庫引当解除：キャンセル時に `reserved_qty` を減算して在庫を戻す
- 配送日・時間帯の指定（「明後日の午前中」等の表現を正しく解釈）
- 配送予定日の自動確定（顧客リードタイム・締め時間・定休日を考慮）
- 誤発注検知（Z-score > 3.0 で確認質問を返す）
- 在庫不足時の代替数量提案（「6個しかありませんが6個でよろしいですか？」）
- 確認質問への回答で受注確定するフロー（数量回答・「はい」肯定返答）
- 注文の変更・キャンセル・一部キャンセル（文脈保持）
- 「いつもの」「前と同じ」による発注パターン学習・復元

### ダッシュボード
- React + Vite ベースのダッシュボード（受注一覧・在庫管理・顧客管理）
- JWT認証（ID/パスワード + Microsoft SSO）
- 受注一覧のSSEライブ更新（新着行ハイライト付き）
- 受注詳細モーダル（会話履歴チャット・メモ編集）
- Dashboard Agent サイドパネル（異常トリアージ・解決プレビュー）
- LINE Tester（`/line-tester`）：ブラウザ上でLINEチャネルと同じ処理パスを実行・デバッグログ表示

### その他
- メール返信はビジネスメール形式で整形（受注Noを本文・件名に付与）
- 休眠顧客への販促営業メッセージ自動送信（テンプレート × 変数でLINE・メール両チャネル対応）
- Azure 予算アラート（コスト上限管理）

未実装や残課題は `STATUS.md` を参照してください。

[↑ 目次に戻る](#目次)

## 4. システム構成の要点

| カテゴリ | 技術 |
|----------|------|
| API / Webhook | FastAPI |
| Agent 実行 | Semantic Kernel 1.28 |
| LLM | Azure OpenAI（gpt-5.4-mini） |
| トランザクション / 参照データ | Azure SQL Database |
| 受注・セッション・学習データ | Azure Cosmos DB |
| 検索・あいまいマッチング | Azure AI Search |
| UI | React + Vite |
| デプロイ先 | Azure Container Apps |
| CI/CD | GitHub Actions |
| 認証 | Microsoft Entra ID |
| 秘密管理 | Azure Key Vault |

詳細は `docs/architecture-overview.md` を参照してください。

[↑ 目次に戻る](#目次)

## 5. 発注側フロント — チャネルとエージェント構成

食品卸の受注処理は **発注側フロント**（顧客と直接やり取りする面）と **受注側ダッシュボード**（社内担当者が管理する面）に分かれます。

### 全体構成図

```
┌─────────────────────────────────────────────────────────┐
│                    発注側フロント                          │
│                                                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                 │
│  │  LINE    │  │  メール  │  │  電話    │  ← チャネル     │
│  └────┬────┘  └────┬────┘  └────┬────┘                 │
│       │            │            │                       │
│       └────────────┼────────────┘                       │
│                    ▼                                    │
│          ┌─────────────────┐                            │
│          │  Orchestrator   │  ← 統括・振り分け           │
│          └────────┬────────┘                            │
│                   │                                     │
│     ┌─────────────┼─────────────┐                       │
│     ▼             ▼             ▼                       │
│  ┌────────┐ ┌───────────┐ ┌───────────┐                │
│  │ Intake │ │ Exception │ │ Inventory │  ← 処理Agent    │
│  │ Agent  │ │   Agent   │ │   Agent   │                │
│  └────┬───┘ └─────┬─────┘ └─────┬─────┘                │
│       └───────────┼─────────────┘                       │
│                   ▼                                     │
│        ┌──────────────────┐                             │
│        │ Communication    │  ← 返信生成Agent             │
│        │     Agent        │                             │
│        └────────┬─────────┘                             │
│                 │                                       │
│    ┌────────────┼────────────┐                          │
│    ▼            ▼            ▼                          │
│ ┌────────┐ ┌────────┐ ┌──────────┐                     │
│ │ナレッジ│ │テンプレ │ │返信送信  │                     │
│ │_knowledge│ │_templates│ │LINE/Mail│                   │
│ └────────┘ └────────┘ └──────────┘                     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│               受注側ダッシュボード                        │
│  ┌──────────────────────────────────────┐               │
│  │  React + Vite（受注一覧・在庫・顧客） │               │
│  └──────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────┘
```

### エージェントの役割

| Agent | 役割 | 入力 | 出力 |
|-------|------|------|------|
| **Orchestrator** | 全体統括。意図分類→各Agentへの委任→最終返信の組み立て | 顧客メッセージ + 会話履歴 | 顧客への返信テキスト |
| **Intake Agent** | 注文内容の構造化。顧客特定・商品正規化・パターン照合 | 自然言語メッセージ | 注文ドラフト（JSON） |
| **Exception Agent** | 異常検知。数量・単位の妥当性チェック、確認質問の生成 | 注文ドラフト | 異常レポート + 確認文 |
| **Inventory Agent** | 在庫照合・引当。不足時は代替品提案 | 注文ドラフト | 在庫確保結果 |
| **Communication Agent** | 返信メッセージの生成。チャネル別の口調・書式に対応 | 処理結果一式 | 返信テキスト |

### チャネル別の対応状況

| チャネル | ナレッジ | テンプレート | 備考 |
|----------|---------|------------|------|
| LINE | `_knowledge/line/` (5ファイル) | `_templates/line/` (12テンプレート) | フル対応 |
| メール | `_knowledge/email/` (2ファイル) | `_templates/メール*.txt` | Communication のみ専用 |
| 電話 | LINE と共有 | — | Phone Order Agent が別途処理 |

[↑ 目次に戻る](#目次)

## 6. ディレクトリ構成・ファイル役割説明

```text
ms-agent-hackathon/
├── docs/                                   # 設計書・業務整理・公開ドキュメント群
│   ├── architecture-overview.md            # 全体構成
│   ├── multi-agent-design.md               # Agent 役割分担と連携
│   ├── connector-design.md                 # Connector / Adapter 設計
│   ├── data-flow.md                        # データフロー
│   ├── line-order-branching.md             # LINE受発注の分岐・会話テンプレ・要件整理
│   ├── line_QC.md                          # LINE QC テスト実施ログ（自動テスト結果）
│   ├── mvp-scope.md                        # デモ対象スコープ
│   ├── dashboard-agent-design.md           # ダッシュボード Agent 設計
│   ├── auth-setup.md                       # 認証セットアップ
│   └── assets/                             # ドキュメント用画像・補助素材
├── src/                                    # バックエンド本体
│   ├── api/
│   │   ├── main.py                         # FastAPI エントリポイント（Webhook・REST API・LINE Tester）
│   │   └── dashboard_agent.py              # ダッシュボード Agent API
│   ├── agents/
│   │   ├── definitions.py                  # Agent instructions 定義・ナレッジ結合・単位正規化
│   │   └── orchestrator.py                 # Agent 統合実行フロー・在庫引当・配送日推定
│   ├── auth/                               # JWT認証（ID/PW + Microsoft SSO）
│   ├── connectors/
│   │   ├── adapters/                       # Cosmos DB / Azure SQL / AI Search 実装
│   │   ├── interfaces/                     # Protocol interface 定義（IInventoryService等）
│   │   ├── context.py                      # TenantContext（debug_log集約機能付き）
│   │   └── factory.py                      # Connector 解決
│   ├── models/                             # Pydantic モデル群
│   ├── plugins/                            # Agent が呼ぶ業務機能
│   │   ├── intake_plugin.py                # 顧客特定・商品正規化・単位正規化・パターン照合
│   │   ├── exception_plugin.py             # 数量異常・単位異常検知
│   │   ├── inventory_plugin.py             # 在庫確認・引当・引当解除
│   │   └── communication_plugin.py         # LINE/メール送信
│   └── services/                           # LINE / メール / 電話 / 学習 / 配送推定など
│       ├── order_application.py            # 注文キャンセル・在庫引当解除
│       ├── inventory_application.py        # 在庫確認業務サービス
│       ├── intent_understanding.py         # 意図分類サービス
│       └── order_memory.py                 # 注文パターン記憶サービス
├── frontend/                               # React + Vite ベースのダッシュボード
│   ├── src/
│   │   ├── components/                     # UI 部品（受注詳細・ExceptionModal等）
│   │   ├── lib/                            # API 呼び出し・定数
│   │   └── pages/                          # 画面単位（Orders・Inventory・Customers・WebPhone）
│   └── package.json
├── infra/                                  # Azure デプロイ定義
│   ├── sql/                                # スキーマ初期化・マイグレーション SQL
│   │   ├── init-schema.sql                 # 初期スキーマ（テナント・顧客・商品・在庫等）
│   │   ├── 002〜007-*.sql                  # マイグレーション（ユーザー追加・在庫リセット等）
│   │   └── ...
│   ├── main.bicep                          # メインテンプレート
│   └── deploy.sh                           # 補助スクリプト
├── tests/                                  # pytest ベースのテスト（323件）
├── _knowledge/                             # Agent 用業務ナレッジ（マニュアル）
│   ├── line/                               # LINE チャネル用（5ファイル）
│   └── email/                              # メールチャネル用（2ファイル）
├── _templates/                             # メッセージテンプレート・設定ファイル
│   ├── line/                               # LINE返信テンプレート（12テンプレート）
│   ├── メール設定.json                     # メール件名ルール・署名情報
│   ├── メール返信_受注確定.txt
│   ├── メール返信_異常時.txt
│   └── 販促営業_久しぶりの顧客用_*.txt
├── scripts/                                # 補助スクリプト
│   ├── seed_orders.py                      # 受注シードデータ投入
│   ├── seed_users.py                       # ユーザーシードデータ投入
│   ├── sync_products_to_search.py          # 商品マスタ → AI Search 同期
│   ├── fix_order_dates_jst.py              # 受注日付をJST基準に補正
│   ├── line_qc/                            # LINE Tester QC自動実行（デバッグ用）
│   │   ├── run.py                          # 14ケース自動テスト・docs/line_QC.md に結果追記
│   │   └── _logs/                          # テスト実行ログ（JSON形式）
│   └── add_stock/                          # 在庫補充スクリプト（デバッグ・デモ用）
│       └── run.py                          # Azure SQL の在庫をリセット・補充
├── .github/workflows/                      # CI/CD（test / deploy-api / deploy-frontend / docs）
├── .env.example                            # ローカル環境変数の雛形
├── AGENTS.md                               # プロジェクト固有ルール・API一覧・DB構成
├── STATUS.md                               # 進捗・残課題・既知の問題
├── Dockerfile                              # API コンテナビルド定義
├── pyproject.toml                          # pytest / ruff 設定
└── requirements.txt                        # Python 本番依存
```

[↑ 目次に戻る](#目次)

## 7. 変更箇所の探し方

| やりたいこと | 場所 |
|-------------|------|
| API / Webhook を追加したい | `src/api/` |
| Agent の振る舞いを変えたい | `src/agents/definitions.py`, `src/plugins/` |
| Agent の業務ルール・判断基準を変えたい | `_knowledge/` |
| LINE / 電話など受信処理を変えたい | `src/services/` |
| DB / 外部サービス接続を変えたい | `src/connectors/` |
| ダッシュボードを変えたい | `frontend/src/` |
| Azure 構成を変えたい | `infra/` |
| 返信文面・テンプレートを変えたい | `_templates/` |
| 在庫の引当・引当解除ロジックを変えたい | `src/agents/orchestrator.py`, `src/services/order_application.py` |
| 在庫をリセット・補充したい | `scripts/add_stock/run.py` |
| LINE QC テストを実行したい | `scripts/line_qc/run.py` |

[↑ 目次に戻る](#目次)

## 8. セットアップ

```bash
git clone <このリポジトリのURL>
cd ms-agent-hackathon
python -m venv .venv
# Windows
.venv\Scripts\pip install -r requirements.txt
git config core.hooksPath .githooks
cp .env.example .env
```

`.env` に必要な値を設定してください。秘密情報はコミットしないでください。

[↑ 目次に戻る](#目次)

## 9. ローカル起動

### 9.1. API

```bash
uvicorn src.api.main:app --reload --port 8080
```

- Health check: `http://localhost:8080/api/health`
- LINE Tester: `http://localhost:8080/line-tester`（アクセスコード: `test`）

### 9.2. Frontend

```bash
cd frontend
npm install
npm run dev
```

[↑ 目次に戻る](#目次)

## 10. テスト

```bash
# Python テスト
.venv\Scripts\pytest

# LINE QC 自動テスト（14ケース）
.venv\Scripts\python scripts/line_qc/run.py --verbose
.venv\Scripts\python scripts/line_qc/run.py --cases 1,3,5  # 特定ケースのみ
```

[↑ 目次に戻る](#目次)

## 11. デバッグ・運用補助スクリプト

### 在庫補充 (`scripts/add_stock/run.py`)

テストやデモ後に在庫が減った場合にリセットするスクリプトです。

```bash
# デフォルト設定でリセット（りんご=0、スイカ/メロン/さくらんぼ=30、他=1000）
.venv\Scripts\python scripts/add_stock/run.py

# 全商品を500に
.venv\Scripts\python scripts/add_stock/run.py --qty 500

# 特定商品だけ指定
.venv\Scripts\python scripts/add_stock/run.py --product P-008 --qty 50

# dry-run（SQL確認のみ、実行しない）
.venv\Scripts\python scripts/add_stock/run.py --dry-run
```

### LINE QC テスト (`scripts/line_qc/run.py`)

LINE Tester API を使って14ケースを自動実行し、`docs/line_QC.md` に結果を追記します。

```bash
# 全14ケース実行
.venv\Scripts\python scripts/line_qc/run.py

# 特定ケースのみ・詳細ログあり
.venv\Scripts\python scripts/line_qc/run.py --cases 1,3,5 --verbose

# 別の顧客で実行
.venv\Scripts\python scripts/line_qc/run.py --customer C-003

# ローカルAPIに向ける
.venv\Scripts\python scripts/line_qc/run.py --base-url http://localhost:8080
```

[↑ 目次に戻る](#目次)

## 12. Azure セットアップの入口

1. `az login` でAzureにログイン
2. `az account set --subscription <サブスクリプションID>` でサブスクリプションを選択
3. デプロイ先: `rg-orderai-dev2`（Japan East）

詳細なリソース一覧・環境変数は `AGENTS.md` を参照してください。

[↑ 目次に戻る](#目次)

## 13. テナント設定（配送関連）

`TenantConfig`（`src/models/tenant.py`）で受注側の会社の配送設定を管理します。

| 設定項目 | フィールド名 | デフォルト値 | 説明 |
|----------|-------------|-------------|------|
| 締め時間 | `order_cutoff_hour` | `16`（16時） | この時刻以降の注文は翌営業日起算 |
| 定休日（曜日） | `closed_weekdays` | `[6]`（日曜） | 配送しない曜日。月=0〜日=6 |
| 臨時休業日 | `extra_holidays` | `[]` | YYYY-MM-DD 形式のリスト |
| 自動確定閾値 | `auto_confirm_threshold` | `0.9` | パターン照合の信頼度閾値 |

顧客ごとのリードタイムは `Customer.delivery_lead_time` で設定します（当日 / 翌日 / 中1日 / 中2日）。

[↑ 目次に戻る](#目次)

## 14. デプロイと運用メモ

- `main` ブランチへの push で GitHub Actions が自動デプロイ（API・Frontend・Docs）
- 手動デプロイ: `docker buildx build --platform linux/amd64` → ACR push → `az containerapp update`
- 新しい環境変数を追加した場合、Container Apps 側にも設定が必要
- デプロイが失敗した場合は `gh run rerun <run-id>` で再実行（Azure認証の一時的な障害の場合あり）

[↑ 目次に戻る](#目次)

## 15. セキュリティ

- `.env` や秘密情報はコミットしない
- API キー・接続文字列・シークレットは Key Vault で管理
- 詳細は `SECURITY.md` と `docs/security.md` を参照する

[↑ 目次に戻る](#目次)
