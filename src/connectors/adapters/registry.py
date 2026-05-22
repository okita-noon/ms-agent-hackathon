from src.connectors.factory import register_adapter


def register_all_adapters() -> None:
    register_adapter(
        "IOrderRepository",
        "cosmosdb",
        "src.connectors.adapters.cosmos_order_repository.CosmosOrderRepository",
    )
    register_adapter(
        "ISessionRepository",
        "cosmosdb",
        "src.connectors.adapters.cosmos_session_repository.CosmosSessionRepository",
    )
    register_adapter(
        "IMessageHistoryRepository",
        "cosmosdb",
        "src.connectors.adapters.cosmos_message_history_repository.CosmosMessageHistoryRepository",
    )
    register_adapter(
        "IOrderIntelligenceStore",
        "cosmosdb",
        "src.connectors.adapters.cosmos_intelligence_store.CosmosIntelligenceStore",
    )
    register_adapter(
        "IProductMaster",
        "azure_sql",
        "src.connectors.adapters.sql_product_master.SqlProductMaster",
    )
    register_adapter(
        "IProductMaster",
        "ai_search",
        "src.connectors.adapters.search_product_master.SearchProductMaster",
    )
    register_adapter(
        "ICustomerRepository",
        "azure_sql",
        "src.connectors.adapters.sql_customer_repository.SqlCustomerRepository",
    )
    register_adapter(
        "IInventoryService",
        "azure_sql",
        "src.connectors.adapters.sql_inventory_service.SqlInventoryService",
    )
    # ── Email ──────────────────────────────────────────────────────────
    register_adapter(
        "IEmailService",
        "microsoft_graph",
        "src.connectors.adapters.graph_email_service.GraphEmailService",
    )
