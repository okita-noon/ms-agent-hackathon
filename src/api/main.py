from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.connectors.adapters.registry import register_all_adapters
from src.services.line_handler import LineWebhookHandler
from src.services.tenant_resolver import resolve_tenant_by_id, resolve_tenant_for_line

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    register_all_adapters()
    logger.info("Adapter registry initialized")
    yield


app = FastAPI(title="OrderAI API", lifespan=lifespan)

dashboard_dir = Path(__file__).resolve().parent.parent / "dashboard"
if dashboard_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=str(dashboard_dir), html=True), name="dashboard")


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "orderai-api"}


async def _process_line_events(handler: LineWebhookHandler, body_json: dict) -> None:
    """Process LINE events in the background after returning 200 to LINE."""
    try:
        results = await handler.handle_webhook(body_json)
        logger.info("Processed %d LINE events", len(results))
    except Exception:
        logger.exception("Error processing LINE webhook in background")


@app.post("/api/line-webhook")
async def line_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature: str = Header(None),
):
    body_bytes = await request.body()
    body_json = await request.json()

    tenant_ctx = resolve_tenant_for_line(body_json.get("destination"))
    handler = LineWebhookHandler(
        tenant_ctx=tenant_ctx,
        azure_openai_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
        azure_openai_key=os.environ.get("AZURE_OPENAI_KEY", ""),
    )

    if x_line_signature and not handler.verify_signature(body_bytes, x_line_signature):
        raise HTTPException(status_code=403, detail="署名の検証に失敗しました。LINE Channelの設定を確認してください。")

    background_tasks.add_task(_process_line_events, handler, body_json)

    return Response(status_code=200)


@app.get("/api/orders")
async def list_orders(
    tenant_id: str = "T-001",
    delivery_date: str | None = None,
):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    repo = tenant_ctx.get_connector("IOrderRepository")

    if delivery_date:
        target = date.fromisoformat(delivery_date)
    else:
        target = date.today()

    orders = await repo.list_by_date(tenant_id, target)
    return {"orders": [o.model_dump(mode="json") for o in orders], "date": target.isoformat()}


@app.get("/api/orders/{order_id}")
async def get_order(order_id: str, tenant_id: str = "T-001"):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    repo = tenant_ctx.get_connector("IOrderRepository")
    order = await repo.find_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"受注ID「{order_id}」が見つかりません。IDをご確認ください。")
    return order.model_dump(mode="json")


@app.get("/api/products")
async def list_products(tenant_id: str = "T-001"):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    master = tenant_ctx.get_connector("IProductMaster")
    products = await master.list_all(tenant_id)
    return {"products": [p.model_dump() for p in products]}


@app.get("/api/inventory/{product_id}")
async def check_inventory(
    product_id: str,
    required_qty: float = 0,
    tenant_id: str = "T-001",
):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    svc = tenant_ctx.get_connector("IInventoryService")
    status = await svc.check(tenant_id, product_id, required_qty)
    return status.model_dump()


@app.get("/api/customers")
async def list_customers(tenant_id: str = "T-001"):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    repo = tenant_ctx.get_connector("ICustomerRepository")
    customers = await repo.list_all(tenant_id)
    return {"customers": [c.model_dump() for c in customers]}


@app.put("/api/customers/{customer_id}")
async def update_customer(customer_id: str, request: Request, tenant_id: str = "T-001"):
    body = await request.json()
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    repo = tenant_ctx.get_connector("ICustomerRepository")
    customer = await repo.get_by_id(tenant_id, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"顧客ID「{customer_id}」が見つかりません。IDをご確認ください。")
    updated = await repo.update(tenant_id, customer_id, body)
    return updated.model_dump()
