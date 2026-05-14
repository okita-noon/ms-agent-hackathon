# システム構成書：AI受発注自動一元管理システム

> ASKNOI_AI木曜会 / Microsoft Agent Hackathon 2026

---

## 1. システム概要

食品卸・食材メーカーの受注担当者が抱える「注文チャネルの分散・手動転記・集計負荷」を解消する
**マルチテナント対応 AI Agent SaaS**。

電話・LINE・メールから届く注文を **複数の専門 AI Agent が協調して** 自動で構造化・一覧化し、
在庫照合から受注確定・返信までを自動化する。

**SaaS設計方針**: 顧客（テナント）ごとにデータ層・外部連携を差し替え可能とし、
デモ環境の即時構築から、既存の顧客業務システム（ERP・在庫DB・受注API）への接続まで対応する。

---

## 2. アーキテクチャ全体図

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         ① 受注チャネル（入力層）                                │
│                                                                                 │
│   📞 電話（音声）            💬 LINE                     📧 メール              │
│   ↓                          ↓                           ↓                     │
│   ACS Call Automation        LINE Messaging API           Microsoft Graph API   │
│   + Azure AI Speech          （Webhook受信）               (Office 365メール監視)│
│   （着信受付→音声文字起こし）                                                    │
│                                                                                 │
│                                                                                 │
│   ※ メール受信: Microsoft Graph API でメールボックスを監視（Change Notifications）│
│   ※ メール返信: Azure Communication Services で送信                               │
│   ※ 将来チャネル追加: FAX(OCR), Webフォーム, EDI 等はここに追加するだけ          │
└────────────────────────────────┬────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      ② 受信処理・セッション管理層                                │
│                                                                                 │
│   Azure Functions（各チャネルの Webhook / イベントを直接受信）                    │
│   ┌──────────────────────────────────────────────────────────────────────────┐  │
│   │ 1. テナントID解決（チャネル識別子 → テナント紐付け）                     │  │
│   │ 2. セッション判定（既存会話の継続 or 新規注文の開始）                    │  │
│   │ 3. Agent呼び出し（Orchestrator Agent を同期実行）                        │  │
│   └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│   ※ 本番スケール時: Service Bus (テナント別トピック) を間に挟み負荷分離・       │
│     デッドレター・バッファリングを追加する（7.5 参照）                           │
└────────────────────────────────┬────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      ③ マルチエージェント処理層                                  │
│                         Azure AI Agent Service + Semantic Kernel                 │
│                                                                                 │
│ ┌─────────────────────────────────────────────────────────────────────────────┐ │
│ │                     🎯 Orchestrator Agent（指揮官）                         │ │
│ │                     Azure AI Agent Service + Azure AI Foundry (GPT-4o)                         │ │
│ │                                                                             │ │
│ │  役割: メッセージの意図を判断し、必要なAgentを選択・実行順序を決定          │ │
│ │  機能: ・注文 / 変更 / キャンセル / 問い合わせの意図分類                    │ │
│ │        ・Agent間のデータ受け渡し制御                                        │ │
│ │        ・全体の処理結果をまとめて最終アクションを決定                       │ │
│ │        ・推論過程をログに記録（透明性確保）                                 │ │
│ └──────┬──────────┬─────────────┬──────────────┬─────────────────────────────┘ │
│        │          │             │              │                                │
│        ▼          ▼             ▼              ▼                                │
│ ┌────────────┐┌─────────────┐┌──────────────┐┌──────────────┐               │
│ │📋 Intake   ││📦 Inventory ││💬 Comms      ││⚠️ Exception  │               │
│ │ Agent      ││ Agent       ││ Agent        ││ Agent        │               │
│ │            ││             ││              ││              │               │
│ │・自然言語→ ││・在庫照合   ││・返信文生成  ││・曖昧注文の  │               │
│ │  構造化    ││・欠品検出   ││・チャネル別  ││  確認質問生成│               │
│ │・顧客特定  ││・代替品提案 ││  フォーマット││・異常数量    │               │
│ │  (AI Search)│・需要予測   ││・Human-in-   ││  検知        │               │
│ │・商品名正規││  (過去傾向) ││  the-Loop    ││・エスカレー  │               │
│ │  化        ││             ││  判定        ││  ション判定  │               │
│ │・過去パター││             ││              ││・誤発注防止  │               │
│ │  ンで自動解││             ││              ││              │               │
│ │  釈        ││             ││              ││              │               │
│ └────────────┘└─────────────┘└──────────────┘└──────────────┘               │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐       │
│  │ 🧠 Learning Service（非Agent・Azure Functions で実装）              │       │
│  │                                                                     │       │
│  │ 注文確定時に非同期で起動。LLM推論は不要なため Agent ではなく        │       │
│  │ 通常のサービス関数として実装し、コスト・レイテンシを削減する。       │       │
│  │                                                                     │       │
│  │ ・確定注文から発注パターン(OrderPattern)を記録・confidence更新       │       │
│  │ ・顧客プロファイル(CustomerOrderProfile)の統計値を再計算            │       │
│  │ ・入力表現のEmbedding生成（Azure AI Foundry Embedding API）             │       │
│  └─────────────────────────────────────────────────────────────────────┘       │
│                                                                                 │
│  ※ 各Agent は Semantic Kernel Plugin として実装                                 │
│  ※ テナントごとに Agent の挙動・プロンプト・ツールセットをカスタマイズ可能       │
│  ※ Learning Service が蓄積したパターンを Intake / Exception Agent が参照         │
└────────────────────────────────┬────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      ④ Connector 層（テナント別差し替え可能）                    │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                    Connector Interface（共通抽象層）                     │   │
│   │                                                                         │   │
│   │  IOrderRepository      IInventoryService      IProductMaster            │   │
│   │  ICustomerRepository   IOrderIntelligenceStore                         │   │
│   └────┬──────────────────────┬───────────────────────┬─────────────────────┘   │
│        │                      │                       │                         │
│   ┌────▼────────────┐   ┌────▼────────────┐   ┌─────▼───────────┐             │
│   │ Default Adapter │   │ Customer A      │   │ Customer B      │             │
│   │ (デモ/新規向け) │   │ Adapter         │   │ Adapter         │             │
│   │                 │   │                 │   │                 │             │
│   │ ・Cosmos DB     │   │ ・既存SQL Server│   │ ・REST API連携  │             │
│   │ ・Azure SQL     │   │ ・既存ERP API   │   │ ・CSVバッチ連携 │             │
│   │ ・Blob Storage  │   │ ・社内在庫API   │   │ ・独自DB        │             │
│   └─────────────────┘   └─────────────────┘   └─────────────────┘             │
│                                                                                 │
│   ※ テナント設定（Tenant Config）で接続先を切り替え                              │
│   ※ 新規顧客: Default Adapter → 即日利用可能                                    │
│   ※ 既存システムあり: Custom Adapter を実装して接続                               │
└────────────────────────────────┬────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      ⑤ データ層（テナント分離）                                  │
│                                                                                 │
│   ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐ │
│   │ Platform DB          │  │ Tenant Data Store    │  │ File Storage         │ │
│   │ (SaaS共通)           │  │ (テナント別)          │  │ (テナント別)          │ │
│   │                      │  │                      │  │                      │ │
│   │ ・テナント管理       │  │ デフォルト構成:      │  │ Azure Blob Storage   │ │
│   │ ・テナント設定       │  │ ・Azure Cosmos DB    │  │ ・元メール保管       │ │
│   │ ・Agent設定          │  │   (受注ドキュメント) │  │ ・音声ファイル保管   │ │
│   │ ・課金・利用量       │  │ ・Azure Cosmos DB    │  │ ・添付ファイル保管   │ │
│   │ ・Connectorレジストリ│  │   (Order Intel Store)│  │                      │ │
│   │ ・信頼度閾値設定     │  │ ・Azure SQL Database │  │                      │ │
│   │                      │  │   (マスタ・在庫)     │  │                      │ │
│   │                      │  │                      │  │                      │ │
│   │ Azure SQL Database   │  │ ※顧客DB直接接続の   │  │ ※コンテナ名で       │ │
│   │                      │  │  場合はバイパス      │  │  テナント分離        │ │
│   └──────────────────────┘  └──────────────────────┘  └──────────────────────┘ │
│                                                                                 │
│   Azure AI Search（共通）── 商品名・顧客名のあいまいマッチング（テナント別Index）│
└────────────────────────────────┬────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      ⑥ 出力・UI層                                               │
│                                                                                 │
│   受注担当者ダッシュボード（Azure Container Apps）                                │
│   ・受注一覧（チャネル・ステータス・顧客・品目で絞り込み）                        │
│   ・確認待ち一覧（ワンタップで「確定／保留／修正」）                              │
│   ・Agent推論ログ閲覧（なぜその判断をしたか確認可能）                             │
│   ・ピッキングリスト自動生成・PDF出力                                             │
│   ・日別・顧客別・商品別ダッシュボード                                            │
│                                                                                 │
│   自動返信                                                                       │
│   ・LINE → LINE Messaging API で受注確認 / 確認質問メッセージ返信                │
│   ・メール → Azure Communication Services でメール返信                           │
│   ・電話 → SMS または担当者通知                                                  │
│                                                                                 │
│   管理者コンソール（テナント管理・Connector設定・Agent設定）                       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. マルチエージェント設計（詳細）

### 3.1 Agent 一覧と責務

| Agent | 責務 | 使用ツール（Semantic Kernel Plugin） | 判断の例 |
|---|---|---|---|
| **Orchestrator** | 意図分類・実行計画・Agent間調整 | `classify_intent`, `plan_execution`, `aggregate_results` | 「これは注文だ。Intake→Inventory→Commsの順で処理」 |
| **Intake** | 自然言語→構造化データ変換 | `parse_order`, `lookup_customer`, `normalize_product`, `validate_order_draft`, `resolve_with_pattern` | 「"ツナ缶100g"→過去パターンで"ツナ缶1個"と自動解釈」 |
| **Inventory** | 在庫照合・欠品対応 | `check_inventory`, `find_alternatives`, `predict_demand` | 「在庫残10kg, 要求20kg→代替品キュウリ在庫あり」 |
| **Communication** | チャネル別返信生成・送信 | `generate_reply`, `send_line`, `send_email`, `send_sms` | 「LINEで来たからLINEで返す。丁寧語で」 |
| **Exception** | 曖昧・矛盾・異常の処理 | `ask_clarification`, `detect_quantity_anomaly`, `detect_unit_anomaly`, `escalate_to_human` | 「普段10個→今回100個。誤発注の可能性を確認」 |

**Learning Service（非Agent）**

| コンポーネント | 責務 | 関数 | 備考 |
|---|---|---|---|
| **Learning Service** | 発注パターン学習・統計更新 | `record_pattern`, `update_pattern_confidence`, `build_customer_profile`, `generate_expression_embedding` | Azure Functions で実装。注文確定イベントで非同期起動。LLM推論不要のためAgentにしない（コスト・速度の最適化） |

### 3.2 Agent 間フロー（具体例）

#### 例A: 初回注文 ── 曖昧表現の確認 → パターン学習

```
飲食店C-042店長「ツナ缶100g」(LINE) ← 初めてこの表現で注文

Orchestrator:
  ├─ 意図判断: "注文"
  ├─ 実行計画: Intake → Exception(検証) → Inventory → Communication → Learning
  │
  ├→ Intake Agent:
  │    ├─ lookup_customer("LINE ID: U1234...") → 顧客ID: C-042 (居酒屋○○)
  │    ├─ normalize_product("ツナ缶") → 商品ID: P-201 (ツナ缶 1個=70g)
  │    ├─ resolve_with_pattern(C-042, "ツナ缶100g")
  │    │    → パターンDB照会 → 該当パターンなし（初回）
  │    ├─ parse_order → { product: P-201, qty: 100, unit: "g", date: "本日" }
  │    └─ validate → 商品の標準単位(個)と注文単位(g)が不一致 → 要確認
  │
  ├→ Exception Agent:
  │    ├─ detect_unit_anomaly → 「ツナ缶は"個"単位。100gは1.4個相当。確認が必要」
  │    └─ ask_clarification → 「ツナ缶を100gとのことですが、1個(70g)でよろしいですか？
  │                             それとも2個(140g)ご希望ですか？」
  │
  ├→ Communication Agent:
  │    └─ send_line(C-042, 確認メッセージ)
  │
  │   ─── 店長返信: 「1個で！」 ───
  │
  ├→ Intake Agent（会話継続 = Agent Service Thread）:
  │    └─ 注文確定: { product: P-201, qty: 1, unit: "個" }
  │
  ├→ Inventory Agent → 在庫OK → Communication Agent → 受注確定返信
  │
  └→ Learning Service（確定後に非同期実行）:
       ├─ record_pattern:
       │    {
       │      customer: "C-042",
       │      input_expression: "ツナ缶100g",
       │      resolved_product: "P-201 (ツナ缶)",
       │      resolved_qty: 1,
       │      resolved_unit: "個",
       │      confidence: 0.7,     ← 初回は低め
       │      source: "customer_confirmed"
       │    }
       └─ → Order Intelligence Store に保存
```

#### 例B: 2回目注文 ── 学習済みパターンで自動解釈

```
同じC-042店長「ツナ缶100g、あとトマト多めで」(LINE) ← 2回目

Orchestrator → Intake Agent:
  │
  ├─ resolve_with_pattern(C-042, "ツナ缶100g")
  │    → パターンDB照会 → HIT! confidence: 0.7
  │    → 「ツナ缶100g → ツナ缶1個」と自動解釈
  │    → ただし confidence < 0.9 なので確認付きで処理
  │
  ├─ resolve_with_pattern(C-042, "トマト多め")
  │    → パターンDB照会 → HIT! 過去3回の平均: 15kg, confidence: 0.85
  │    → 「トマト多め → 完熟トマト15kg」と自動解釈
  │
  └→ Communication Agent:
       └─ send_line → 「下記の内容で注文を承ります:
                        ・ツナ缶 1個
                        ・完熟トマト 15kg
                        よろしければ「OK」とご返信ください」

  ─── 店長返信: 「OK」 ───

  └→ Learning Service:
       └─ update_pattern_confidence("ツナ缶100g"): 0.7 → 0.85
       └─ update_pattern_confidence("トマト多め"): 0.85 → 0.92
```

#### 例C: N回目 ── 高信頼パターンで完全自動処理

```
同じC-042店長「ツナ缶100gとトマト多めで」(LINE) ← 何度も確定済み

Orchestrator → Intake Agent:
  │
  ├─ resolve_with_pattern(C-042, "ツナ缶100g")
  │    → confidence: 0.95（閾値0.9超え）→ 確認不要で自動確定
  │
  ├─ resolve_with_pattern(C-042, "トマト多め")
  │    → confidence: 0.97 → 確認不要で自動確定
  │
  └→ Inventory Agent → 在庫OK
  └→ Communication Agent:
       └─ send_line → 「ご注文承りました:
                        ・ツナ缶 1個
                        ・完熟トマト 15kg
                        本日配送予定です」

  ※ 確認ステップなしで即確定（担当者ダッシュボードには表示）
```

#### 例D: 異常数量検知 ── 誤発注防止

```
C-042店長「トマト150kgで」(LINE) ← 普段は10-20kg

Orchestrator → Intake Agent → Exception Agent:
  │
  ├─ detect_quantity_anomaly(C-042, P-103, 150kg)
  │    ├─ 過去パターン: 平均15kg, 標準偏差5kg, 最大30kg
  │    ├─ 150kg = 平均の10倍 → 異常スコア: 0.99（閾値0.8超え）
  │    └─ 判定: 「誤発注の可能性が高い」
  │
  ├→ Communication Agent:
  │    └─ send_line → 「トマト150kgのご注文ですが、
  │                     いつもは15kg前後です。
  │                     数量をご確認いただけますか？」
  │
  │   ─── 店長返信: 「ああ、15kgの間違い！」 ───
  │
  ├→ Intake Agent: 数量修正 → 15kg
  └→ 通常フローへ（Learning Serviceが「150kgは誤り」も記録）
```

### 3.3 Order Intelligence Store（発注パターンDB）

Agent の「記憶」を支えるデータモデル。テナント×顧客×商品ごとに蓄積される。

```
Order Intelligence Store（Cosmos DB コンテナ: order-intelligence）

┌─────────────────────────────────────────────────────────────────────┐
│  発注パターン（OrderPattern）                                       │
│                                                                     │
│  ■ 単品パターン（1表現 → 1商品）                                    │
│  {                                                                  │
│    "id": "pat-C042-tuna100g",                                       │
│    "tenant_id": "T-001",                                            │
│    "customer_id": "C-042",                                          │
│    "type": "single",                                                │
│    "input_expression": "ツナ缶100g",        // 顧客の生の表現       │
│    "input_expression_normalized": "ツナ缶100g",  // 正規化済み表現  │
│    "input_embedding": [0.12, -0.34, ...],   // Embedding（類似検索用）│
│    "resolved_items": [                      // ※ 配列で統一         │
│      {                                                              │
│        "product_id": "P-201",                                       │
│        "product_name": "ツナ缶",                                    │
│        "qty": 1,                                                    │
│        "unit": "個"                                                 │
│      }                                                              │
│    ],                                                               │
│    "confidence": 0.95,                      // 信頼度 (0.0-1.0)     │
│    "occurrence_count": 8,                   // 出現回数             │
│    "last_confirmed_at": "2026-05-14T07:23:00Z",                     │
│    "source": "customer_confirmed"           // 学習ソース           │
│  }                                                                  │
│                                                                     │
│  ■ テンプレートパターン（1表現 → 複数商品セット）                    │
│  {                                                                  │
│    "id": "pat-C088-itsumo",                                         │
│    "tenant_id": "T-001",                                            │
│    "customer_id": "C-088",                                          │
│    "type": "template",                                              │
│    "input_expression": "いつもの",                                   │
│    "input_expression_normalized": "いつもの",                        │
│    "input_embedding": [0.05, 0.78, ...],                            │
│    "resolved_items": [                      // 複数商品を格納       │
│      { "product_id": "P-050", "product_name": "鶏もも肉",          │
│        "qty": 20, "unit": "kg" },                                   │
│      { "product_id": "P-112", "product_name": "キャベツ",           │
│        "qty": 10, "unit": "ケース" },                               │
│      { "product_id": "P-300", "product_name": "卵",                 │
│        "qty": 5, "unit": "パック" }                                 │
│    ],                                                               │
│    "confidence": 0.98,                                              │
│    "occurrence_count": 12,                                          │
│    "last_confirmed_at": "2026-05-13T06:50:00Z",                     │
│    "source": "customer_confirmed"                                   │
│  }                                                                  │
│                                                                     │
│  ※ confidence 閾値:                                                 │
│     < 0.5  → 毎回確認が必要                                        │
│     0.5-0.9 → 解釈結果を提示して軽い確認（「○○でよろしいですか？」）│
│     ≥ 0.9  → 自動確定（確認スキップ）                               │
│                                                                     │
│  ※ テナントごとに閾値はカスタマイズ可能                             │
│                                                                     │
│  ※ パターン検索方式:                                                │
│     1. input_expression_normalized で完全一致を試行                  │
│     2. 一致なし → input_embedding でコサイン類似度検索               │
│        (Azure AI Search のベクトル検索を利用)                        │
│     3. 類似度 > 0.85 のパターンがあれば候補として返す                │
│     →「ツナ缶100g」「つな缶100グラム」「ツナ缶を100g」を同一視     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  顧客発注プロファイル（CustomerOrderProfile）                       │
│                                                                     │
│  {                                                                  │
│    "id": "prof-C042",                                               │
│    "tenant_id": "T-001",                                            │
│    "customer_id": "C-042",                                          │
│    "product_stats": {                                               │
│      "P-103": {                            // 完熟トマト            │
│        "avg_qty": 15.0,                    // 平均注文数量          │
│        "std_dev": 5.2,                     // 標準偏差              │
│        "min_qty": 5.0,                     // 最小注文数量          │
│        "max_qty": 30.0,                    // 最大注文数量          │
│        "typical_unit": "kg",               // 通常使用する単位      │
│        "order_frequency_days": 3.5,        // 平均注文間隔（日）    │
│        "last_ordered_at": "2026-05-12",                             │
│        "total_orders": 24                  // 累計注文回数          │
│      },                                                             │
│      "P-201": { ... }                      // ツナ缶               │
│    },                                                               │
│    "anomaly_thresholds": {                                          │
│      "qty_z_score": 3.0,                   // 数量のZスコア閾値     │
│      "frequency_alert_days": 14            // 注文間隔アラート      │
│    }                                                                │
│  }                                                                  │
│                                                                     │
│  ※ 異常検知: Zスコア = |注文数量 - 平均| / 標準偏差                 │
│     Zスコア > 3.0 → 誤発注の可能性をアラート                        │
│     例: 平均15kg, 標準偏差5kg, 注文150kg → Z=27 → 確実に異常        │
│     例: 平均15kg, 標準偏差5kg, 注文30kg → Z=3 → ギリギリ正常        │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.4 Semantic Kernel ツール定義（実装イメージ）

```python
# ── Intake Agent のツール群 ──
class IntakePlugin:

    @kernel_function(description="顧客名/LINE ID/電話番号から顧客を特定する")
    async def lookup_customer(self, identifier: str, tenant_ctx: TenantContext) -> Customer:
        repo = tenant_ctx.get_connector(ICustomerRepository)
        return await repo.find_by_identifier(identifier)

    @kernel_function(description="商品名の表記ゆれをAI Searchで正規化する")
    async def normalize_product(self, raw_name: str, tenant_ctx: TenantContext) -> Product:
        search = tenant_ctx.get_connector(IProductMaster)
        return await search.fuzzy_match(raw_name)

    @kernel_function(description="過去の発注パターンに基づいて曖昧な表現を解釈する。"
                     "Embeddingベースの類似検索で表記ゆれにも対応。"
                     "パターンが見つかれば解釈結果とconfidenceを返す。初回ならNoneを返す。")
    async def resolve_with_pattern(self, customer_id: str, raw_expression: str,
                                    tenant_ctx: TenantContext) -> PatternMatch | None:
        store = tenant_ctx.get_connector(IOrderIntelligenceStore)
        embedding = await tenant_ctx.embedding_client.embed(raw_expression)

        # 1. Embeddingベースの類似検索（表記ゆれ対応）
        #    「ツナ缶100g」「つな缶100グラム」「ツナ缶を100g」を同一パターンとして検出
        pattern = await store.find_pattern_by_embedding(
            customer_id, embedding, similarity_threshold=0.85
        )

        if not pattern:
            return None  # 初回 → Exception Agentへ

        if pattern.confidence >= tenant_ctx.config.auto_confirm_threshold:
            return PatternMatch(
                resolved_items=pattern.resolved_items,
                confidence=pattern.confidence,
                needs_confirmation=False
            )
        else:
            return PatternMatch(
                resolved_items=pattern.resolved_items,
                confidence=pattern.confidence,
                needs_confirmation=True
            )

    @kernel_function(description="注文ドラフトの必須項目を検証する")
    async def validate_order_draft(self, draft: OrderDraft) -> ValidationResult:
        missing = [f for f in ["customer", "product", "quantity"] if not getattr(draft, f)]
        return ValidationResult(valid=not missing, missing_fields=missing)


# ── Inventory Agent のツール群 ──
class InventoryPlugin:

    @kernel_function(description="在庫数量を確認する")
    async def check_inventory(self, product_id: str, tenant_ctx: TenantContext) -> InventoryStatus:
        svc = tenant_ctx.get_connector(IInventoryService)
        return await svc.check(product_id)

    @kernel_function(description="在庫不足時に代替品を提案する")
    async def find_alternatives(self, product_id: str, required_qty: float,
                                 tenant_ctx: TenantContext) -> list[Alternative]:
        svc = tenant_ctx.get_connector(IInventoryService)
        return await svc.find_alternatives(product_id, required_qty)


# ── Exception Agent のツール群 ──
class ExceptionPlugin:

    @kernel_function(description="不足情報を確認する質問メッセージを生成する")
    async def ask_clarification(self, draft: OrderDraft, order_history: list[Order]) -> str:
        ...

    @kernel_function(description="注文数量が顧客の過去パターンから著しく逸脱しているか検知する")
    async def detect_quantity_anomaly(self, customer_id: str, product_id: str,
                                      ordered_qty: float,
                                      tenant_ctx: TenantContext) -> AnomalyResult:
        store = tenant_ctx.get_connector(IOrderIntelligenceStore)
        profile = await store.get_customer_profile(customer_id)
        stats = profile.product_stats.get(product_id)
        if not stats or stats.total_orders < 3:
            return AnomalyResult(is_anomaly=False, reason="データ不足")
        z_score = abs(ordered_qty - stats.avg_qty) / stats.std_dev
        threshold = profile.anomaly_thresholds.qty_z_score
        return AnomalyResult(
            is_anomaly=z_score > threshold,
            z_score=z_score,
            avg_qty=stats.avg_qty,
            max_qty=stats.max_qty,
            reason=f"通常{stats.avg_qty}{stats.typical_unit}のところ{ordered_qty}{stats.typical_unit}"
        )

    @kernel_function(description="注文の単位が顧客の通常使用単位と異なるか検知する")
    async def detect_unit_anomaly(self, customer_id: str, product_id: str,
                                   ordered_unit: str,
                                   tenant_ctx: TenantContext) -> AnomalyResult:
        store = tenant_ctx.get_connector(IOrderIntelligenceStore)
        profile = await store.get_customer_profile(customer_id)
        stats = profile.product_stats.get(product_id)
        if stats and stats.typical_unit != ordered_unit:
            return AnomalyResult(is_anomaly=True,
                                  reason=f"通常は{stats.typical_unit}単位だが{ordered_unit}で注文")
        return AnomalyResult(is_anomaly=False)

    @kernel_function(description="担当者にエスカレーションする")
    async def escalate_to_human(self, draft: OrderDraft, reason: str) -> EscalationTicket:
        ...


# ── Learning Service（非Agent・Azure Functions で実装） ──
# LLM推論は不要。注文確定イベント（Cosmos DB Change Feed）で非同期起動する。
class LearningService:

    def __init__(self, embedding_client: FoundryEmbeddingClient):
        self.embedding_client = embedding_client

    async def record_pattern(self, customer_id: str, input_expression: str,
                              resolved_items: list[ResolvedItem], source: str,
                              tenant_ctx: TenantContext) -> OrderPattern:
        store = tenant_ctx.get_connector(IOrderIntelligenceStore)
        normalized = self._normalize_expression(input_expression)
        embedding = await self.embedding_client.embed(input_expression)

        existing = await store.find_pattern_by_embedding(
            customer_id, embedding, similarity_threshold=0.85
        )
        if existing and self._same_resolution(existing.resolved_items, resolved_items):
            existing.confidence = min(1.0, existing.confidence + 0.1)
            existing.occurrence_count += 1
            return await store.update_pattern(existing)
        else:
            pattern_type = "template" if len(resolved_items) > 1 else "single"
            return await store.create_pattern(OrderPattern(
                customer_id=customer_id,
                type=pattern_type,
                input_expression=input_expression,
                input_expression_normalized=normalized,
                input_embedding=embedding,
                resolved_items=resolved_items,
                confidence=0.5 if source == "agent_inferred" else 0.7,
                occurrence_count=1,
                source=source
            ))

    async def build_customer_profile(self, customer_id: str,
                                      tenant_ctx: TenantContext) -> CustomerOrderProfile:
        store = tenant_ctx.get_connector(IOrderIntelligenceStore)
        orders = await tenant_ctx.get_connector(IOrderRepository).list_by_customer(
            customer_id, limit=100
        )
        profile = await store.get_customer_profile(customer_id) or CustomerOrderProfile(customer_id)
        for product_id, product_orders in group_by_product(orders):
            quantities = [o.quantity for o in product_orders]
            profile.product_stats[product_id] = ProductStats(
                avg_qty=mean(quantities),
                std_dev=stdev(quantities) if len(quantities) > 1 else quantities[0] * 0.3,
                min_qty=min(quantities),
                max_qty=max(quantities),
                typical_unit=most_common(o.unit for o in product_orders),
                order_frequency_days=avg_interval(product_orders),
                total_orders=len(product_orders)
            )
        return await store.upsert_profile(profile)

    def _normalize_expression(self, expr: str) -> str:
        """全角→半角、スペース除去、カタカナ統一など基本的な正規化"""
        ...

    def _same_resolution(self, a: list[ResolvedItem], b: list[ResolvedItem]) -> bool:
        """同じ商品セットに解決されているか判定"""
        return sorted(i.product_id for i in a) == sorted(i.product_id for i in b)
```

---

## 4. Connector 層設計（テナント別DB/API差し替え）

### 4.1 設計思想

```
                        ┌─────────────────────────┐
                        │    Agent (Plugin)        │
                        │    ※ DBを直接知らない    │
                        └──────────┬──────────────┘
                                   │ 呼び出し
                                   ▼
                        ┌─────────────────────────┐
                        │  Connector Interface     │  ← 共通の抽象インターフェース
                        │  (IOrderRepository 等)   │
                        └──────────┬──────────────┘
                                   │ テナント設定で解決
                    ┌──────────────┼──────────────────┐
                    ▼              ▼                   ▼
          ┌─────────────┐ ┌───────────────┐ ┌──────────────────┐
          │ CosmosDB    │ │ SQL Server    │ │ External API     │
          │ Adapter     │ │ Adapter       │ │ Adapter          │
          │ (デフォルト)│ │ (顧客既存DB) │ │ (顧客既存API)   │
          └─────────────┘ └───────────────┘ └──────────────────┘
```

### 4.2 Connector Interface 定義

```python
# すべてのテナントで共通のインターフェース
class IOrderRepository(Protocol):
    async def save(self, order: Order) -> str: ...
    async def find_by_id(self, order_id: str) -> Order: ...
    async def list_by_date(self, tenant_id: str, date: date) -> list[Order]: ...
    async def list_by_customer(self, customer_id: str, limit: int) -> list[Order]: ...
    async def update_status(self, order_id: str, status: OrderStatus) -> None: ...

class IInventoryService(Protocol):
    async def check(self, product_id: str) -> InventoryStatus: ...
    async def find_alternatives(self, product_id: str, qty: float) -> list[Alternative]: ...
    async def reserve(self, product_id: str, qty: float) -> ReservationResult: ...

class IProductMaster(Protocol):
    async def fuzzy_match(self, raw_name: str) -> Product: ...
    async def get_by_id(self, product_id: str) -> Product: ...
    async def list_for_customer(self, customer_id: str) -> list[Product]: ...

class ICustomerRepository(Protocol):
    async def find_by_identifier(self, identifier: str) -> Customer: ...
    async def get_order_history(self, customer_id: str, limit: int) -> list[Order]: ...

class IOrderIntelligenceStore(Protocol):
    """発注パターン学習・顧客プロファイル管理（Learning Service用）"""
    async def find_pattern_by_embedding(self, customer_id: str, embedding: list[float],
                                         similarity_threshold: float) -> OrderPattern | None: ...
    async def create_pattern(self, pattern: OrderPattern) -> OrderPattern: ...
    async def update_pattern(self, pattern: OrderPattern) -> OrderPattern: ...
    async def get_customer_profile(self, customer_id: str) -> CustomerOrderProfile | None: ...
    async def upsert_profile(self, profile: CustomerOrderProfile) -> CustomerOrderProfile: ...
```

### 4.3 テナント設定によるConnector解決

```python
# テナント設定（Platform DBに格納）
tenant_config = {
    "tenant_id": "T-001",
    "name": "デモ環境A",
    "connectors": {
        "IOrderRepository": {
            "type": "cosmosdb",
            "connection": "AccountEndpoint=https://xxx.documents.azure.com:443/;...",
            "database": "orders-t001"
        },
        "IInventoryService": {
            "type": "azure_sql",
            "connection": "Server=xxx.database.windows.net;Database=inventory-t001;..."
        },
        "IProductMaster": {
            "type": "ai_search",
            "endpoint": "https://xxx.search.windows.net",
            "index": "products-t001"
        }
    }
}

# 顧客既存システム接続の例
tenant_config_existing = {
    "tenant_id": "T-042",
    "name": "○○食品株式会社",
    "connectors": {
        "IOrderRepository": {
            "type": "custom_api",
            "endpoint": "https://erp.example-foods.co.jp/api/orders",
            "auth": {"type": "oauth2", "token_url": "..."}
        },
        "IInventoryService": {
            "type": "custom_sql",
            "connection": "Server=192.168.xxx;Database=InventoryDB;...",
            "via": "azure_relay"  # オンプレ接続はAzure Relay経由
        }
    }
}
```

### 4.4 Connector Factory（ランタイム解決）

```python
class ConnectorFactory:
    """テナント設定に基づいてConnector実装を動的に解決する"""

    _registry: dict[str, dict[str, type]] = {
        "IOrderRepository": {
            "cosmosdb": CosmosDBOrderRepository,
            "azure_sql": SqlOrderRepository,
            "custom_api": ExternalApiOrderRepository,
        },
        "IInventoryService": {
            "azure_sql": SqlInventoryService,
            "custom_sql": CustomSqlInventoryService,
            "custom_api": ExternalApiInventoryService,
        },
        "IOrderIntelligenceStore": {
            "cosmosdb": CosmosDBOrderIntelligenceStore,  # デフォルト
        },
        # ...
    }

    def resolve(self, interface: str, tenant_config: TenantConfig) -> Any:
        connector_cfg = tenant_config.connectors[interface]
        adapter_class = self._registry[interface][connector_cfg.type]
        return adapter_class(connector_cfg)
```

---

## 5. マルチテナント設計

### 5.1 テナント分離戦略

```
┌─────────────────────────────────────────────────────────┐
│                  共有リソース                             │
│  ・Azure Container Apps（アプリ実行基盤）                │
│  ・Azure AI Agent Service（Agent実行）                   │
│  ・Azure AI Foundry（LLM推論・Embedding）                │
│  ・Platform DB（テナント管理・設定）                      │
└─────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────┐
│                テナント別リソース                         │
│  ・Cosmos DB データベース / コンテナ（テナント別に分離）  │
│  ・Order Intelligence Store（テナント×顧客×商品パターン）│
│  ・Azure SQL スキーマ or データベース（テナント別）       │
│  ・Blob Storage コンテナ（テナント別）                    │
│  ・AI Search インデックス（テナント別）                   │
│  ・Agent Thread（テナント×顧客の会話コンテキスト）        │
│  ・Connector 設定（テナント別に接続先を切り替え）         │
└─────────────────────────────────────────────────────────┘
```

### 5.2 新規テナント（デモ環境）のプロビジョニング

```
管理者が「新規テナント作成」を実行
  │
  ├→ Platform DB にテナントレコード作成
  ├→ Cosmos DB に新規データベース自動作成
  ├→ Azure SQL にスキーマ＋初期マスタデータ投入
  ├→ AI Search にインデックス作成
  ├→ Blob Storage にコンテナ作成
  ├→ Default Connector 設定を自動登録
  │
  └→ 即利用可能（所要時間: 数分）
```

---

## 6. 使用 Azure サービス一覧

| レイヤー | サービス | 用途 |
|---|---|---|
| **受注チャネル** | | |
| 電話着信 | Azure Communication Services (Call Automation) | 電話着信の受付・音声ストリーム取得 |
| 音声文字起こし | Azure AI Speech | 音声ストリームのリアルタイムテキスト化 |
| LINE連携 | LINE Messaging API + Azure Functions | Webhook受信・返信 |
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
| アプリ実行 | Azure Container Apps | ダッシュボード・API・管理コンソール |
| サーバーレス | Azure Functions | Webhook受信・イベント駆動処理 |
| **セキュリティ** | | |
| 認証 | Microsoft Entra ID | SSO・テナント別権限管理 |
| 秘密管理 | Azure Key Vault | 接続文字列・APIキー管理 |
| オンプレ接続 | Azure Relay | 顧客既存システムとのハイブリッド接続 |

---

## 7. データフロー詳細

> **MVP方針**: Service Bus はスケール時（本番運用・マルチテナント）に導入する。
> MVP段階では Azure Functions が各チャネルの Webhook/イベントを直接受信し、
> Agent を同期呼び出しする構成でシンプルに実装する。

### 7.1 LINE チャネル

```
顧客 → LINE メッセージ送信
    → LINE Webhook → Azure Functions (直接受信)
    → テナントID解決（LINE公式アカウント → テナント紐付け）
    → セッション判定（後述 7.4）
        ├─ 既存セッションあり → 該当セッションのAgent Threadに返信を追記
        └─ 新規 → 新しいAgent Thread作成
    → Orchestrator Agent (Azure AI Agent Service)
        ├→ Intake Agent: 注文解析・顧客特定・パターン照合・商品正規化
        ├→ [必要に応じて] Exception Agent: 確認質問 / 異常検知
        ├→ Inventory Agent: 在庫照合
        └→ Communication Agent: 返信生成・LINE送信
    → Cosmos DB (受注ドキュメント保存)
    → Learning Service (非同期: パターン記録・プロファイル更新)
    → ダッシュボード更新 (リアルタイム)
```

### 7.2 メール チャネル

```
顧客 → メール送信
    → Microsoft Graph API (Office 365 Change Notifications)
    → Azure Functions (通知受信・メール本文取得)
    → テナントID解決（受信アドレス → テナント紐付け）
    → Orchestrator Agent → 各専門Agent
    → Cosmos DB (保存)
    → Azure Communication Services でメール自動返信
    → Learning Service (非同期)
```

### 7.3 電話（音声）チャネル

```
顧客 → 電話発信
    → ACS Call Automation (着信受付・音声ストリーム取得)
    → Azure AI Speech (リアルタイム文字起こし)
    → テナントID解決（着信番号 → テナント紐付け）
    → Azure Functions → Orchestrator Agent → 各専門Agent
    → Cosmos DB (保存) + 担当者ダッシュボードに表示 + SMS通知
    → Learning Service (非同期)
```

### 7.4 LINE会話セッション管理

確認質問→顧客返信の会話継続を実現するために、セッション管理が必要。

```
セッション管理テーブル（Cosmos DB: order-sessions）

{
  "id": "sess-U1234-20260515-001",
  "tenant_id": "T-001",
  "channel": "line",
  "channel_user_id": "U1234...",        // LINE User ID
  "customer_id": "C-042",
  "agent_thread_id": "thread_abc123",   // Azure AI Agent Service の Thread ID
  "status": "awaiting_reply",           // active / awaiting_reply / completed / expired
  "pending_order_draft": { ... },       // 確認中の注文ドラフト
  "created_at": "2026-05-15T07:15:00Z",
  "expires_at": "2026-05-15T09:15:00Z", // 2時間でタイムアウト
  "last_message_at": "2026-05-15T07:15:30Z"
}

フロー:
  1. LINE Webhook受信 → channel_user_id + tenant_id でセッション検索
  2. status=awaiting_reply のセッションがある
     → 既存の agent_thread_id に返信を追記
     → Orchestrator Agent が会話を継続（Thread内のコンテキストを保持）
  3. セッションがない or expired
     → 新しいセッション + Agent Thread を作成
     → 新規注文として処理開始
  4. 注文確定 → status=completed に更新
  5. タイムアウト → Azure Functions (Timer Trigger) で定期的に expired に更新
     → 担当者ダッシュボードに「返信待ちタイムアウト」として通知
```

### 7.5 本番スケール時の構成変更

```
MVP構成:
  LINE Webhook → Azure Functions → Orchestrator Agent（直接呼び出し）

本番構成（マルチテナント・高負荷対応時に移行）:
  LINE Webhook → Azure Functions → Service Bus (テナント別トピック)
              → Azure Functions (トリガー) → Orchestrator Agent

※ Service Bus を挟むことで:
  ・テナント間の負荷分離（1テナントの大量注文が他テナントに影響しない）
  ・デッドレターキューによる障害時のメッセージ保全
  ・ピーク時のバッファリング（朝の注文集中）
  が実現できる。MVP段階では不要。
```

---

## 8. ユーザー体験フロー

### シナリオ1: 通常注文（即確定）

1. **朝7:00** ── 飲食店A店長からLINE: 「鶏もも肉 10kg、白菜 5ケース」
2. **Intake Agent** ── 顧客特定（A店 = C-012）、商品正規化、数量解析
3. **Inventory Agent** ── 在庫十分 → OK
4. **Communication Agent** ── LINE返信: 「ご注文承りました。鶏もも肉10kg、白菜5ケース、本日配送予定です」
5. **Learning Service** ── 確定注文を顧客プロファイルに反映（統計値を更新）
6. **結果** ── 受注確定・ピッキングリスト自動反映。担当者は確認するだけ

### シナリオ2: 単位の曖昧さ ── 初回は確認、次回から自動解釈

**【初回】**
1. **朝7:15** ── 飲食店B店長からLINE: 「ツナ缶100g」
2. **Intake Agent** ── `resolve_with_pattern` → パターンなし（初回）
3. **Exception Agent** ── 「ツナ缶は"個"単位（1個=70g）。100gは端数。確認が必要」
4. **Communication Agent** ── LINE返信: 「ツナ缶100gとのことですが、1個(70g)でよろしいですか？」
5. **店長返信** ── 「1個で！」
6. **Learning Service** ── パターン記録: `{C-015, "ツナ缶100g" → ツナ缶1個, confidence: 0.7}`

**【2回目】**
1. 同じB店長「ツナ缶100g」
2. **Intake Agent** ── `resolve_with_pattern` → HIT（confidence: 0.7、閾値0.9未満）
3. **Communication Agent** ── LINE返信: 「ツナ缶1個でよろしいですか？」（軽い確認のみ）
4. **店長返信** ── 「OK」
5. **Learning Service** ── confidence更新: 0.7 → 0.85

**【4回目以降】**
1. 同じB店長「ツナ缶100g」
2. **Intake Agent** ── `resolve_with_pattern` → HIT（confidence: 0.95、閾値超え）
3. → **確認なしで自動確定**。ツナ缶1個として即処理
4. **Communication Agent** ── LINE返信: 「ご注文承りました。ツナ缶1個、本日配送予定です」

### シナリオ3: 誤発注の自動検知

1. **朝7:30** ── 飲食店C店長からLINE: 「トマト150kgで」
2. **Intake Agent** ── 商品正規化OK、数量解析OK → 一見正常
3. **Exception Agent** ── `detect_quantity_anomaly`:
   - 過去パターン: 平均15kg、最大30kg、標準偏差5kg
   - 150kg → Zスコア = 27.0（閾値3.0を大幅超過）
   - 判定: **「誤発注の可能性が非常に高い」**
4. **Communication Agent** ── LINE返信: 「トマト150kgのご注文ですが、いつもは15kg前後です。数量をご確認いただけますか？」
5. **店長返信** ── 「ああ15kgの間違い！ありがとう」
6. **結果** ── 15kgで受注確定。**事故を未然に防止**

### シナリオ4: 「いつもの」注文 ── 学習済みパターンでフル自動

1. **朝6:45** ── 常連の飲食店D店長からLINE: 「いつものお願い」
2. **Intake Agent** ── `resolve_with_pattern(C-088, "いつもの")`
   - → 過去パターン: 毎週月曜に同じ注文（鶏もも肉20kg, キャベツ10ケース, 卵5パック）
   - → confidence: 0.98（高信頼）
3. → **確認なしで自動確定**
4. **Communication Agent** ── LINE返信:
   「いつものご注文承りました: 鶏もも肉20kg / キャベツ10ケース / 卵5パック。本日配送予定です」
5. **結果** ── 担当者出社前に処理完了

### シナリオ5: 複数チャネル同時着信（朝のピーク）

1. **朝6:30-7:00** ── LINE 8件 + メール 3件 + 電話 2件 = 13件同時
2. **Service Bus** ── 全件並列でキューイング
3. **各Agent** ── 並列処理（Azure Container Apps のオートスケール）
4. **Learning Service** ── 学習済みパターンにより13件中9件が自動確定
5. **担当者出社** ── ダッシュボードに全件処理済み一覧。**確認待ちはたった4件**

---

## 9. MVP スコープ（ハッカソン提出版）

| Phase | 機能 | 実装方法 |
|---|---|---|
| **Must（デモ必須）** | Orchestrator + Intake Agent | Azure AI Agent Service + Semantic Kernel |
| **Must** | Exception Agent（確認質問 + 異常数量検知） | 同上（Agenticらしさのデモの核心） |
| **Must** | Learning Service（パターン学習 + 自動解釈） | Cosmos DB (Order Intelligence Store) + Azure Functions + Foundry Embedding |
| **Must** | LINE受信→注文抽出→自動返信 | LINE Webhook + Azure Functions |
| **Must** | 受注一覧ダッシュボード | Azure Container Apps |
| **Must** | Inventory Agent（在庫照合） | Azure SQL + Semantic Kernel Plugin |
| **Must** | テナント切り替えデモ | Connector Factory + 2テナント設定 |
| **Should** | AI Search商品あいまい検索 | Azure AI Search |
| **Should** | 電話音声→テキスト変換 | ACS Call Automation + Azure AI Speech |
| **Should** | ピッキングリストPDF生成 | Azure Functions |
| **Could** | メール受信→注文抽出 | Microsoft Graph API (Office 365) |
| **Could** | メール自動返信 | Azure Communication Services |

---

## 10. 非機能要件

| 要件 | 対応 |
|---|---|
| **可用性** | Azure Container Apps の自動スケーリング（朝のピーク対応） |
| **テナント分離** | データベース/コンテナ/インデックス単位で分離。Entra IDでアクセス制御 |
| **セキュリティ** | Entra ID認証、Key Vault秘密管理、Azure Relay経由のオンプレ接続 |
| **監査ログ** | Agent推論ログ含む全操作をCosmos DBに記録 |
| **バックアップ** | 音声・メール原本をBlob Storageに90日保管 |
| **拡張性** | 新チャネル=①に追加、新Agent=③にPlugin追加、新DB=④にAdapter追加 |
| **DB使い分け** | **Cosmos DB**: 受注ドキュメント・パターン学習・セッション（スキーマレス＋TTL＋Change Feed向き）。**Azure SQL**: マスタデータ・在庫（リレーショナル整合性・JOIN・トランザクション向き）。MVP段階でも両方使う理由は、マスタ管理のリレーショナル制約とドキュメント系のスキーマ柔軟性を両立するため |
