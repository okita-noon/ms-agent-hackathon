from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from src.api.dashboard_agent import router as dashboard_agent_router
from src.auth.dependencies import get_tenant_id
from src.auth.endpoints import auth_router
from src.connectors.adapters.registry import register_all_adapters
from src.services.tenant_resolver import resolve_tenant_by_id, resolve_tenant_for_email, resolve_tenant_for_line

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_FRONTEND_URL = "https://storderaidev.z11.web.core.windows.net/dashboard/"
DEFAULT_AZURE_OPENAI_DEPLOYMENT = "gpt-5.4-mini"
LineWebhookHandler: Any | None = None
PhoneCallHandler: Any | None = None


GRAPH_SUBSCRIPTION_EXPIRY_HOURS = 48
GRAPH_SUBSCRIPTION_RENEW_BUFFER_SECONDS = 3600


async def _create_graph_subscription() -> str | None:
    """Graph APIのSubscriptionを作成し、メール受信通知を有効にする"""
    mailbox = os.environ.get("GRAPH_MAILBOX_USER_ID")
    client_id = os.environ.get("GRAPH_CLIENT_ID")
    client_secret = os.environ.get("GRAPH_CLIENT_SECRET")
    graph_tenant_id = os.environ.get("GRAPH_TENANT_ID")
    callback_url = os.environ.get("GRAPH_WEBHOOK_URL")

    if not all([mailbox, client_id, client_secret, graph_tenant_id, callback_url]):
        logger.info("Graph Subscription: 環境変数不足のためスキップ")
        return None

    try:
        import httpx

        from src.services.email_handler import _token_cache

        token = await _token_cache.get_token(graph_tenant_id, client_id, client_secret)
        expiry = datetime.now(timezone.utc) + timedelta(hours=GRAPH_SUBSCRIPTION_EXPIRY_HOURS)

        payload = {
            "changeType": "created",
            "notificationUrl": callback_url,
            "resource": f"/users/{mailbox}/messages",
            "expirationDateTime": expiry.strftime("%Y-%m-%dT%H:%M:%S.0000000Z"),
            "clientState": os.environ.get("GRAPH_WEBHOOK_CLIENT_STATE", "orderai-webhook"),
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://graph.microsoft.com/v1.0/subscriptions",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code in (200, 201):
                sub_id = resp.json().get("id")
                logger.info("Graph Subscription 作成完了: id=%s expiry=%s", sub_id, expiry.isoformat())
                return sub_id
            logger.error("Graph Subscription 作成失敗: %s %s", resp.status_code, resp.text)
            return None
    except Exception:
        logger.exception("Graph Subscription 作成エラー")
        return None


async def _renew_graph_subscription(subscription_id: str) -> None:
    """Subscriptionの自動更新ループ"""
    while True:
        renew_interval = GRAPH_SUBSCRIPTION_EXPIRY_HOURS * 3600 - GRAPH_SUBSCRIPTION_RENEW_BUFFER_SECONDS
        await asyncio.sleep(renew_interval)
        try:
            import httpx

            from src.services.email_handler import _token_cache

            client_id = os.environ.get("GRAPH_CLIENT_ID", "")
            client_secret = os.environ.get("GRAPH_CLIENT_SECRET", "")
            graph_tenant_id = os.environ.get("GRAPH_TENANT_ID", "")
            token = await _token_cache.get_token(graph_tenant_id, client_id, client_secret)

            expiry = datetime.now(timezone.utc) + timedelta(hours=GRAPH_SUBSCRIPTION_EXPIRY_HOURS)
            async with httpx.AsyncClient() as client:
                resp = await client.patch(
                    f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={"expirationDateTime": expiry.strftime("%Y-%m-%dT%H:%M:%S.0000000Z")},
                )
                if resp.status_code == 200:
                    logger.info("Graph Subscription 更新完了: id=%s expiry=%s", subscription_id, expiry.isoformat())
                else:
                    logger.error("Graph Subscription 更新失敗: %s %s", resp.status_code, resp.text)
        except Exception:
            logger.exception("Graph Subscription 更新エラー")


@asynccontextmanager
async def lifespan(app: FastAPI):
    register_all_adapters()
    logger.info("Adapter registry initialized")

    renew_task = None
    sub_id = await _create_graph_subscription()
    if sub_id:
        renew_task = asyncio.create_task(_renew_graph_subscription(sub_id))

    yield

    if renew_task:
        renew_task.cancel()


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

# ── Auth routes (public) ──────────────────────────────────────────────────────
app.include_router(auth_router, prefix="/api/auth")
app.include_router(dashboard_agent_router)


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


async def _process_line_events(handler: Any, body_json: dict) -> None:
    """Process LINE events in the background after returning 200 to LINE."""
    try:
        results = await handler.handle_webhook(body_json)
        logger.info("Processed %d LINE events", len(results))
    except Exception:
        logger.exception("Error processing LINE webhook in background")


async def _process_email_notification(
    message_id: str,
    recipient_address: str,
    azure_openai_endpoint: str,
    azure_openai_key: str,
) -> None:
    try:
        from src.services.email_handler import EmailIngestionService

        tenant_ctx = resolve_tenant_for_email(recipient_address)
        service = EmailIngestionService(
            tenant_ctx=tenant_ctx,
            azure_openai_endpoint=azure_openai_endpoint,
            azure_openai_key=azure_openai_key,
        )
        await service.process_notification(message_id, recipient_address)
    except Exception:
        logger.exception("Error processing email notification in background")


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
    global LineWebhookHandler  # noqa: PLW0603
    if LineWebhookHandler is None:
        from src.services.line_handler import LineWebhookHandler as _LineWebhookHandler

        LineWebhookHandler = _LineWebhookHandler

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


@app.api_route("/api/email-webhook", methods=["GET", "POST"])
async def email_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    validationToken: str | None = None,
):
    if validationToken:
        return Response(content=validationToken, media_type="text/plain")

    body = await request.json()

    expected_state = os.environ.get("GRAPH_WEBHOOK_CLIENT_STATE", "orderai-webhook")
    notifications = body.get("value", [])
    notifications = [n for n in notifications if n.get("clientState") == expected_state]
    if not notifications:
        logger.warning("Email webhook: clientState不一致または通知なし")
        return Response(status_code=202)
    default_recipient = os.environ.get("GRAPH_MAILBOX_ADDRESS", "order@example.com")
    azure_openai_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_key = os.environ.get("AZURE_OPENAI_KEY", "")

    for notification in notifications:
        resource_data = notification.get("resourceData", {}) or {}
        message_id = resource_data.get("id")
        if not message_id:
            continue
        recipient_address = (
            notification.get("recipientAddress")
            or notification.get("toAddress")
            or resource_data.get("recipientAddress")
            or default_recipient
        )
        background_tasks.add_task(
            _process_email_notification,
            message_id,
            recipient_address,
            azure_openai_endpoint,
            azure_openai_key,
        )

    return Response(status_code=202)


# ── Phone (ACS Call Automation) webhook ───────────────────────────────────────

_phone_handler: Any | None = None


class PhoneDemoMessageRequest(BaseModel):
    message: str = Field(..., min_length=1)
    caller_number: str = "+81312345678"
    called_number: str = "+81501234567"
    call_connection_id: str | None = None
    disconnect: bool = False


def _get_phone_handler() -> Any:
    global PhoneCallHandler, _phone_handler  # noqa: PLW0603
    if _phone_handler is None:
        if PhoneCallHandler is None:
            from src.services.phone_handler import PhoneCallHandler as _PhoneCallHandler

            PhoneCallHandler = _PhoneCallHandler

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


def _verify_eventgrid_key(request: Request, header_key: str | None) -> bool:
    """Verify the shared secret EventGrid presents on each delivery.

    Accepts the key in the ``X-EventGrid-Webhook-Key`` header or in a ``code``
    query parameter (Functions-style). Fails closed if ``EVENTGRID_WEBHOOK_KEY``
    is not configured.
    """
    expected = os.environ.get("EVENTGRID_WEBHOOK_KEY", "")
    if not expected:
        logger.error("EVENTGRID_WEBHOOK_KEY is not configured — rejecting phone webhook")
        return False
    presented = header_key or request.query_params.get("code", "")
    return bool(presented) and presented == expected


@app.post("/api/phone-webhook")
async def phone_webhook(
    request: Request,
    x_eventgrid_webhook_key: str | None = Header(None, alias="X-EventGrid-Webhook-Key"),
):
    if not _verify_eventgrid_key(request, x_eventgrid_webhook_key):
        raise HTTPException(status_code=401, detail="Unauthorized")

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


@app.post("/api/phone-demo/message")
async def phone_demo_message(
    payload: PhoneDemoMessageRequest,
    request: Request,
    x_eventgrid_webhook_key: str | None = Header(None, alias="X-EventGrid-Webhook-Key"),
):
    """Inject a recognized phone utterance without requiring an ACS phone number.

    Secured with the same shared key as the ACS EventGrid webhook so demo calls
    cannot be created anonymously on deployed environments.
    """
    if not _verify_eventgrid_key(request, x_eventgrid_webhook_key):
        raise HTTPException(status_code=401, detail="Unauthorized")

    handler = _get_phone_handler()
    result = await handler.process_demo_message(
        message=payload.message,
        caller_number=payload.caller_number,
        called_number=payload.called_number,
        call_connection_id=payload.call_connection_id,
    )
    if payload.disconnect:
        disconnect_result = await handler.disconnect_demo_call(result["call_connection_id"])
        result["disconnect"] = disconnect_result
    return result


# ── Protected business endpoints ──────────────────────────────────────────────


@app.get("/api/orders")
async def list_orders(
    tenant_id: str = Depends(get_tenant_id),
    delivery_date: str | None = None,
    status: str | None = None,
    source: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    repo = tenant_ctx.get_connector("IOrderRepository")

    if delivery_date:
        target = date.fromisoformat(delivery_date)
    else:
        target = date.today()

    orders, total = await repo.list_orders(
        tenant_id,
        target,
        status=status,
        source=source,
        q=q,
        limit=limit,
        offset=offset,
    )
    return {
        "orders": [o.model_dump(mode="json") for o in orders],
        "date": target.isoformat(),
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": {
            "status": status,
            "source": source,
            "q": q,
        },
    }


@app.get("/api/orders/{order_id}")
async def get_order(order_id: str, tenant_id: str = Depends(get_tenant_id)):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    repo = tenant_ctx.get_connector("IOrderRepository")
    order = await repo.find_by_id(tenant_id, order_id)
    if not order:
        raise HTTPException(
            status_code=404,
            detail=f"受注ID「{order_id}」が見つかりません。IDをご確認ください。",
        )
    return order.model_dump(mode="json")


class MemoUpdateRequest(BaseModel):
    memo: str | None = Field(None, max_length=2000)


@app.put("/api/orders/{order_id}/memo")
async def update_order_memo(order_id: str, body: MemoUpdateRequest, tenant_id: str = Depends(get_tenant_id)):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    repo = tenant_ctx.get_connector("IOrderRepository")
    order = await repo.find_by_id(tenant_id, order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"受注ID「{order_id}」が見つかりません。")
    order.memo = body.memo
    await repo.save(order)
    return order.model_dump(mode="json")


@app.get("/api/orders/{order_id}/messages")
async def get_order_messages(order_id: str, tenant_id: str = Depends(get_tenant_id)):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    order_repo = tenant_ctx.get_connector("IOrderRepository")
    order = await order_repo.find_by_id(tenant_id, order_id)
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
