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
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from src.api.dashboard_agent import router as dashboard_agent_router
from src.auth.dependencies import get_tenant_id
from src.auth.endpoints import auth_router
from src.connectors.adapters.registry import register_all_adapters
from src.services.dashboard_events import dashboard_event_broker
from src.services.order_status_updater import run_order_status_updater
from src.services.tenant_resolver import resolve_tenant_by_id, resolve_tenant_for_email, resolve_tenant_for_line

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_FRONTEND_URL = "https://storderaidev2.z11.web.core.windows.net/"
DEFAULT_AZURE_OPENAI_DEPLOYMENT = "gpt-5.4-mini"
LINE_TESTER_COOKIE_NAME = "line_tester_auth"
LineWebhookHandler: Any | None = None
PhoneCallHandler: Any | None = None


GRAPH_SUBSCRIPTION_EXPIRY_HOURS = 48
GRAPH_SUBSCRIPTION_RENEW_BUFFER_SECONDS = 3600

# モジュールレベルでsubscription IDを保持（lifecycle event時の再作成に使用）
_active_subscription_id: str | None = None


async def _cleanup_duplicate_graph_subscriptions(token: str, callback_url: str) -> None:
    """同じ notificationUrl を持つ既存 Subscription を全て削除する（重複蓄積防止）"""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://graph.microsoft.com/v1.0/subscriptions",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                logger.warning("Graph Subscription 一覧取得失敗: %s", resp.status_code)
                return
            subscriptions = resp.json().get("value", [])
            duplicates = [s for s in subscriptions if s.get("notificationUrl") == callback_url]
            if not duplicates:
                return
            logger.info("既存 Graph Subscription %d 件を削除します", len(duplicates))
            for sub in duplicates:
                sub_id = sub.get("id")
                del_resp = await client.delete(
                    f"https://graph.microsoft.com/v1.0/subscriptions/{sub_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if del_resp.status_code in (200, 204):
                    logger.info("Graph Subscription 削除完了: id=%s", sub_id)
                else:
                    logger.warning("Graph Subscription 削除失敗: id=%s status=%s", sub_id, del_resp.status_code)
    except Exception:
        logger.exception("Graph Subscription クリーンアップエラー")


async def _create_graph_subscription() -> str | None:
    """Graph APIのSubscriptionを作成し、メール受信通知を有効にする。
    作成前に同一 notificationUrl の既存 Subscription を全削除して重複蓄積を防ぐ。
    """
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

        # 作成前に同一 notificationUrl の既存 Subscription を全削除
        await _cleanup_duplicate_graph_subscriptions(token, callback_url)

        expiry = datetime.now(timezone.utc) + timedelta(hours=GRAPH_SUBSCRIPTION_EXPIRY_HOURS)

        payload = {
            "changeType": "created",
            "notificationUrl": callback_url,
            "resource": f"/users/{mailbox}/mailFolders('Inbox')/messages",
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
    """Subscriptionの自動更新ループ。更新失敗時は再作成を試みる"""
    consecutive_failures = 0
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
                    consecutive_failures = 0
                elif resp.status_code == 404:
                    logger.warning("Graph Subscription が存在しない（404）。再作成を試行")
                    await _recreate_graph_subscription()
                    return
                else:
                    consecutive_failures += 1
                    logger.error("Graph Subscription 更新失敗: %s %s", resp.status_code, resp.text)
                    if consecutive_failures >= 3:
                        logger.warning("連続3回更新失敗。Subscription再作成を試行")
                        await _recreate_graph_subscription()
                        return
        except Exception:
            consecutive_failures += 1
            logger.exception("Graph Subscription 更新エラー")
            if consecutive_failures >= 3:
                logger.warning("連続3回更新エラー。Subscription再作成を試行")
                await _recreate_graph_subscription()
                return


async def _recreate_graph_subscription() -> None:
    """Subscription削除・失効時に再作成する"""
    global _active_subscription_id  # noqa: PLW0603
    logger.info("Graph Subscription 再作成を開始")
    sub_id = await _create_graph_subscription()
    if sub_id:
        _active_subscription_id = sub_id
        asyncio.create_task(_renew_graph_subscription(sub_id))
        logger.info("Graph Subscription 再作成完了: id=%s", sub_id)
    else:
        logger.error("Graph Subscription 再作成に失敗")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _active_subscription_id  # noqa: PLW0603
    register_all_adapters()
    logger.info("Adapter registry initialized")

    renew_task = None
    sub_id = await _create_graph_subscription()
    if sub_id:
        _active_subscription_id = sub_id
        renew_task = asyncio.create_task(_renew_graph_subscription(sub_id))

    # 受注ステータス自動更新タスク（30分ごと）
    status_updater_task = asyncio.create_task(run_order_status_updater(["T-001", "T-002"]))

    yield

    status_updater_task.cancel()
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


class LineTesterMessageRequest(BaseModel):
    message: str = Field(..., min_length=1)
    customer_id: str | None = None
    customer_name: str | None = None
    session_id: str | None = None
    current_order_id: str | None = None
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    pending_order_draft: dict[str, Any] | None = None


def _line_tester_enabled() -> bool:
    return os.environ.get("LINE_TESTER_PUBLIC_ENABLED", "true").lower() == "true"


def _line_tester_tenant_id() -> str:
    return os.environ.get("LINE_TESTER_TENANT_ID", "T-001")


def _line_tester_access_code() -> str:
    return os.environ.get("LINE_TESTER_ACCESS_CODE", "test")


def _is_line_tester_authorized(request: Request) -> bool:
    return request.cookies.get(LINE_TESTER_COOKIE_NAME) == _line_tester_access_code()


def _ensure_line_tester_authorized(request: Request) -> None:
    if not _is_line_tester_authorized(request):
        raise HTTPException(status_code=401, detail="line tester access code is required")


def _ensure_line_tester_enabled() -> None:
    if not _line_tester_enabled():
        raise HTTPException(status_code=404, detail="line tester is disabled")


@app.get("/line-tester", response_class=HTMLResponse)
async def line_tester_page(request: Request):
    _ensure_line_tester_enabled()
    if not _is_line_tester_authorized(request):
        return """<!doctype html>
<html lang="ja">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>LINE Tester Unlock</title>
<style>body{font-family:Segoe UI,Meiryo,sans-serif;background:#f2f5f7;margin:0}.box{max-width:420px;margin:10vh auto;background:#fff;padding:20px;border-radius:10px;box-shadow:0 6px 16px rgba(0,0,0,.12)}input,button{font-size:14px;padding:10px}input{width:100%;box-sizing:border-box;margin:8px 0}button{width:100%}</style>
</head>
<body><div class="box"><h2>LINE Tester</h2><p>アクセスコードを入力してください。</p><input id="code" type="password" placeholder="code"><button id="unlock">入室</button><p id="msg" style="color:#b00020;"></p></div>
<script>
document.getElementById("unlock").addEventListener("click", async ()=>{
  const code = document.getElementById("code").value;
  const res = await fetch("/line-tester/unlock",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({code})});
  if(res.redirected){ location.href = res.url; return; }
  document.getElementById("msg").textContent = "コードが違います";
});
</script></body>
</html>"""
    return """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>foogent LINE テスター</title>
  <style>
    body{margin:0;font-family:Meiryo,Segoe UI,sans-serif;background:#7B9EBC}
    .wrap{max-width:640px;margin:0 auto;height:100vh;display:flex;flex-direction:column}
    .head{padding:12px;background:#6b8daa;color:#fff;display:flex;gap:8px;align-items:center}
    select,input,button{font-size:14px}
    .chat{flex:1;overflow:auto;padding:12px}
    .row{margin:8px 0;display:flex}
    .u{justify-content:flex-end}.a{justify-content:flex-start}
    .b{max-width:75%;padding:10px;border-radius:10px;white-space:pre-wrap}
    .u .b{background:#DCF8C6}.a .b{background:#fff}
    .t{font-size:11px;color:#eaf7ff;margin-top:2px}
    .u .t{text-align:right}.a .t{text-align:left}
    .foot{padding:10px;background:#e8eef3;display:flex;gap:8px}
    .foot input{flex:1;padding:8px}
    .debug-toggle{padding:6px 10px;background:#3d5a73;color:#fff;border:none;cursor:pointer;font-size:12px;border-radius:4px}
    .debug-panel{max-height:200px;overflow:auto;background:#1e1e1e;color:#d4d4d4;font-family:Consolas,monospace;font-size:12px;padding:8px;display:none}
    .debug-panel.open{display:block}
    .debug-panel .dl{padding:2px 0;border-bottom:1px solid #333}
    .debug-panel .dl .tag{color:#569cd6}.debug-panel .dl .msg{color:#ce9178}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="head">
      <label>顧客:</label>
      <select id="customer"></select>
      <span id="status">loading...</span>
    </div>
    <div id="chat" class="chat"></div>
    <div class="foot">
      <input id="msg" placeholder="メッセージを入力" />
      <button id="send">送信</button>
      <button id="reset">リセット</button>
      <button id="dbgToggle" class="debug-toggle">Debug</button>
    </div>
    <div id="debugPanel" class="debug-panel"></div>
  </div>
  <script>
    const st = {sessionId:newSessionId(), history:[], pending:null, currentOrderId:null, customerId:null, customerName:null, busy:false};
    const $ = (id)=>document.getElementById(id);
    const chat=$("chat"), status=$("status"), msg=$("msg"), send=$("send"), reset=$("reset"), customer=$("customer"), debugPanel=$("debugPanel"), dbgToggle=$("dbgToggle");
    dbgToggle.addEventListener("click", ()=>{ debugPanel.classList.toggle("open"); });
    function newSessionId(){ return "web-local-"+Date.now(); }
    function nowLabel(){
      const d = new Date();
      const hh = String(d.getHours()).padStart(2, "0");
      const mm = String(d.getMinutes()).padStart(2, "0");
      const ss = String(d.getSeconds()).padStart(2, "0");
      return `${hh}:${mm}:${ss}`;
    }
    function add(text, role){
      const r=document.createElement("div"); r.className="row "+(role==="user"?"u":"a");
      const box=document.createElement("div");
      const b=document.createElement("div"); b.className="b"; b.textContent=text; box.appendChild(b);
      const t=document.createElement("div"); t.className="t"; t.textContent=nowLabel(); box.appendChild(t);
      r.appendChild(box); chat.appendChild(r);
      chat.scrollTop=chat.scrollHeight;
    }
    function setBusy(v){ st.busy=v; send.disabled=v; msg.disabled=v; status.textContent=v?"処理中...":"ready"; }
    function showDebugLog(logs){
      debugPanel.innerHTML="";
      if(!logs.length){ debugPanel.innerHTML='<div class="dl" style="color:#666">（ログなし）</div>'; return; }
      const ts = nowLabel();
      const hdr = document.createElement("div"); hdr.className="dl"; hdr.innerHTML='<span class="tag">── '+ts+' ──</span>'; debugPanel.appendChild(hdr);
      for(const line of logs){
        const d=document.createElement("div"); d.className="dl";
        const m=line.match(/^(\[[^\]]+\])\s*(.*)/);
        if(m){ d.innerHTML='<span class="tag">'+m[1]+'</span> <span class="msg">'+m[2]+'</span>'; }
        else{ d.textContent=line; }
        debugPanel.appendChild(d);
      }
      debugPanel.scrollTop=debugPanel.scrollHeight;
    }
    async function loadCustomers(){
      const res = await fetch("/api/line-tester/customers"); const data = await res.json();
      customer.innerHTML = "";
      for (const c of data.customers){
        const o=document.createElement("option"); o.value=c.customer_id||""; o.textContent=c.label; o.dataset.name=c.customer_name||""; customer.appendChild(o);
      }
      status.textContent="ready";
    }
    customer.addEventListener("change", ()=>{
      st.customerId = customer.value || null;
      st.customerName = customer.options[customer.selectedIndex]?.dataset?.name || null;
      st.history=[]; st.pending=null; st.currentOrderId=null; st.sessionId=newSessionId(); chat.innerHTML="";
      add("顧客を切り替えました", "assistant");
    });
    async function sendMsg(){
      if(st.busy) return;
      const text = msg.value.trim(); if(!text) return;
      msg.value=""; add(text,"user"); setBusy(true);
      const payload = {
        message:text, customer_id:st.customerId, customer_name:st.customerName,
        session_id:st.sessionId, current_order_id:st.currentOrderId,
        conversation_history:st.history, pending_order_draft:st.pending
      };
      try{
        const res = await fetch("/api/line-tester/message",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
        const data = await res.json();
        add(data.response||"（応答なし）","assistant");
        st.sessionId = data.session_id || st.sessionId;
        st.history = data.conversation_history || st.history;
        st.pending = data.pending_order_draft || null;
        st.currentOrderId = data.current_order_id ?? st.currentOrderId;
        if (data.current_order_cleared === true) st.currentOrderId = null;
        showDebugLog(data.debug_log || []);
      }catch(e){
        add("エラー: "+e, "assistant");
      }finally{ setBusy(false); msg.focus(); }
    }
    send.addEventListener("click", sendMsg);
    msg.addEventListener("keydown", (e)=>{ if(e.key==="Enter") sendMsg(); });
    reset.addEventListener("click", ()=>{ st.history=[]; st.pending=null; st.currentOrderId=null; st.sessionId=newSessionId(); chat.innerHTML=""; add("会話をリセットしました","assistant");});
    loadCustomers().catch((e)=>{ status.textContent="error"; add("初期化エラー: "+e, "assistant");});
  </script>
</body>
</html>"""


@app.post("/line-tester/unlock")
async def line_tester_unlock(request: Request):
    _ensure_line_tester_enabled()
    body = await request.json()
    code = str(body.get("code", ""))
    if code != _line_tester_access_code():
        raise HTTPException(status_code=401, detail="invalid access code")
    response = RedirectResponse(url="/line-tester", status_code=303)
    response.set_cookie(key=LINE_TESTER_COOKIE_NAME, value=code, httponly=True, samesite="lax", max_age=60 * 60 * 8)
    return response


@app.get("/api/line-tester/customers")
async def line_tester_customers(request: Request):
    _ensure_line_tester_enabled()
    _ensure_line_tester_authorized(request)
    tenant_id = _line_tester_tenant_id()
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    repo = tenant_ctx.get_connector("ICustomerRepository")
    customers = await repo.list_all(tenant_id)
    items = [{"label": "ゲスト（顧客未指定）", "customer_id": None, "customer_name": None}]
    items.extend({"label": f"{c.id}: {c.name}", "customer_id": c.id, "customer_name": c.name} for c in customers)
    return {"tenant_id": tenant_id, "customers": items}


@app.post("/api/line-tester/message")
async def line_tester_message(request: Request, payload: LineTesterMessageRequest):
    _ensure_line_tester_enabled()
    _ensure_line_tester_authorized(request)
    tenant_id = _line_tester_tenant_id()
    tenant_ctx = resolve_tenant_by_id(tenant_id)

    from src.agents.orchestrator import OrderOrchestrator
    from src.models.order import Order
    from src.models.message_history import MessageHistory
    from src.models.order import OrderSource

    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    api_key = os.environ.get("AZURE_OPENAI_KEY", "")
    if not endpoint or not api_key:
        raise HTTPException(status_code=500, detail="AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_KEY is required")

    deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", DEFAULT_AZURE_OPENAI_DEPLOYMENT)
    orchestrator = OrderOrchestrator(
        tenant_ctx=tenant_ctx,
        azure_openai_endpoint=endpoint,
        azure_openai_key=api_key,
        deployment_name=deployment_name,
    )

    session_id = payload.session_id or f"web-local-{int(datetime.now(timezone.utc).timestamp())}"
    known_customer_id = payload.customer_id
    known_customer_name = payload.customer_name
    if not known_customer_id:
        from src.services.line_handler import _build_new_customer

        customer_repo = tenant_ctx.get_connector("ICustomerRepository")
        web_line_user_id = f"WEB-TESTER-{payload.session_id or 'anonymous'}"
        existing = await customer_repo.find_by_line_user_id(tenant_id, web_line_user_id)
        if existing:
            known_customer_id = existing.id
            known_customer_name = existing.name
        else:
            next_id = await customer_repo.next_customer_id(tenant_id)
            new_customer = _build_new_customer(tenant_id, next_id, line_user_id=web_line_user_id)
            new_customer = await customer_repo.create(tenant_id, new_customer)
            known_customer_id = new_customer.id
            known_customer_name = new_customer.name
    line_user_id = f"WEB-{known_customer_id}" if known_customer_id else "WEB-TESTER"

    history = [MessageHistory(**item) for item in payload.conversation_history]
    current_order: Order | None = None
    if payload.current_order_id:
        order_repo = tenant_ctx.get_connector("IOrderRepository")
        current_order = await order_repo.find_by_id(tenant_id, payload.current_order_id)
        if current_order and current_order.customer_id != payload.customer_id:
            current_order = None

    result = await orchestrator.process_order_message(
        message=payload.message,
        line_user_id=line_user_id,
        reply_token=None,
        source=OrderSource.LINE,
        conversation_history=history,
        pending_order_draft=payload.pending_order_draft,
        session_id=session_id,
        known_customer_id=known_customer_id,
        known_customer_name=known_customer_name,
        current_order=current_order,
    )

    response_text = result.get("response", "")
    base_index = len(history)
    history.append(
        MessageHistory(
            id=f"web-user-{base_index}",
            tenant_id=tenant_id,
            session_id=session_id,
            channel="line",
            channel_user_id=line_user_id,
            role="user",
            text=payload.message,
        )
    )
    history.append(
        MessageHistory(
            id=f"web-assistant-{base_index + 1}",
            tenant_id=tenant_id,
            session_id=session_id,
            channel="line",
            channel_user_id=line_user_id,
            role="assistant",
            text=response_text,
        )
    )

    pending = result.get("pending_order_draft")
    if result.get("order_saved") is True:
        pending = None
    return {
        "response": response_text,
        "session_id": session_id,
        "pending_order_draft": pending,
        "conversation_history": [h.model_dump(mode="json") for h in history],
        "order_id": result.get("order_id"),
        "order_saved": result.get("order_saved", False),
        "current_order_id": result.get("current_order_id"),
        "current_order_cleared": result.get("current_order_cleared", False),
        "debug_log": result.get("debug_log", []),
    }


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

    # lifecycle notification対応（subscriptionRemoved / missed）
    for notification in notifications:
        lifecycle_event = notification.get("lifecycleNotification") or notification.get("lifecycleEvent")
        if lifecycle_event:
            event_type = lifecycle_event if isinstance(lifecycle_event, str) else str(lifecycle_event)
            logger.warning("Graph lifecycle notification受信: %s", event_type)
            if event_type in ("subscriptionRemoved", "missed"):
                background_tasks.add_task(_recreate_graph_subscription)
            return Response(status_code=202)

    default_recipient = os.environ.get("GRAPH_MAILBOX_ADDRESS", "order@example.com")
    azure_openai_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_key = os.environ.get("AZURE_OPENAI_KEY", "")

    # 同一リクエスト内での重複 message_id はここでスキップ（複数 subscription が同一 value に混入する場合の防御）
    queued_message_ids: set[str] = set()
    for notification in notifications:
        resource_data = notification.get("resourceData", {}) or {}
        message_id = resource_data.get("id")
        if not message_id:
            continue
        if message_id in queued_message_ids:
            logger.info("Email webhook: 同一リクエスト内重複をスキップ: message_id=%s", message_id)
            continue
        queued_message_ids.add(message_id)
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
    with_audio: bool = False
    customer_id: str | None = None


class WebPhoneGreetingRequest(BaseModel):
    caller_number: str = "+81312345678"
    called_number: str = "+81501234567"
    customer_id: str | None = None


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
        customer_id=payload.customer_id,
    )
    if payload.disconnect:
        disconnect_result = await handler.disconnect_demo_call(result["call_connection_id"])
        result["disconnect"] = disconnect_result
    return result


# ── Web phone endpoints (JWT protected) ──────────────────────────────────────

_speech_service: Any | None = None


def _get_speech_service() -> Any:
    global _speech_service  # noqa: PLW0603
    if _speech_service is None:
        from src.services.speech_service import SpeechService

        key = os.environ.get("SPEECH_SERVICE_KEY", "")
        region = os.environ.get("SPEECH_SERVICE_REGION", "")
        if not key or not region:
            raise HTTPException(
                status_code=503,
                detail="SPEECH_SERVICE_KEY / SPEECH_SERVICE_REGION not configured",
            )
        _speech_service = SpeechService(speech_key=key, speech_region=region)
    return _speech_service


@app.get("/api/speech-token")
async def speech_token(tenant_id: str = Depends(get_tenant_id)):
    """Issue a short-lived token for Azure Speech SDK in the browser."""
    svc = _get_speech_service()
    token = await svc.issue_token()
    region = os.environ.get("SPEECH_SERVICE_REGION", "")
    return {"token": token, "region": region}


@app.post("/api/web-phone/greeting")
async def web_phone_greeting(
    payload: WebPhoneGreetingRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    """Start a web phone call and return greeting audio."""
    import base64

    from src.services.phone_handler import GREETING_MESSAGE

    handler = _get_phone_handler()
    call_connection_id = handler.init_demo_call(
        caller_number=payload.caller_number,
        called_number=payload.called_number,
        customer_id=payload.customer_id,
    )

    try:
        svc = _get_speech_service()
        audio_bytes = await svc.synthesize(GREETING_MESSAGE)
        audio_b64 = base64.b64encode(audio_bytes).decode()
    except Exception:
        logger.exception("TTS failed for greeting")
        audio_b64 = ""

    return {
        "text": GREETING_MESSAGE,
        "audio": audio_b64,
        "call_connection_id": call_connection_id,
    }


@app.post("/api/web-phone/message")
async def web_phone_message(
    payload: PhoneDemoMessageRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    """Web phone endpoint: inject a phone utterance without ACS/EventGrid auth."""
    handler = _get_phone_handler()
    result = await handler.process_demo_message(
        message=payload.message,
        caller_number=payload.caller_number,
        called_number=payload.called_number,
        call_connection_id=payload.call_connection_id,
        customer_id=payload.customer_id,
    )
    if payload.disconnect:
        disconnect_result = await handler.disconnect_demo_call(result["call_connection_id"])
        result["disconnect"] = disconnect_result

    if payload.with_audio and result.get("response"):
        import base64

        try:
            svc = _get_speech_service()
            audio_bytes = await svc.synthesize(result["response"])
            result["response_audio"] = base64.b64encode(audio_bytes).decode()
        except Exception:
            logger.exception("TTS failed for response")
            result["response_audio"] = ""

    return result


@app.post("/api/web-phone/disconnect")
async def web_phone_disconnect(
    payload: dict,
    tenant_id: str = Depends(get_tenant_id),
):
    """Disconnect a web phone call by call_connection_id."""
    call_connection_id = payload.get("call_connection_id", "")
    if not call_connection_id:
        raise HTTPException(status_code=400, detail="call_connection_id is required")
    handler = _get_phone_handler()
    result = await handler.disconnect_demo_call(call_connection_id)
    return result or {"status": "disconnected", "call_connection_id": call_connection_id}


# ── Protected business endpoints ──────────────────────────────────────────────


@app.get("/api/orders")
async def list_orders(
    tenant_id: str = Depends(get_tenant_id),
    delivery_date: str | None = None,
    order_date: str | None = None,
    status: str | None = None,
    source: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    repo = tenant_ctx.get_connector("IOrderRepository")

    target: date | None = None
    if order_date:
        target = date.fromisoformat(order_date)
        date_field = "order_date"
    elif delivery_date:
        target = date.fromisoformat(delivery_date)
        date_field = "delivery_date"
    else:
        date_field = "order_date"

    orders, total = await repo.list_orders(
        tenant_id,
        target,
        status=status,
        source=source,
        q=q,
        limit=limit,
        offset=offset,
        date_field=date_field,
    )
    return {
        "orders": [o.model_dump(mode="json") for o in orders],
        "date": target.isoformat() if target else None,
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": {
            "status": status,
            "source": source,
            "q": q,
        },
    }


@app.get("/api/orders/events")
async def stream_order_events(tenant_id: str = Depends(get_tenant_id)):
    return StreamingResponse(
        dashboard_event_broker.subscribe(tenant_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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


class OrderMemoUpdate(BaseModel):
    memo: str | None = None


@app.put("/api/orders/{order_id}/memo")
async def update_order_memo(
    order_id: str,
    payload: OrderMemoUpdate,
    tenant_id: str = Depends(get_tenant_id),
):
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    repo = tenant_ctx.get_connector("IOrderRepository")
    order = await repo.find_by_id(tenant_id, order_id)
    if not order:
        raise HTTPException(
            status_code=404,
            detail=f"受注ID「{order_id}」が見つかりません。IDをご確認ください。",
        )
    memo = (payload.memo or "").strip() or None
    updated = await repo.update_memo(tenant_id, order_id, memo)
    await dashboard_event_broker.publish(
        "order_updated",
        tenant_id,
        {
            "order_id": updated.id,
            "customer_name": updated.customer_name,
            "reason": "memo_updated",
            "delivery_date": updated.delivery_date.isoformat() if updated.delivery_date else None,
            "order_date": updated.order_date.isoformat(),
        },
    )
    return updated.model_dump(mode="json")


class OrderStatusUpdate(BaseModel):
    status: str


_STATUS_UPDATE_TERMINAL: frozenset[str] = frozenset({"完了", "キャンセル"})


@app.put("/api/orders/{order_id}/status")
async def update_order_status(
    order_id: str,
    payload: OrderStatusUpdate,
    tenant_id: str = Depends(get_tenant_id),
):
    from src.models.order import OrderStatus

    try:
        new_status = OrderStatus(payload.status)
    except ValueError:
        valid = ", ".join(s.value for s in OrderStatus)
        raise HTTPException(
            status_code=400,
            detail=f"不正なステータスです: '{payload.status}'。有効な値: {valid}",
        ) from None

    tenant_ctx = resolve_tenant_by_id(tenant_id)
    repo = tenant_ctx.get_connector("IOrderRepository")
    order = await repo.find_by_id(tenant_id, order_id)
    if not order:
        raise HTTPException(
            status_code=404,
            detail=f"受注ID「{order_id}」が見つかりません。IDをご確認ください。",
        )

    # 完了・キャンセル済みの再オープンは禁止
    if order.status.value in _STATUS_UPDATE_TERMINAL and new_status != order.status:
        raise HTTPException(
            status_code=409,
            detail=f"ステータス「{order.status.value}」の受注は変更できません。",
        )

    if order.status == new_status:
        return order.model_dump(mode="json")

    await repo.update_status(tenant_id, order_id, new_status)
    updated = await repo.find_by_id(tenant_id, order_id)
    if not updated:
        raise HTTPException(status_code=500, detail="ステータス更新後の受注取得に失敗しました。")

    await dashboard_event_broker.publish(
        "order_updated",
        tenant_id,
        {
            "order_id": updated.id,
            "customer_name": updated.customer_name,
            "reason": "status_updated",
            "delivery_date": updated.delivery_date.isoformat() if updated.delivery_date else None,
            "order_date": updated.order_date.isoformat(),
        },
    )
    return updated.model_dump(mode="json")


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
    for rsid in order.related_session_ids or []:
        messages.extend(await history_repo.list_by_session_id(tenant_id, rsid))
    messages.sort(key=lambda m: m.created_at)
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


@app.get("/api/products/suggest")
async def suggest_products(q: str, tenant_id: str = Depends(get_tenant_id)):
    """AI Search の Suggester によるオートコンプリート。未構成時は空配列を返す。"""
    tenant_ctx = resolve_tenant_by_id(tenant_id)
    master = tenant_ctx.get_connector("IProductMaster")
    if hasattr(master, "suggest"):
        suggestions = await master.suggest(tenant_id, q)
        return {"suggestions": suggestions}
    return {"suggestions": []}


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
