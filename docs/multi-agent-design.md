# マルチエージェント設計

> Orchestrator / Intake / Inventory / Communication / Exception (Agent) + Learning Service の詳細設計

## Agent 一覧と責務

| Agent | 責務 | 使用ツール（Semantic Kernel Plugin） | 判断の例 |
|---|---|---|---|
| **Orchestrator** | 意図分類・実行計画・Agent間調整 | `classify_intent`, `plan_execution`, `aggregate_results` | 「これは注文だ。Intake→Inventory→Commsの順で処理」 |
| **Phone Order** | 電話中の低レイテンシ注文抽出・復唱 | `lookup_customer`, `normalize_product`, `resolve_with_pattern` | 「電話なので1回のAgent呼び出しで注文ドラフトを作り、在庫確認はコードで同期実行」 |
| **Intake** | 自然言語→構造化データ変換 | `parse_order`, `lookup_customer`, `normalize_product`, `validate_order_draft`, `resolve_with_pattern` | 「"ツナ缶100g"→過去パターンで"ツナ缶1個"と自動解釈」 |
| **Inventory** | 在庫照合・欠品対応 | `check_inventory`, `find_alternatives`, `predict_demand` | 「在庫残10kg, 要求20kg→代替品キュウリ在庫あり」 |
| **Communication** | チャネル別返信生成・送信 | `generate_reply`, `send_line`, `send_email`, `send_sms` | 「LINEで来たからLINEで返す。丁寧語で」 |
| **Exception** | 曖昧・矛盾・異常の処理 | `ask_clarification`, `detect_quantity_anomaly`, `detect_unit_anomaly`, `escalate_to_human` | 「普段10個→今回100個。誤発注の可能性を確認」 |

**Learning Service（非Agent）**

| コンポーネント | 責務 | 関数 | 備考 |
|---|---|---|---|
| **Learning Service** | 発注パターン学習・統計更新 | `record_pattern`, `update_pattern_confidence`, `build_customer_profile`, `generate_expression_embedding` | Container Apps 内のバックグラウンドタスクとして実装。注文確定イベントで非同期起動。LLM推論不要のためAgentにしない（コスト・速度の最適化） |

## 電話同期応答フロー

電話チャネルは、通話中の沈黙を短くしつつ在庫確認まで返答するため、通常の4 Agent直列実行とは別に同期応答用の経路を持つ。

```
Azure AI Speech 文字起こし
  → Phone Order Agent（顧客特定・商品正規化・注文ドラフト化）
  → IInventoryService.check（アプリケーションコードで同期在庫確認）
  → TTS: 「りんご10箱ですね。在庫は確認できました。ご注文を受け付けます」
  → 既存 Orchestrator / Intake / Exception / Inventory / Communication（非同期で正式検証・登録）
```

Phone Order Agent は在庫判断や引当をLLMに任せない。LLMは注文抽出に集中し、在庫確認は Connector 経由の決定的な処理として実行する。
これにより電話1ターンあたりのLLM呼び出しを原則1回に抑え、既定20秒以内の応答を目標にする。
タイムアウト時は受付済みメッセージを返し、裏で既存マルチAgent処理を継続する。

## Agent 間フロー（具体例）

### 例A: 初回注文 ── 曖昧表現の確認 → パターン学習

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

### 例B: 2回目注文 ── 学習済みパターンで自動解釈

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

### 例C: N回目 ── 高信頼パターンで完全自動処理

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

### 例D: 異常数量検知 ── 誤発注防止

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

## Order Intelligence Store（発注パターンDB）

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

## Semantic Kernel ツール定義（実装イメージ）

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

        # Embeddingベースの類似検索（表記ゆれ対応）
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

## ダッシュボード連携（Dashboard Agent）

LINE / 電話で動く Agent 群はリアルタイム会話を捌くが、業務担当者が朝〜夕方に
「今日この後の配送分で、人手が必要なものは？」と確認するための窓口がダッシュボード
側にも必要。`src/services/dashboard_agent.py` の `DashboardAgentService` は
**Exception Agent と Resolution Agent をダッシュボード文脈で再利用** するための
薄いラッパー。

### 役割分担

| 区分 | 入口 | 主に呼ぶ Connector | 出力 |
|---|---|---|---|
| Exception Triage | `GET /api/agent/exceptions?...` | `IOrderRepository`, `IOrderIntelligenceStore`, `IInventoryService` | `ExceptionCase[]`（severity / type / evidence / metadata） |
| Resolution プレビュー | `POST /api/agent/resolutions/preview` | `IInventoryService.find_alternatives`（在庫不足時のみ） | `ResolutionPreview`（recommended_actions / customer_message / confidence） |
| Feature flag | `GET /api/agent/features` | — | env 由来の機能フラグ |

LLM 推論は呼ばず、CustomerOrderProfile（Z-score）と在庫の客観値で決定論的に
組み立てる。文面と推奨アクションは担当者承認後に Communication Agent へ委譲する
前提（`DASHBOARD_RESOLUTION_EXECUTE_ENABLED=true` で自動送信を許可）。
`/api/agent/exceptions` は受注一覧と同じ `delivery_date` / `order_date` / `status` / `q` /
`limit` / `offset` を受け取り、日付未指定時も現在表示中のページ範囲を対象にする。

### Exception Case の分類

| `type` | 検知ロジック | severity の基本値 |
|---|---|---|
| `needs_review` | `Order.status == 要対応`。旧データの `返信待ち` は Repository 取得時に `要対応` へ正規化 | high |
| `quantity_anomaly` | `ProductStats.std_dev` を使った Z-score (>3) で逸脱を検知。プロファイル不足時は 100 単位以上をフォールバック判定 | Z≥6 で high、それ未満は medium |
| `unit_anomaly` | `ProductStats.typical_unit` と `OrderItem.unit` の不一致 | medium |
| `inventory_shortage` | `IInventoryService.check` が `is_sufficient=False` を返す商品 | high |

### Resolution プレビューの構造

`ResolutionPreview` は LINE/電話チャネルで送る前提の `customer_message`、
担当者の作業を順序立てる `recommended_actions[]`、Agent の確からしさを示す
`confidence`、`requires_approval` を持つ。在庫不足の場合は
`IInventoryService.find_alternatives` を引き、`customer_message` に代替候補を
列挙する。

### Feature Flag

| env | 既定 | 用途 |
|---|---|---|
| `DASHBOARD_AGENT_ENABLED` | `false` | 機能のマスタースイッチ（false の場合 UI も非表示） |
| `DASHBOARD_EXCEPTION_TRIAGE_ENABLED` | `true` | `/exceptions` の有効化 |
| `DASHBOARD_RESOLUTION_AGENT_ENABLED` | `true` | `/resolutions/preview` の有効化 |
| `DASHBOARD_RESOLUTION_EXECUTE_ENABLED` | `false` | プレビュー承認時の自動送信を許可するか |
| `DASHBOARD_AGENT_DEMO_MODE` | `false` | デモ用挙動切り替えフラグ |

フロントの `frontend/src/components/DashboardAgentPanel.tsx` がサイドパネルとして
受注一覧画面に同居し、`/api/agent/features` でフラグを確認 →
`/api/agent/exceptions` で Exception を読み、各 Case ごとに
`/api/agent/resolutions/preview` を呼び出すフローで動作する。
