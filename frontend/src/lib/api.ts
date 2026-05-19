const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const TOKEN_KEY = "foogent_token";

function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

async function authFetch(url: string, init?: RequestInit): Promise<Response> {
  const resp = await fetch(url, {
    ...init,
    headers: { ...getHeaders(), ...init?.headers },
  });
  if (resp.status === 401) {
    localStorage.removeItem(TOKEN_KEY);
    window.location.href = `${window.location.origin}/dashboard/`;
  }
  return resp;
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
  session_id?: string;
}

export interface Customer {
  id: string;
  tenant_id: string;
  name: string;
  short_name?: string;
  line_user_id?: string;
  email?: string;
  phone?: string;
  fax?: string;
  active: boolean;
}

export async function fetchOrders(date: string): Promise<Order[]> {
  const resp = await authFetch(
    `${API_BASE}/api/orders?delivery_date=${date}`
  );
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return data.orders || [];
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
  orderId: string
): Promise<{ messages: Message[]; session_id: string | null }> {
  try {
    const resp = await authFetch(`${API_BASE}/api/orders/${orderId}/messages`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    if (data.messages.length === 0) {
      const { getDemoMessages } = await import("./demo");
      const demoMsgs = getDemoMessages(orderId);
      if (demoMsgs.length > 0) {
        return { messages: demoMsgs, session_id: `demo-${orderId}` };
      }
    }
    return data;
  } catch {
    const { getDemoMessages } = await import("./demo");
    const demoMsgs = getDemoMessages(orderId);
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
  delivery_date: string;
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

export async function fetchAgentExceptions(date: string): Promise<AgentExceptionsResponse> {
  const resp = await authFetch(
    `${API_BASE}/api/agent/exceptions?delivery_date=${encodeURIComponent(date)}`
  );
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
