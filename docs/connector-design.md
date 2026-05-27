# Connector層・マルチテナント設計

> テナント別DB/API差し替え・データ分離・プロビジョニングの詳細設計

## 設計思想

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

## Connector Interface 定義

```python
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

class IPickingListRepository(Protocol):
    """ピッキングリストの生成・管理"""
    async def generate_from_orders(self, tenant_id: str, delivery_date: date) -> PickingList: ...
    async def get_by_date(self, tenant_id: str, delivery_date: date) -> PickingList: ...
    async def update_item_status(self, uid: str, status: str) -> None: ...
    async def update_actual_weight(self, uid: str, weight: float) -> None: ...

class IDeliveryRouteResolver(Protocol):
    """配送ルート・便の自動解決"""
    async def resolve_carrier(self, tenant_id: str, customer_id: str,
                               temperature_zone: str) -> tuple[str, str]: ...
    async def list_routes(self, tenant_id: str) -> list[dict]: ...

class ISessionRepository(Protocol):
    """会話セッション管理（LINE/電話の注文会話状態保持）"""
    async def create_session(self, session: OrderSession) -> OrderSession: ...
    async def find_active_session(self, tenant_id: str, channel: str, channel_user_id: str) -> OrderSession | None: ...
    async def update_session(self, session: OrderSession) -> None: ...

class IMessageHistoryRepository(Protocol):
    """会話メッセージ履歴（LINE/電話のやり取り保存・参照）"""
    async def create_message(self, message: MessageHistory) -> MessageHistory: ...
    async def list_recent_messages(self, tenant_id: str, channel: str,
                                     channel_user_id: str, limit: int) -> list[MessageHistory]: ...
    async def list_by_session_id(self, tenant_id: str, session_id: str) -> list[MessageHistory]: ...

class IOrderIntelligenceStore(Protocol):
    """発注パターン学習・顧客プロファイル管理（Learning Service用）"""
    async def find_pattern_by_embedding(self, customer_id: str, embedding: list[float],
                                         similarity_threshold: float) -> OrderPattern | None: ...
    async def create_pattern(self, pattern: OrderPattern) -> OrderPattern: ...
    async def update_pattern(self, pattern: OrderPattern) -> OrderPattern: ...
    async def get_customer_profile(self, customer_id: str) -> CustomerOrderProfile | None: ...
    async def upsert_profile(self, profile: CustomerOrderProfile) -> CustomerOrderProfile: ...
```

## テナント設定によるConnector解決

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

## Connector Factory（ランタイム解決）

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

## テナント分離戦略

```
┌─────────────────────────────────────────────────────────┐
│                  共有リソース                             │
│  ・Azure Container Apps（アプリ実行基盤）                │
│  ・Semantic Kernel（Agent実行）                           │
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

## 新規テナント（デモ環境）のプロビジョニング

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
