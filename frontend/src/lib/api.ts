import { getStoredToken } from "../auth/token";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  // Cookie がクロスサイトでブロックされるプライベートウィンドウ向けに
  // sessionStorage 上の Bearer トークンを併送する。
  // バックエンドは Authorization ヘッダ優先 → Cookie の順で解釈する（src/auth/dependencies.py）。
  const token = getStoredToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

const FETCH_TIMEOUT_MS = 30_000;

async function authFetch(url: string, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const resp = await fetch(url, {
      ...init,
      signal: controller.signal,
      credentials: "include",
      headers: { ...getHeaders(), ...init?.headers },
    });
    if (resp.status === 401) {
      window.dispatchEvent(new Event("auth:token-expired"));
    }
    return resp;
  } finally {
    clearTimeout(timer);
  }
}

export interface OrderItem {
  product_name: string;
  quantity: number;
  unit: string;
  temperature_zone: string;
}

export interface Order {
  uid: string;
  id?: string;
  tenant_id: string;
  order_date: string;
  delivery_date?: string;
  customer_id: string;
  customer_name: string;
  source: string;
  items: OrderItem[];
  delivery_carrier?: string;
  delivery_route?: string;
  delivery_time_slot?: string;
  yamato_tracking_number?: string;
  status: string;
  preparation_date?: string;
  remarks?: string;
  memo?: string;
  session_id?: string;
  created_at?: string;
  updated_at?: string;
}

export interface OrderFilters {
  status?: string;
  source?: string;
  q?: string;
  limit?: number;
  offset?: number;
  date_field?: "delivery_date" | "order_date";
}

export interface OrdersResponse {
  orders: Order[];
  date: string | null;
  total: number;
  limit: number;
  offset: number;
}

export type OrderEventType = "connected" | "order_created" | "order_updated";

export interface OrderEventPayload {
  order_id?: string;
  tenant_id?: string;
  customer_id?: string;
  customer_name?: string;
  source?: string;
  status?: string;
  reason?: string;
  delivery_date?: string | null;
  order_date?: string;
  created_at?: string;
}

export function createOrderEventSource(): EventSource {
  return new EventSource(`${API_BASE}/api/orders/events`, { withCredentials: true });
}

export type DeliveryLeadTime = "当日" | "翌日" | "中1日" | "中2日";

export const DELIVERY_LEAD_TIME_OPTIONS: DeliveryLeadTime[] = [
  "当日",
  "翌日",
  "中1日",
  "中2日",
];


export interface Customer {
  id: string;
  tenant_id: string;
  name: string;
  short_name?: string | null;
  line_user_id?: string | null;
  email?: string | null;
  phone?: string | null;
  fax?: string | null;
  delivery_lead_time?: DeliveryLeadTime | null;
  active: boolean;
}

export async function updateOrderMemo(orderId: string, memo: string | null): Promise<Order> {
  const resp = await authFetch(`${API_BASE}/api/orders/${orderId}/memo`, {
    method: "PUT",
    body: JSON.stringify({ memo }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function updateOrderStatus(orderId: string, status: string): Promise<Order> {
  const resp = await authFetch(`${API_BASE}/api/orders/${orderId}/status`, {
    method: "PUT",
    body: JSON.stringify({ status }),
  });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return resp.json();
}


export async function fetchOrders(
  date: string | null,
  filters: OrderFilters = {}
): Promise<OrdersResponse> {
  const params = new URLSearchParams();
  if (date) {
    const paramKey = filters.date_field === "order_date" ? "order_date" : "delivery_date";
    params.set(paramKey, date);
  }
  if (filters.status) params.set("status", filters.status);
  if (filters.source) params.set("source", filters.source);
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.offset) params.set("offset", String(filters.offset));

  const resp = await authFetch(`${API_BASE}/api/orders?${params.toString()}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  const orders = data.orders || [];
  return {
    orders,
    date: data.date || date,
    total: data.total ?? orders.length,
    limit: data.limit ?? filters.limit ?? orders.length,
    offset: data.offset ?? filters.offset ?? 0,
  };
}

export async function fetchCustomers(): Promise<Customer[]> {
  const resp = await authFetch(`${API_BASE}/api/customers`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return data.customers || [];
}

export interface InventoryItem {
  product_id: string;
  product_name: string;
  category: string | null;
  temperature_zone: string;
  quantity: number;
  unit: string;
  is_variable_weight: boolean;
  price_per_unit: number | null;
}

export async function fetchInventory(): Promise<InventoryItem[]> {
  const resp = await authFetch(`${API_BASE}/api/inventory`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return data.inventory || [];
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  channel: string;
  created_at: string;
}

export async function fetchOrderMessages(
  orderId: string,
  order?: Order,
): Promise<{ messages: Message[]; session_id: string | null }> {
  try {
    const resp = await authFetch(`${API_BASE}/api/orders/${orderId}/messages`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (data.messages.length === 0) {
      const { getDemoMessages } = await import("./demo");
      const demoMsgs = getDemoMessages(orderId, order);
      if (demoMsgs.length > 0) {
        return { messages: demoMsgs, session_id: `demo-${orderId}` };
      }
    }
    return data;
  } catch {
    const { getDemoMessages } = await import("./demo");
    const demoMsgs = getDemoMessages(orderId, order);
    return { messages: demoMsgs, session_id: demoMsgs.length > 0 ? `demo-${orderId}` : null };
  }
}

export interface AgentFeatures {
  dashboard_agent: boolean;
  exception_triage: boolean;
  resolution_agent: boolean;
  resolution_execute: boolean;
  demo_mode: boolean;
}

export type AgentExceptionType =
  | "quantity_anomaly"
  | "unit_anomaly"
  | "inventory_shortage"
  | "needs_review"
  | "awaiting_reply";

export type AgentExceptionSeverity = "high" | "medium" | "low";

export interface AgentEvidence {
  label: string;
  value: string;
}

export interface AgentExceptionCase {
  id: string;
  order_id: string;
  customer_id: string;
  customer_name: string;
  type: AgentExceptionType;
  severity: AgentExceptionSeverity;
  title: string;
  summary: string;
  suggested_action: string;
  evidence: AgentEvidence[];
  metadata: Record<string, unknown>;
}

export interface AgentResolutionPreview {
  exception_id: string;
  title: string;
  summary: string;
  confidence: number;
  recommended_actions: string[];
  customer_message: string;
  requires_approval: boolean;
}

export interface AgentExceptionsResponse {
  enabled: boolean;
  date: string | null;
  date_field: "delivery_date" | "order_date" | null;
  filters?: {
    status?: string | null;
    source?: string | null;
    q?: string | null;
    limit?: number;
    offset?: number;
  };
  cases: AgentExceptionCase[];
}

export interface AgentResolutionResponse {
  enabled: boolean;
  execute_enabled: boolean;
  preview: AgentResolutionPreview | null;
}

export async function fetchAgentFeatures(): Promise<AgentFeatures> {
  const resp = await authFetch(`${API_BASE}/api/agent/features`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return (await resp.json()) as AgentFeatures;
}

export async function fetchAgentExceptions(
  date: string | null,
  filters: OrderFilters = {},
): Promise<AgentExceptionsResponse> {
  const params = new URLSearchParams();
  if (date) {
    const paramKey = filters.date_field === "order_date" ? "order_date" : "delivery_date";
    params.set(paramKey, date);
  }
  if (filters.status) params.set("status", filters.status);
  if (filters.source) params.set("source", filters.source);
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.offset) params.set("offset", String(filters.offset));

  const resp = await authFetch(`${API_BASE}/api/agent/exceptions?${params.toString()}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return (await resp.json()) as AgentExceptionsResponse;
}

export async function previewAgentResolution(
  exceptionCase: AgentExceptionCase
): Promise<AgentResolutionResponse> {
  const resp = await authFetch(`${API_BASE}/api/agent/resolutions/preview`, {
    method: "POST",
    body: JSON.stringify({ exception_case: exceptionCase }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return (await resp.json()) as AgentResolutionResponse;
}

export interface WebPhoneRequest {
  message: string;
  caller_number?: string;
  called_number?: string;
  call_connection_id?: string;
  disconnect?: boolean;
  with_audio?: boolean;
  customer_id?: string;
}

export interface WebPhoneResponse {
  call_connection_id: string;
  status?: string;
  order_id?: string | null;
  review_order_id?: string | null;
  order_saved?: boolean;
  response?: string;
  response_audio?: string;
  session_status?: string;
  demo_mode?: boolean;
  error?: string;
  disconnect?: Record<string, unknown>;
}

export interface WebPhoneGreetingResponse {
  text: string;
  audio: string;
  call_connection_id: string;
}

export async function fetchSpeechToken(): Promise<{ token: string; region: string }> {
  const resp = await authFetch(`${API_BASE}/api/speech-token`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function webPhoneGreeting(req: {
  caller_number?: string;
  called_number?: string;
  customer_id?: string;
}): Promise<WebPhoneGreetingResponse> {
  const resp = await authFetch(`${API_BASE}/api/web-phone/greeting`, {
    method: "POST",
    body: JSON.stringify(req),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function webPhoneSendMessage(
  req: WebPhoneRequest,
): Promise<WebPhoneResponse> {
  const resp = await authFetch(`${API_BASE}/api/web-phone/message`, {
    method: "POST",
    body: JSON.stringify(req),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function webPhoneDisconnect(
  callConnectionId: string,
): Promise<WebPhoneResponse> {
  const resp = await authFetch(`${API_BASE}/api/web-phone/disconnect`, {
    method: "POST",
    body: JSON.stringify({ call_connection_id: callConnectionId }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function updateCustomer(
  customerId: string,
  fields: Partial<Customer>
): Promise<Customer> {
  const resp = await authFetch(
    `${API_BASE}/api/customers/${customerId}`,
    {
      method: "PUT",
      body: JSON.stringify(fields),
    }
  );
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}
