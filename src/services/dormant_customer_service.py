"""休眠顧客への営業メッセージ自動送信サービス.

Created: 2026-05-22
Updated: 2026-05-22 22:23
"""

from __future__ import annotations

import logging
import random
from datetime import date, datetime
from pathlib import Path
from string import Template

from src.connectors.context import TenantContext
from src.models.customer import Customer
from src.models.product import Product
from src.utils.business_date import now_jst, today_jst

logger = logging.getLogger(__name__)

DORMANT_THRESHOLD_DAYS = 30
SEND_HOUR_START = 9
SEND_HOUR_END = 18
MAX_DAILY_SENDS = 10

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _PROJECT_ROOT / "_templates"
_TEMPLATE_GLOB = "販促営業_久しぶりの顧客用_*.txt"


def _load_templates() -> list[Template]:
    """_templates/ フォルダからテンプレートファイルを読み込む."""
    files = sorted(_TEMPLATE_DIR.glob(_TEMPLATE_GLOB))
    if not files:
        logger.warning("テンプレートファイルが見つかりません: %s/%s", _TEMPLATE_DIR, _TEMPLATE_GLOB)
        return []
    return [Template(f.read_text(encoding="utf-8")) for f in files]


def render_message(
    customer: Customer,
    product: Product,
) -> str:
    """テンプレートからランダムに1つ選び、変数を埋めてメッセージを生成する."""
    templates = _load_templates()
    if not templates:
        return f"{customer.short_name or customer.name}様、おすすめ商品のご案内です。"
    template = random.choice(templates)
    return template.safe_substitute(
        customer_name=customer.short_name or customer.name,
        product_name=product.display_name or product.name,
        product_origin=product.origin or "",
        product_appeal=product.appeal or "",
    )


def is_send_allowed(now: datetime | None = None) -> bool:
    """現在時刻が送信可能時間帯（JST）内かどうか判定する."""
    current = now or now_jst()
    return SEND_HOUR_START <= current.hour < SEND_HOUR_END


class DormantCustomerService:
    def __init__(self, tenant_ctx: TenantContext):
        self._ctx = tenant_ctx

    async def find_dormant_customers(
        self,
        threshold_days: int = DORMANT_THRESHOLD_DAYS,
    ) -> list[tuple[Customer, date | None]]:
        """LINE または メールが紐付いている顧客のうち、休眠状態のものを返す."""
        customer_repo = self._ctx.get_connector("ICustomerRepository")
        order_repo = self._ctx.get_connector("IOrderRepository")

        all_customers: list[Customer] = await customer_repo.list_all(self._ctx.tenant_id)
        today = today_jst()
        dormant: list[tuple[Customer, date | None]] = []

        for customer in all_customers:
            if not customer.active:
                continue
            if not customer.line_user_id and not customer.email:
                continue

            orders = await order_repo.list_by_customer(customer.id, limit=1)
            last_order_date = orders[0].order_date if orders else None
            if last_order_date is None or (today - last_order_date).days >= threshold_days:
                dormant.append((customer, last_order_date))

        return dormant

    async def pick_recommended_product(self) -> Product | None:
        """おすすめ商品を1つ選ぶ。origin と appeal が設定されている商品を優先する."""
        product_master = self._ctx.get_connector("IProductMaster")
        products: list[Product] = await product_master.list_all(self._ctx.tenant_id)

        featured = [p for p in products if p.active and p.origin and p.appeal]
        if featured:
            return random.choice(featured)

        active = [p for p in products if p.active]
        if active:
            return random.choice(active)

        return None

    async def send_outreach(
        self,
        customers: list[tuple[Customer, date | None]],
        product: Product,
        dry_run: bool = False,
    ) -> list[dict]:
        """休眠顧客に営業メッセージを送信する. dry_run=True でメッセージ生成のみ."""
        from src.plugins.communication_plugin import CommunicationPlugin

        comm = CommunicationPlugin(self._ctx)
        results: list[dict] = []

        for customer, last_order_date in customers[:MAX_DAILY_SENDS]:
            message = render_message(customer, product)
            entry: dict = {
                "customer_id": customer.id,
                "customer_name": customer.name,
                "last_order_date": str(last_order_date) if last_order_date else None,
                "message": message,
                "channels_sent": [],
                "status": "skipped",
            }

            if dry_run:
                entry["status"] = "dry_run"
                results.append(entry)
                continue

            sent = False
            if customer.line_user_id:
                try:
                    await comm.send_line_push(
                        user_id=customer.line_user_id,
                        message=message,
                    )
                    entry["channels_sent"].append("line")
                    sent = True
                except Exception:
                    logger.exception("LINE送信失敗: %s", customer.id)

            if customer.email:
                try:
                    await comm.send_email(
                        to_address=customer.email,
                        subject="おすすめ商品のご案内",
                        body=message,
                    )
                    entry["channels_sent"].append("email")
                    sent = True
                except Exception:
                    logger.exception("メール送信失敗: %s", customer.id)

            entry["status"] = "sent" if sent else "failed"
            results.append(entry)

        return results
