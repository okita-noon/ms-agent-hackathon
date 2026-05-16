import type { Order, Customer } from "./api";

export function getDemoOrders(): Order[] {
  const today = new Date().toISOString().split("T")[0];
  return [
    { uid: "ORD-001", tenant_id: "T-001", order_date: today, delivery_date: today, customer_id: "C-001", customer_name: "株式会社A", source: "LINE", items: [{ product_name: "りんご", quantity: 10, unit: "箱", temperature_zone: "冷蔵" }, { product_name: "バナナ", quantity: 20, unit: "kg", temperature_zone: "常温" }], delivery_carrier: "自社便", delivery_route: "北関東便", status: "未処理", remarks: undefined },
    { uid: "ORD-002", tenant_id: "T-001", order_date: today, delivery_date: today, customer_id: "C-002", customer_name: "株式会社B", source: "LINE", items: [{ product_name: "もも", quantity: 5, unit: "箱", temperature_zone: "冷蔵" }], delivery_carrier: "芦川便", delivery_route: "西日本便", status: "完了", remarks: undefined },
    { uid: "ORD-003", tenant_id: "T-001", order_date: today, delivery_date: today, customer_id: "C-003", customer_name: "株式会社C", source: "Phone", items: [{ product_name: "メロン", quantity: 3, unit: "玉", temperature_zone: "冷凍" }], delivery_carrier: "自社便", delivery_route: "中部便", status: "製造", remarks: undefined },
    { uid: "ORD-004", tenant_id: "T-001", order_date: today, delivery_date: today, customer_id: "C-004", customer_name: "株式会社D", source: "LINE", items: [{ product_name: "いちご", quantity: 15, unit: "パック", temperature_zone: "常温" }, { product_name: "ぶどう", quantity: 8, unit: "房", temperature_zone: "常温" }], delivery_carrier: "自社便", delivery_route: "九州便", status: "配送", remarks: undefined },
    { uid: "ORD-005", tenant_id: "T-001", order_date: today, delivery_date: today, customer_id: "C-005", customer_name: "株式会社E", source: "Phone", items: [{ product_name: "みかん", quantity: 100, unit: "個", temperature_zone: "冷凍" }], delivery_carrier: "冷凍ヤマト便", delivery_route: "北海道便", status: "返信待ち", remarks: "数量確認中" },
    { uid: "ORD-006", tenant_id: "T-001", order_date: today, delivery_date: today, customer_id: "C-006", customer_name: "株式会社F", source: "LINE", items: [{ product_name: "レモン", quantity: 30, unit: "個", temperature_zone: "常温" }], delivery_carrier: "自社便", delivery_route: "東北便", status: "完了", remarks: undefined },
  ];
}

export function getDemoCustomers(): Customer[] {
  return [
    { id: "C-001", tenant_id: "T-001", name: "株式会社テスト", short_name: "テスト社", line_user_id: undefined, phone: "03-1234-5678", email: "test@example.com", active: true },
    { id: "C-002", tenant_id: "T-001", name: "株式会社サンプル", short_name: "サンプル社", line_user_id: "U1234567890abcdef", phone: "06-9876-5432", email: undefined, active: true },
    { id: "C-003", tenant_id: "T-001", name: "有限会社デモ", short_name: "デモ社", line_user_id: undefined, phone: undefined, email: "demo@example.com", active: true },
  ];
}
