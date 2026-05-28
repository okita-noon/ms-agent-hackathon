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
- [11. Azure セットアップの入口](#11-azure-セットアップの入口)
- [12. テナント設定（配送関連）](#12-テナント設定配送関連)
- [13. デプロイと運用メモ](#13-デプロイと運用メモ)
- [14. セキュリティ](#14-セキュリティ)

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
- `docs/email-channel-design.md` - メール連携設計
- `docs/line-conversation-memory.md` - LINE 会話継続設計
- `docs/line-order-branching.md` - LINE受発注の分岐・会話テンプレ・要件整理
- `docs/dashboard-agent-design.md` - ダッシュボード Agent 設計
- `docs/auth-setup.md` - 認証セットアップ
- `docs/deployment-split.md` - デプロイ分割設計

[↑ 目次に戻る](#目次)

## 3. いまできること

- LINE webhook 経由で注文メッセージを受信（会話履歴を保持し文脈を維持）
- メールチャネル（Graph API Webhook）で注文メールを受信・AI処理・自動返信
- メール返信はビジネスメール形式で整形（テンプレート＋設定JSONで管理、受注Noを本文・件名に付与）
- 未登録メールアドレスのデモモード（`EMAIL_DEMO_MODE` + `EMAIL_DEMO_CUSTOMER_ID` で切替可能。フォールバック顧客名を正しく表示）
- 電話チャネル（ACS Call Automation）の受信フローを処理
- 電話デモモード（実際の電話番号なしでテスト可能）
- 在庫問い合わせ（「りんごの在庫ある？」等のメッセージに直接回答）
- Semantic Kernel を使った注文解析、異常検知、在庫確認、返信生成
- 配送時間帯の指定（午前中、14時、夕方等の表現を解釈）
- 配送予定日の自動確定（顧客リードタイム・締め時間・定休日を考慮し、確定日を受注確定メッセージに含める）
- ダッシュボード Agent（異常トリアージ・解決プレビュー）
- Cosmos DB / Azure SQL を使った受注・セッション・学習データ管理
- JWT 認証付き REST API（FastAPI）
- React + Vite ベースのダッシュボード（受注一覧・在庫管理・顧客管理）
- Azure Container Apps / ACR / GitHub Actions を使ったデプロイ
- 休眠顧客への販促営業メッセージ自動送信（テンプレート × 変数でLINE・メール両チャネル対応、dry_run可）
- Azure 予算アラート（コスト上限管理）

未実装や残課題は `STATUS.md` を参照してください。

[↑ 目次に戻る](#目次)

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

[↑ 目次に戻る](#目次)

## 5. 発注側フロント — チャネルとエージェント構成

食品卸の受注処理は **発注側フロント**（顧客と直接やり取りする面）と **受注側ダッシュボード**（社内担当者が管理する面）に分かれます。
この章では発注側フロントの構成を示します。

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
│ │_knowledge│ │_templates│ │LINE/Mail│                     │
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
| **Inventory Agent** | 在庫照合・引当。不足時は代替品提案や分納判断 | 注文ドラフト | 在庫確保結果 |
| **Communication Agent** | 返信メッセージの生成。チャネル別の口調・書式に対応 | 処理結果一式 | 返信テキスト |

### ナレッジとテンプレートの役割分担

| レイヤー | 場所 | 役割 | 例 |
|----------|------|------|-----|
| **ナレッジ**（脳） | `_knowledge/` | 判断ルール・分岐条件・一問一答 | 「白菜追加で」→ 追加注文と判断 |
| **テンプレート**（口） | `_templates/` | 返信の定型文・変数埋め込み | `承知しました。${items}を追加します` |

ナレッジはエージェント生成時に instructions へ結合されます（`definitions.py` の `_build_instructions()`）。
チャネル（LINE / メール）ごとに異なるナレッジを読み込むため、同じ Intake Agent でもチャネルに応じた判断ができます。

### チャネル別の対応状況

| チャネル | ナレッジ | テンプレート | 備考 |
|----------|---------|------------|------|
| LINE | `_knowledge/line/` (5ファイル) | `_templates/line/` (12テンプレート) | フル対応 |
| メール | `_knowledge/email/` (2ファイル) | `_templates/メール*.txt` | Communication のみ専用 |
| 電話 | LINE と共有 | — | Phone Order Agent が別途処理 |

[↑ 目次に戻る](#目次)

## 6. ディレクトリ構成・ファイル役割説明

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
│   ├── line-order-branching.md             # LINE受発注の分岐・会話テンプレ・要件整理
│   ├── multi-agent-design.md               # Agent 役割分担と連携
│   ├── mvp-scope.md                        # デモ対象スコープ
│   ├── phone-testing.md                    # 電話チャネル検証メモ
│   ├── dashboard-agent-design.md           # ダッシュボード Agent 設計
│   ├── auth-setup.md                       # 認証セットアップ
│   ├── deployment-split.md                 # デプロイ分割設計
│   ├── agent-behavior-testing.md           # Agent 動作テスト
│   ├── security.md                         # セキュリティ補足
│   ├── visual-flows.md                     # 図解系ドキュメント
│   ├── index.md                            # MkDocs トップページ
│   └── assets/                             # ドキュメント用画像・補助素材
├── src/                                    # バックエンド本体
│   ├── api/
│   │   ├── main.py                         # FastAPI エントリポイント
│   │   └── dashboard_agent.py              # ダッシュボード Agent API
│   ├── agents/
│   │   ├── definitions.py                  # Agent instructions 定義 + ナレッジ結合
│   │   └── orchestrator.py                 # Agent 統合実行フロー
│   ├── auth/                               # JWT認証（MSAL連携）
│   ├── connectors/
│   │   ├── adapters/                       # Cosmos DB / Azure SQL / AI Search 実装
│   │   ├── interfaces/                     # Protocol interface 定義
│   │   ├── context.py                      # TenantContext
│   │   └── factory.py                      # Connector 解決
│   ├── models/                             # Pydantic モデル群
│   ├── plugins/                            # Agent が呼ぶ業務機能（intake/exception/inventory/communication）
│   └── services/                           # LINE / メール / 電話 / 学習 / 配送推定などの処理
├── frontend/                               # React + Vite ベースのダッシュボード
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
│   ├── modules/                            # Bicep モジュール（Container Apps / Cosmos / SQL / AI Search 等）
│   ├── search/                             # AI Search インデックス定義
│   ├── seed/                               # シードデータ（Cosmos / CSV）
│   ├── sql/                                # スキーマ初期化・マイグレーション SQL
│   ├── main.bicep                          # メインテンプレート
│   ├── main.bicepparam                     # デプロイパラメータ
│   └── deploy.sh                           # 補助スクリプト
├── tests/                                  # pytest ベースのテスト
│   ├── conftest.py                         # 共通フィクスチャ
│   ├── test_api.py                         # API テスト
│   ├── test_auth.py                        # 認証テスト
│   ├── test_line_handler.py                # LINE フローのテスト
│   ├── test_email_handler.py               # メールフローのテスト
│   ├── test_phone_handler.py               # 電話フローのテスト
│   ├── test_orchestrator.py                # Agent 統合処理のテスト
│   ├── test_plugins.py                     # Plugin ロジックのテスト
│   ├── test_delivery_estimator.py          # 到着予定日推定のテスト
│   ├── test_dormant_customer_service.py    # 休眠顧客サービスのテスト
│   ├── test_dashboard_agent.py             # ダッシュボード Agent テスト
│   ├── test_cosmos_order_repository.py     # Cosmos 受注リポジトリのテスト
│   ├── test_learning_service.py            # 学習サービスのテスト
│   ├── test_message_history_logger.py      # 会話履歴ロガーのテスト
│   ├── test_models.py                      # モデルのテスト
│   ├── test_sql_util.py                    # SQL ユーティリティのテスト
│   ├── test_deploy_config.py              # デプロイ設定のテスト
│   └── test_tenant_resolver.py             # テナント解決のテスト
├── _knowledge/                             # Agent 用業務ナレッジ（マニュアル）
│   ├── line/                               # LINE チャネル用
│   │   ├── overview.md                     # 全エージェント共通の業務前提・フロー全体像
│   │   ├── intake_manual.md                # Intake Agent: 注文解析・顧客特定・商品正規化
│   │   ├── exception_manual.md             # Exception Agent: 確認質問・異常検知の判断基準
│   │   ├── inventory_manual.md             # Inventory Agent: 在庫照合・代替/分納の分岐
│   │   └── communication_manual.md         # Communication Agent: 返信生成・口調・テンプレ選択
│   └── email/                              # メールチャネル用
│       ├── overview.md                     # メール共通の業務前提
│       └── communication_manual.md         # メール返信の書式・口調
├── _templates/                             # メッセージテンプレート・設定ファイル
│   ├── line/                               # LINE返信テンプレート（12テンプレート + 設定JSON）
│   ├── メール設定.json                    # メール件名ルール・署名情報
│   ├── メール返信_受注確定.txt            # 受注確定メールの本文テンプレート
│   ├── メール返信_異常時.txt              # 異常時メールの本文テンプレート
│   └── 販促営業_久しぶりの顧客用_*.txt    # 休眠顧客向け営業メッセージ（3パターン）
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
├── articles/                               # 記事草稿や発信用素材
├── images/                                 # 図版・画像
├── .github/                                # GitHub 設定
│   ├── workflows/                          # CI/CD（test / deploy-api / deploy-frontend / docs）
│   └── pull_request_template.md            # PR テンプレート
├── .githooks/                              # Git フック（pre-commit）
├── .env.example                            # ローカル環境変数の雛形
├── AGENTS.md                               # プロジェクト固有ルール・構成説明
├── CLAUDE.md                               # AI 作業ルール
├── STATUS.md                               # 進捗・残課題・既知の問題
├── GIT_STATUS.md                           # Git 運用状況メモ
├── README.md                               # このファイル
├── SECURITY.md                             # セキュリティルール
├── Dockerfile                              # API コンテナビルド定義
├── mkdocs.yml                              # ドキュメントサイト設定
├── pyproject.toml                          # pytest / ruff 設定
├── requirements.txt                        # Python 本番依存
└── requirements-dev.txt                    # Python 開発依存
```

[↑ 目次に戻る](#目次)

## 7. 変更箇所の探し方

どこを触ればよいか迷ったときの目安です。

- API / Webhook を追加したい -> `src/api/`
- Agent の振る舞いを変えたい -> `src/agents/`, `src/plugins/`
- DB / 外部サービス接続を変えたい -> `src/connectors/`
- LINE / 電話など受信処理を変えたい -> `src/services/`
- モデルを追加したい -> `src/models/`
- ダッシュボードを変えたい -> `frontend/src/`
- Azure 構成を変えたい -> `infra/`
- 設計の前提を確認したい -> `docs/`
- 営業メッセージのテンプレートを変えたい -> `_templates/`
- Agent の判断ルール・返信品質を改善したい -> `_knowledge/`

### テンプレートとナレッジの関係

Agent の返信品質は **テンプレート** と **ナレッジ** の2層で管理しています。

```
_knowledge/（判断のルール = 脳みそ）
  「白菜も追加で」→ 現在注文への追加と判断 → B-02 の分岐へ
  「さっきのやつ減らして」→ 対象不明 → 確認質問へ
      │
      ▼  どう判断するか
_templates/（返信の型 = 口）
  order_add_confirm.txt → 「承知いたしました。現在のご注文に追加いたします。…」
  order_change_clarify.txt → 「確認です。${body}」
```

- **`_knowledge/`**: 各エージェントが「何をどう判断するか」の業務マニュアル。一問一答形式の具体例を多数含む
- **`_templates/`**: 判断結果に基づいて「何を返すか」の定型文。変数 `${}` で動的部分を埋める

テンプレートだけでは「いつどれを使うか」がわからず、ナレッジだけでは「どう言うか」がブレる。
両方揃って初めて安定した返信が出る仕組みです。

### ナレッジの構成

`_knowledge/` は **チャネル別 × エージェント別** にマニュアルを配置します。

```
_knowledge/
  line/
    overview.md              ← 全エージェント共通の業務前提
    intake_manual.md         ← Intake Agent 用
    exception_manual.md      ← Exception Agent 用
    inventory_manual.md      ← Inventory Agent 用
    communication_manual.md  ← Communication Agent 用
  email/
    overview.md              ← メール共通の業務前提
    communication_manual.md  ← メール返信用
```

各マニュアルには以下を含みます:

1. **このエージェントの責任範囲** — 何をやり、何をやらないか
2. **判断ルール** — 優先順位つきの分岐条件
3. **一問一答集** — 入力例 → 正しい判断 → 期待する出力、を多数列挙
4. **やってはいけないこと** — 典型的な誤判断パターン

`overview.md` には全エージェント共通の前提（1顧客1オープン注文、LINEでは受注Noを見せない等）を記載し、
各エージェントマニュアルの冒頭で「先に overview.md を読んでいること」を前提とします。

### テンプレートの管理

`_templates/` フォルダにメッセージテンプレート（`.txt`）と設定ファイル（`.json`）を配置しています。

#### メール返信テンプレート
- `メール返信_受注確定.txt` — 正常受注時の本文テンプレート
- `メール返信_異常時.txt` — 確認質問・異常警告時の本文テンプレート
- テンプレート内で使える変数: `${customer_name}`, `${company_name}`, `${order_items}`, `${delivery_estimate}`, `${body}`
- 署名はテンプレートに含めない（`メール設定.json` から自動付加）

#### LINE返信テンプレート
- `_templates/line/` に LINE の定型返信テンプレートを配置する
- LINE は受注Noを表示せず、現在注文への追加・変更・取消を会話文脈で扱う
- 受注確定 / 注文更新 / 全体キャンセル / 現在注文なし / ロック済み変更 などの文種ごとにテンプレートを分ける

#### メール設定
- `メール設定.json` — 署名情報（会社名・部署・TEL・Email）と件名ルール（受注No付与サフィックス等）を一元管理
- 受注確定時の件名例: `Re: 食材の注文 【受注No: ORD-20260524-001】`

#### 販促営業テンプレート
- ファイル名でテンプレートの用途がわかるようにする（例: `販促営業_久しぶりの顧客用_01.txt`）
- テンプレート内で使える変数: `${customer_name}`, `${product_name}`, `${product_origin}`, `${product_appeal}`
- パターンを増やしたい場合は同じ命名規則でファイルを追加するだけでOK（コード変更不要）

[↑ 目次に戻る](#目次)

## 8. セットアップ

```bash
git clone <このリポジトリのURL>
cd ms-agent-hackathon
git config core.hooksPath .githooks
cp .env.example .env
```

`.env` に必要な値を設定してください。秘密情報はコミットしないでください。

セキュリティルールは必ず `SECURITY.md` を確認してください。

[↑ 目次に戻る](#目次)

## 9. ローカル起動

### 9.1. API

```bash
pip install -r requirements.txt
uvicorn src.api.main:app --reload --port 8080
```

- Health check: `http://localhost:8080/api/health`
- Dashboard: `http://localhost:8080/dashboard`

### 9.2. Frontend

```bash
cd frontend
npm install
npm run dev
```

ビルド成果物がある場合、FastAPI は `frontend/dist` を優先して `/dashboard` に配信します。

[↑ 目次に戻る](#目次)

## 10. テスト

```bash
pytest
```

補足:

- Connector のテストは interface ベースで書く
- Agent のテストはモック前提
- pre-commit フックは `.githooks` を使う

[↑ 目次に戻る](#目次)

## 11. Azure セットアップの入口

Azure 利用が必要な場合の大まかな流れです。

1. Azure CLI を利用可能にする
2. Azure Portal にログインする
3. 必要なテナントへ参加する
4. `Microsoft Entra ID` からテナント ID を確認する
5. CLI ログイン後、利用できるか確認する

詳細な権限や現在の進捗はチーム内連絡に依存するため、都度確認してください。

[↑ 目次に戻る](#目次)

## 12. テナント設定（配送関連）

`TenantConfig`（`src/models/tenant.py`）で受注側の会社の配送設定を管理します。

| 設定項目 | フィールド名 | デフォルト値 | 説明 |
|----------|-------------|-------------|------|
| 締め時間 | `order_cutoff_hour` | `16`（16時） | この時刻以降の注文は翌営業日起算になる |
| 定休日（曜日） | `closed_weekdays` | `[6]`（日曜） | 配送しない曜日。月=0〜日=6 |
| 臨時休業日 | `extra_holidays` | `[]` | YYYY-MM-DD 形式のリスト（年末年始・GW等） |

顧客ごとのリードタイムは `Customer.delivery_lead_time` で設定します。

| リードタイム | 値 | 意味 |
|-------------|-----|------|
| 当日 | `SAME_DAY` | 締め時間前の注文 → 当日お届け |
| 翌日 | `NEXT_DAY` | 締め時間前の注文 → 翌営業日お届け |
| 中1日 | `ONE_DAY_GAP` | 締め時間前の注文 → 2営業日後お届け |
| 中2日 | `TWO_DAY_GAP` | 締め時間前の注文 → 3営業日後お届け |

顧客にリードタイムが未設定の場合は、配送ルート（地域）から日数を幅で推定します。

### 設定例

- 締め時間を15時に変更: `order_cutoff_hour=15`
- 水曜・日曜を定休日に: `closed_weekdays=[2, 6]`
- 年末年始を追加: `extra_holidays=["2026-12-31", "2027-01-01", "2027-01-02", "2027-01-03"]`

[↑ 目次に戻る](#目次)

## 13. デプロイと運用メモ

- `main` ブランチへの push で GitHub Actions が自動デプロイ
- 手動デプロイ時は Docker build -> ACR push -> Container Apps update
- 新しい環境変数を追加した場合、Container Apps 側にも設定が必要

[↑ 目次に戻る](#目次)

## 14. セキュリティ

- `.env` や秘密情報はコミットしない
- API キー、接続文字列、シークレットは Key Vault または安全な方法で管理する
- 詳細は `SECURITY.md` と `docs/security.md` を参照する

[↑ 目次に戻る](#目次)
