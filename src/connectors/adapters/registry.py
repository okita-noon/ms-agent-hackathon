from src.connectors.factory import register_adapter

from src.connectors.adapters.cosmos_order_repository import CosmosOrderRepository
from src.connectors.adapters.cosmos_session_repository import CosmosSessionRepository
from src.connectors.adapters.cosmos_intelligence_store import CosmosIntelligenceStore
from src.connectors.adapters.cosmos_message_history_repository import (
    CosmosMessageHistoryRepository,
)
from src.connectors.adapters.sql_product_master import SqlProductMaster
from src.connectors.adapters.sql_customer_repository import SqlCustomerRepository
from src.connectors.adapters.sql_inventory_service import SqlInventoryService
from src.connectors.adapters.search_product_master import SearchProductMaster


def register_all_adapters() -> None:
    register_adapter("IOrderRepository", "cosmosdb", CosmosOrderRepository)
    register_adapter("ISessionRepository", "cosmosdb", CosmosSessionRepository)
    register_adapter(
        "IMessageHistoryRepository", "cosmosdb", CosmosMessageHistoryRepository
    )
    register_adapter("IOrderIntelligenceStore", "cosmosdb", CosmosIntelligenceStore)
    register_adapter("IProductMaster", "azure_sql", SqlProductMaster)
    register_adapter("IProductMaster", "ai_search", SearchProductMaster)
    register_adapter("ICustomerRepository", "azure_sql", SqlCustomerRepository)
    register_adapter("IInventoryService", "azure_sql", SqlInventoryService)
