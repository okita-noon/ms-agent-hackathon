import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { ALL_STATUS_FILTER, countAcceptedOrders, filterOrdersByStatus } from "../src/lib/orderFilters.ts";
import type { Order } from "../src/lib/api.ts";

function order(uid: string, status: string): Order {
  return {
    uid,
    tenant_id: "T-001",
    order_date: "2026-05-19",
    customer_id: `C-${uid}`,
    customer_name: `顧客${uid}`,
    source: "LINE",
    items: [],
    status,
  };
}

describe("order status filters", () => {
  const orders = [
    order("ORD-001", "未処理"),
    order("ORD-002", "要対応"),
    order("ORD-003", "完了"),
  ];

  it("returns all orders when the all filter is selected", () => {
    assert.deepEqual(filterOrdersByStatus(orders, ALL_STATUS_FILTER), orders);
  });

  it("filters orders by the selected status", () => {
    assert.deepEqual(
      filterOrdersByStatus(orders, "要対応").map((o) => o.uid),
      ["ORD-002"]
    );
  });

  it("returns an empty list when no order has the selected status", () => {
    assert.deepEqual(filterOrdersByStatus(orders, "配送"), []);
  });

  it("counts accepted orders independently from review statuses", () => {
    assert.equal(countAcceptedOrders(orders, new Set(["未処理", "製造", "配送", "完了"])), 2);
  });
});
