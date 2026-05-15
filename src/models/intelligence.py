from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ResolvedItem(BaseModel):
    product_id: str
    product_name: str
    qty: float
    unit: str


class OrderPattern(BaseModel):
    id: str | None = None
    tenant_id: str
    customer_id: str
    type: str = "single"
    input_expression: str
    input_expression_normalized: str
    input_embedding: list[float] = Field(default_factory=list)
    resolved_items: list[ResolvedItem] = Field(default_factory=list)
    confidence: float = 0.7
    occurrence_count: int = 1
    last_confirmed_at: datetime = Field(default_factory=datetime.utcnow)
    source: str = "customer_confirmed"


class ProductStats(BaseModel):
    avg_qty: float = 0.0
    std_dev: float = 0.0
    min_qty: float = 0.0
    max_qty: float = 0.0
    typical_unit: str = "kg"
    order_frequency_days: float = 7.0
    last_ordered_at: str | None = None
    total_orders: int = 0


class CustomerOrderProfile(BaseModel):
    id: str | None = None
    tenant_id: str
    customer_id: str
    product_stats: dict[str, ProductStats] = Field(default_factory=dict)
    anomaly_thresholds: dict[str, float] = Field(
        default_factory=lambda: {"qty_z_score": 3.0, "frequency_alert_days": 14.0}
    )
