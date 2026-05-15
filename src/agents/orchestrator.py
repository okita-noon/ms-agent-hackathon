from __future__ import annotations

import json
import logging
from datetime import date, datetime

from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

from src.agents.definitions import (
    COMMUNICATION_AGENT_INSTRUCTIONS,
    EXCEPTION_AGENT_INSTRUCTIONS,
    INTAKE_AGENT_INSTRUCTIONS,
    INVENTORY_AGENT_INSTRUCTIONS,
    ORCHESTRATOR_INSTRUCTIONS,
)
from src.connectors.context import TenantContext
from src.models.order import Order, OrderItem, OrderSource, OrderStatus, TemperatureZone
from src.plugins.exception_plugin import ExceptionPlugin
from src.plugins.intake_plugin import IntakePlugin
from src.plugins.inventory_plugin import InventoryPlugin

logger = logging.getLogger(__name__)


class OrderOrchestrator:
    def __init__(
        self,
        tenant_ctx: TenantContext,
        azure_openai_endpoint: str,
        azure_openai_key: str,
        deployment_name: str = "gpt-4o",
    ):
        self._ctx = tenant_ctx
        self._endpoint = azure_openai_endpoint
        self._key = azure_openai_key
        self._deployment = deployment_name

    def _build_kernel(self) -> Kernel:
        kernel = Kernel()
        kernel.add_service(
            AzureChatCompletion(
                deployment_name=self._deployment,
                endpoint=self._endpoint,
                api_key=self._key,
            )
        )
        kernel.add_plugin(IntakePlugin(self._ctx), plugin_name="intake")
        kernel.add_plugin(InventoryPlugin(self._ctx), plugin_name="inventory")
        kernel.add_plugin(ExceptionPlugin(self._ctx), plugin_name="exception")
        return kernel

    async def process_order_message(
        self,
        message: str,
        line_user_id: str,
        reply_token: str | None = None,
        source: OrderSource = OrderSource.LINE,
    ) -> dict:
        kernel = self._build_kernel()

        agent = ChatCompletionAgent(
            kernel=kernel,
            name="Orchestrator",
            instructions=ORCHESTRATOR_INSTRUCTIONS,
        )

        user_message = (
            f"以下の注文メッセージを処理してください。\n"
            f"チャネル: {source.value}\n"
            f"LINE User ID: {line_user_id}\n"
            f"メッセージ: {message}\n\n"
            f"まず lookup_customer_by_line_id でこの顧客を特定し、"
            f"次に注文内容を解析してください。"
        )

        result_text = ""
        thread = None
        async for response in agent.invoke(messages=user_message, thread=thread):
            result_text = str(response.content)
            thread = response.thread

        logger.info("Orchestrator result: %s", result_text[:500])

        return {
            "response": result_text,
            "line_user_id": line_user_id,
            "reply_token": reply_token,
        }

    async def create_order_from_draft(
        self,
        draft: dict,
        source: OrderSource = OrderSource.LINE,
    ) -> Order:
        items = []
        for item_data in draft.get("items", []):
            items.append(
                OrderItem(
                    product_id=item_data["product_id"],
                    product_name=item_data["product_name"],
                    quantity=item_data.get("quantity"),
                    unit=item_data.get("unit", "kg"),
                    temperature_zone=TemperatureZone(
                        item_data.get("temperature_zone", "常温")
                    ),
                )
            )

        order = Order(
            uid="",
            tenant_id=self._ctx.tenant_id,
            order_date=date.today(),
            customer_id=draft["customer_id"],
            customer_name=draft.get("customer_name", ""),
            source=source,
            items=items,
            status=OrderStatus.PENDING,
        )

        repo = self._ctx.get_connector("IOrderRepository")
        order_id = await repo.save(order)
        order.id = order_id
        return order
