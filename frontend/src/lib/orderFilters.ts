import type { Order } from "./api";

export const ALL_STATUS_FILTER = "all";

export function filterOrdersByStatus(orders: Order[], statusFilter: string): Order[] {
  if (statusFilter === ALL_STATUS_FILTER) return orders;
  return orders.filter((order) => order.status === statusFilter);
}

export function countAcceptedOrders(orders: Order[], acceptedStatuses: Set<string>): number {
  return orders.filter((order) => acceptedStatuses.has(order.status)).length;
}
