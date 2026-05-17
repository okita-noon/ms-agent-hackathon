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
  yamato_tracking_number?: string;
  status: string;
  preparation_date?: string;
  remarks?: string;
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
