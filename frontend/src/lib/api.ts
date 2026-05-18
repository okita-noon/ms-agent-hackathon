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
  const resp = await authFetch(`${API_BASE}/api/orders/${orderId}/messages`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export interface AgentFeatures {
  dashboard_agent: boolean;
  exception_triage?: boolean;
  resolution_agent?: boolean;
  resolution_execute?: boolean;
  demo_mode?: boolean;
}

export type AgentExceptionSeverity = "critical" | "high" | "medium" | "low" | string;

export interface AgentEvidence {
  label: string;
  value: string;
  source?: string;
}

export interface AgentExceptionCase {
  id: string;
  order_id?: string;
  customer?: {
    id: string;
    name: string;
  };
  customer_name?: string;
  type?: string;
  title: string;
  summary?: string;
  reason?: string;
  severity: AgentExceptionSeverity;
  priority?: number;
  status?: string;
  evidence?: AgentEvidence[];
  suggested_action?: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
}

export interface AgentResolutionPreview {
  exception_id?: string;
  title: string;
  summary: string;
  confidence?: number;
  recommended_actions?: string[];
  proposed_actions?: Array<{ type: string; label: string; payload?: Record<string, unknown> }>;
  customer_message?: string;
  evidence?: AgentEvidence[];
  requires_approval?: boolean;
}

function normalizeFeatureFlags(data: unknown): AgentFeatures {
  const obj = (data && typeof data === "object" ? data : {}) as Record<string, unknown>;
  const features = (obj.features && typeof obj.features === "object" ? obj.features : obj) as Record<string, unknown>;
  const dashboardAgent = features.dashboard_agent ?? features.dashboardAgent ?? features.agent_dashboard;
  return {
    dashboard_agent: dashboardAgent === true || dashboardAgent === "true" || dashboardAgent === 1,
    exception_triage: features.exception_triage === undefined ? undefined : features.exception_triage === true,
    resolution_agent: features.resolution_agent === undefined ? undefined : features.resolution_agent === true,
    resolution_execute: features.resolution_execute === undefined ? undefined : features.resolution_execute === true,
    demo_mode: features.demo_mode === undefined ? undefined : features.demo_mode === true,
  };
}

function normalizeEvidence(value: unknown): AgentEvidence[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      if (typeof item === "string") return { label: "根拠", value: item };
      if (!item || typeof item !== "object") return null;
      const row = item as Record<string, unknown>;
      return {
        label: String(row.label ?? row.name ?? row.type ?? "根拠"),
        value: String(row.value ?? row.text ?? row.summary ?? ""),
        source: row.source === undefined ? undefined : String(row.source),
      };
    })
    .filter((item): item is AgentEvidence => Boolean(item?.value));
}

function normalizeExceptionCase(item: unknown, index: number): AgentExceptionCase | null {
  if (!item || typeof item !== "object") return null;
  const row = item as Record<string, unknown>;
  const id = row.id ?? row.exception_id ?? row.case_id ?? row.order_id ?? `exception-${index}`;
  const title = row.title ?? row.reason ?? row.type ?? row.summary;
  const customer = row.customer && typeof row.customer === "object" ? row.customer as Record<string, unknown> : null;
  if (!title) return null;
  return {
    id: String(id),
    order_id: row.order_id === undefined ? undefined : String(row.order_id),
    customer: customer ? { id: String(customer.id ?? ""), name: String(customer.name ?? "") } : undefined,
    customer_name: row.customer_name === undefined ? (customer?.name === undefined ? undefined : String(customer.name)) : String(row.customer_name),
    type: row.type === undefined ? undefined : String(row.type),
    title: String(title),
    summary: row.summary === undefined ? (row.reason === undefined ? undefined : String(row.reason)) : String(row.summary),
    reason: row.reason === undefined ? undefined : String(row.reason),
    severity: String(row.severity ?? row.priority_label ?? "medium"),
    priority: typeof row.priority === "number" ? row.priority : undefined,
    status: row.status === undefined ? undefined : String(row.status),
    evidence: normalizeEvidence(row.evidence ?? row.signals),
    suggested_action: row.suggested_action === undefined ? undefined : String(row.suggested_action),
    metadata: row.metadata && typeof row.metadata === "object" ? row.metadata as Record<string, unknown> : undefined,
    created_at: row.created_at === undefined ? undefined : String(row.created_at),
  };
}

export async function fetchAgentFeatures(): Promise<AgentFeatures> {
  const resp = await authFetch(`${API_BASE}/api/agent/features`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return normalizeFeatureFlags(await resp.json());
}

export async function fetchAgentExceptions(date: string): Promise<AgentExceptionCase[]> {
  const resp = await authFetch(`${API_BASE}/api/agent/exceptions?delivery_date=${encodeURIComponent(date)}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  const rawCases = Array.isArray(data) ? data : data.exceptions ?? data.cases ?? [];
  if (!Array.isArray(rawCases)) return [];
  return rawCases
    .map((item, index) => normalizeExceptionCase(item, index))
    .filter((item): item is AgentExceptionCase => Boolean(item))
    .sort((a, b) => (a.priority ?? 999) - (b.priority ?? 999));
}

export async function previewAgentResolution(exceptionCase: AgentExceptionCase): Promise<AgentResolutionPreview> {
  const resp = await authFetch(`${API_BASE}/api/agent/resolutions/preview`, {
    method: "POST",
    body: JSON.stringify({ exception_case: exceptionCase }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = (await resp.json()) as Record<string, unknown>;
  const preview = (data.preview && typeof data.preview === "object" ? data.preview : data) as Record<string, unknown>;
  const proposedActions = Array.isArray(preview.proposed_actions)
    ? preview.proposed_actions
        .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
        .map((item) => ({
          type: String(item.type ?? "action"),
          label: String(item.label ?? ""),
          payload: item.payload && typeof item.payload === "object" ? item.payload as Record<string, unknown> : undefined,
        }))
        .filter((item) => item.label)
    : [];
  return {
    exception_id: preview.exception_id === undefined ? exceptionCase.id : String(preview.exception_id),
    title: String(preview.title ?? "解決プレビュー"),
    summary: String(preview.summary ?? preview.recommendation ?? ""),
    confidence: typeof preview.confidence === "number" ? preview.confidence : undefined,
    recommended_actions: Array.isArray(preview.recommended_actions)
      ? preview.recommended_actions.map(String)
      : proposedActions.length > 0
        ? proposedActions.map((action) => action.label)
      : Array.isArray(preview.actions)
        ? preview.actions.map(String)
        : [],
    proposed_actions: proposedActions,
    customer_message: preview.customer_message === undefined ? undefined : String(preview.customer_message),
    evidence: normalizeEvidence(preview.evidence),
    requires_approval: preview.requires_approval === undefined ? undefined : preview.requires_approval === true,
  };
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
