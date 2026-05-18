from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import date

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from src.agents.orchestrator import DEFAULT_AZURE_OPENAI_DEPLOYMENT
from src.auth.dependencies import get_tenant_id
from src.auth.endpoints import auth_router
from src.connectors.adapters.registry import register_all_adapters
from src.services.line_handler import LineWebhookHandler
from src.services.phone_handler import PhoneCallHandler
from src.services.tenant_resolver import resolve_tenant_by_id, resolve_tenant_for_line

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_FRONTEND_URL = "https://storderaidev.z11.web.core.windows.net/dashboard/"


@asynccontextmanager
async def lifespan(app: FastAPI):
    register_all_adapters()
    logger.info("Adapter registry initialized")
    yield


app = FastAPI(title="foogent API", lifespan=lifespan)

frontend_origins = [origin.strip() for origin in os.environ.get("FRONTEND_ORIGINS", "").split(",") if origin.strip()]
if frontend_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=frontend_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

frontend_origins = [origin.strip() for origin in os.environ.get("FRONTEND_ORIGINS", "").split(",") if origin.strip()]
if frontend_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=frontend_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ── Auth routes (public) ──────────────────────────────────────────────────────
app.include_router(auth_router, prefix="/api/auth")


@app.get("/")
async def root():
    return RedirectResponse(url=os.environ.get("FRONTEND_URL", DEFAULT_FRONTEND_URL))


@app.get("/dashboard")
@app.get("/dashboard/")
@app.get("/dashboard/{path:path}")
async def dashboard_redirect(path: str = ""):
    return RedirectResponse(url=os.environ.get("FRONTEND_URL", DEFAULT_FRONTEND_URL))


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "foogent-api"}


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
    x_line_signature: str | None = Header(None),
):
    if not x_line_signature:
        raise HTTPException(status_code=401, detail="x-line-signature header is required")

    body_bytes = await request.body()
    try:
        body_json = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_ctx = resolve_tenant_for_line(body_json.get("destination"))
    handler = LineWebhookHandler(
        tenant_ctx=tenant_ctx,
        azure_openai_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
        azure_openai_key=os.environ.get("AZURE_OPENAI_KEY", ""),
        azure_openai_deployment_name=os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", DEFAULT_AZURE_OPENAI_DEPLOYMENT),
    )

    if not handler.verify_signature(body_bytes, x_line_signature):
        raise HTTPException(
            status_code=403,
            detail="署名の検証に失敗しました。LINE Channelの設定を確認してください。",
        )

    background_tasks.add_task(_process_line_events, handler, body_json)
    return Response(status_code=200)


# ── Phone (ACS Call Automation) webhook ───────────────────────────────────────

_phone_handler: PhoneCallHandler | None = None


def _get_phone_handler() -> PhoneCallHandler:
    global _phone_handler  # noqa: PLW0603
    if _phone_handler is None:
        _phone_handler = PhoneCallHandler(
            callback_base_url=os.environ.get("ACS_CALLBACK_BASE_URL", ""),
            azure_openai_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
            azure_openai_key=os.environ.get("AZURE_OPENAI_KEY", ""),
            azure_openai_deployment_name=os.environ.get(
                "AZURE_OPENAI_DEPLOYMENT_NAME", DEFAULT_AZURE_OPENAI_DEPLOYMENT
            ),
            speech_service_key=os.environ.get("SPEECH_SERVICE_KEY", ""),
            speech_service_endpoint=os.environ.get("SPEECH_SERVICE_ENDPOINT"),
        )
    return _phone_handler


@app.post("/api/phone-webhook")
async def phone_webhook(request: Request):
    events = await request.json()
    if not isinstance(events, list):
        events = [events]

    handler = _get_phone_handler()
    results = []
    for event in events:
        event_type = event.get("type", "")
        if event_type == "Microsoft.EventGrid.SubscriptionValidationEvent":
            validation_code = event.get("data", {}).get("validationCode")
            return {"validationResponse": validation_code}

        try:
            result = await handler.handle_event(event)
            if result:
                results.append(result)
        except Exception:
            logger.exception("Error handling phone event: %s", event_type)

    return Response(status_code=200)


# ── Protected business endpoints ──────────────────────────────────────────────


@app.get("/api/orders")
async def list_orders(
    tenant_id: str = Depends(get_tenant_id),
    delivery_date: str | None = None,
):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    repo = tenant_ctx.get_connector("IOrderRepository")

    if delivery_date:
        target = date.fromisoformat(delivery_date)
    else:
        target = date.today()

    orders = await repo.list_by_date(tenant_id, target)
    return {
        "orders": [o.model_dump(mode="json") for o in orders],
        "date": target.isoformat(),
    }


@app.get("/api/orders/{order_id}")
async def get_order(order_id: str, tenant_id: str = Depends(get_tenant_id)):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    repo = tenant_ctx.get_connector("IOrderRepository")
    order = await repo.find_by_id(order_id)
    if not order:
        raise HTTPException(
            status_code=404,
            detail=f"受注ID「{order_id}」が見つかりません。IDをご確認ください。",
        )
    return order.model_dump(mode="json")


@app.get("/api/orders/{order_id}/messages")
async def get_order_messages(order_id: str, tenant_id: str = Depends(get_tenant_id)):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    order_repo = tenant_ctx.get_connector("IOrderRepository")
    order = await order_repo.find_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"受注ID「{order_id}」が見つかりません。")

    if not order.session_id:
        return {"messages": [], "session_id": None}

    history_repo = tenant_ctx.get_connector("IMessageHistoryRepository")
    messages = await history_repo.list_by_session_id(tenant_id, order.session_id)
    filtered = [m for m in messages if m.role in ("user", "assistant")]
    return {
        "messages": [m.model_dump(mode="json") for m in filtered],
        "session_id": order.session_id,
    }


@app.get("/api/products")
async def list_products(tenant_id: str = Depends(get_tenant_id)):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    master = tenant_ctx.get_connector("IProductMaster")
    products = await master.list_all(tenant_id)
    return {"products": [p.model_dump() for p in products]}


@app.get("/api/inventory")
async def list_inventory(tenant_id: str = Depends(get_tenant_id)):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    master = tenant_ctx.get_connector("IProductMaster")
    svc = tenant_ctx.get_connector("IInventoryService")
    products = await master.list_all(tenant_id)
    items = []
    for p in products:
        inv_status = await svc.check(tenant_id, p.id, 0)
        items.append(
            {
                "product_id": p.id,
                "product_name": p.name,
                "category": p.category,
                "temperature_zone": p.temperature_zone.value if p.temperature_zone else "常温",
                "quantity": inv_status.available_qty,
                "unit": inv_status.unit,
                "is_variable_weight": p.is_variable_weight,
                "price_per_unit": p.price_per_unit,
            }
        )
    return {"inventory": items}


@app.get("/api/inventory/{product_id}")
async def check_inventory(
    product_id: str,
    required_qty: float = 0,
    tenant_id: str = Depends(get_tenant_id),
):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    svc = tenant_ctx.get_connector("IInventoryService")
    inv_status = await svc.check(tenant_id, product_id, required_qty)
    return inv_status.model_dump()


@app.get("/api/customers")
async def list_customers(tenant_id: str = Depends(get_tenant_id)):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    repo = tenant_ctx.get_connector("ICustomerRepository")
    customers = await repo.list_all(tenant_id)
    return {"customers": [c.model_dump() for c in customers]}


@app.put("/api/customers/{customer_id}")
async def update_customer(customer_id: str, request: Request, tenant_id: str = Depends(get_tenant_id)):
    body = await request.json()
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    repo = tenant_ctx.get_connector("ICustomerRepository")
    customer = await repo.get_by_id(tenant_id, customer_id)
    if not customer:
        raise HTTPException(
            status_code=404,
            detail=f"顧客ID「{customer_id}」が見つかりません。IDをご確認ください。",
        )
    updated = await repo.update(tenant_id, customer_id, body)
    return updated.model_dump()
