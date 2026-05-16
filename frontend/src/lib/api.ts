const API_BASE = "";

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
  const resp = await fetch(`${API_BASE}/api/orders?delivery_date=${date}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return data.orders || [];
}

export async function fetchCustomers(): Promise<Customer[]> {
  const resp = await fetch(`${API_BASE}/api/customers`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return data.customers || [];
}

export async function updateCustomer(
  customerId: string,
  fields: Partial<Customer>
): Promise<Customer> {
  const resp = await fetch(`${API_BASE}/api/customers/${customerId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}
