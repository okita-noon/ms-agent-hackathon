"""休眠顧客サービスのテスト.

Created: 2026-05-22
Updated: 2026-05-22 22:15
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.customer import Customer, CustomerDeliveryPreference
from src.models.order import Order, OrderSource, OrderStatus, TemperatureZone
from src.models.product import Product, UnitType
from src.services.dormant_customer_service import (
    DORMANT_THRESHOLD_DAYS,
    MAX_DAILY_SENDS,
    SEND_HOUR_END,
    SEND_HOUR_START,
    DormantCustomerService,
    is_send_allowed,
    render_message,
)
from src.utils.business_date import JST


def _make_customer(
    id: str = "C001",
    name: str = "テスト商店",
    short_name: str | None = "テスト",
    line_user_id: str | None = "U123",
    email: str | None = "test@example.com",
    active: bool = True,
) -> Customer:
    return Customer(
        id=id,
        tenant_id="T1",
        name=name,
        short_name=short_name,
        line_user_id=line_user_id,
        email=email,
        delivery_preference=CustomerDeliveryPreference(),
        active=active,
    )


def _make_product(
    id: str = "P001",
    name: str = "みかん",
    display_name: str | None = "温州みかん",
    origin: str | None = "愛媛",
    appeal: str | None = "甘くてジューシーな旬の味わい。",
) -> Product:
    return Product(
        id=id,
        tenant_id="T1",
        name=name,
        display_name=display_name,
        origin=origin,
        appeal=appeal,
        default_unit=UnitType.BOX,
        temperature_zone=TemperatureZone.AMBIENT,
    )


def _make_order(customer_id: str, order_date: date) -> Order:
    return Order(
        uid="O001",
        tenant_id="T1",
        customer_id=customer_id,
        customer_name="テスト商店",
        source=OrderSource.LINE,
        status=OrderStatus.ACCEPTED,
        order_date=order_date,
    )


# --- render_message ---


class TestRenderMessage:
    def test_メッセージに顧客名と商品名が含まれる(self):
        customer = _make_customer()
        product = _make_product()
        msg = render_message(customer, product)
        assert "テスト" in msg
        assert "温州みかん" in msg

    def test_産地とアピールが含まれる(self):
        customer = _make_customer()
        product = _make_product(origin="愛媛", appeal="甘くてジューシー。")
        msg = render_message(customer, product)
        assert "愛媛" in msg
        assert "甘くてジューシー" in msg

    def test_short_nameがNoneならnameを使う(self):
        customer = _make_customer(short_name=None)
        product = _make_product()
        msg = render_message(customer, product)
        assert "テスト商店" in msg

    def test_display_nameがNoneならnameを使う(self):
        customer = _make_customer()
        product = _make_product(display_name=None)
        msg = render_message(customer, product)
        assert "みかん" in msg

    def test_originとappealがNoneでもエラーにならない(self):
        customer = _make_customer()
        product = _make_product(origin=None, appeal=None)
        msg = render_message(customer, product)
        assert "テスト" in msg


# --- is_send_allowed ---


class TestIsSendAllowed:
    def test_営業時間内はTrue(self):
        noon = datetime(2026, 5, 22, 12, 0, tzinfo=JST)
        assert is_send_allowed(noon) is True

    def test_開始時刻ちょうどはTrue(self):
        start = datetime(2026, 5, 22, SEND_HOUR_START, 0, tzinfo=JST)
        assert is_send_allowed(start) is True

    def test_終了時刻ちょうどはFalse(self):
        end = datetime(2026, 5, 22, SEND_HOUR_END, 0, tzinfo=JST)
        assert is_send_allowed(end) is False

    def test_早朝はFalse(self):
        early = datetime(2026, 5, 22, 5, 0, tzinfo=JST)
        assert is_send_allowed(early) is False

    def test_深夜はFalse(self):
        late = datetime(2026, 5, 22, 23, 0, tzinfo=JST)
        assert is_send_allowed(late) is False


# --- DormantCustomerService ---


def _make_service():
    ctx = MagicMock()
    ctx.tenant_id = "T1"
    return DormantCustomerService(ctx), ctx


class TestFindDormantCustomers:
    @pytest.mark.asyncio
    async def test_最終注文が閾値以上前の顧客を返す(self):
        svc, ctx = _make_service()
        customer = _make_customer()
        old_date = date.today() - timedelta(days=DORMANT_THRESHOLD_DAYS + 1)
        order = _make_order("C001", old_date)

        customer_repo = AsyncMock()
        customer_repo.list_all.return_value = [customer]
        order_repo = AsyncMock()
        order_repo.list_by_customer.return_value = [order]
        ctx.get_connector.side_effect = lambda name: {
            "ICustomerRepository": customer_repo,
            "IOrderRepository": order_repo,
        }[name]

        result = await svc.find_dormant_customers()
        assert len(result) == 1
        assert result[0][0].id == "C001"
        assert result[0][1] == old_date

    @pytest.mark.asyncio
    async def test_最近注文した顧客は含まない(self):
        svc, ctx = _make_service()
        customer = _make_customer()
        recent_date = date.today() - timedelta(days=5)
        order = _make_order("C001", recent_date)

        customer_repo = AsyncMock()
        customer_repo.list_all.return_value = [customer]
        order_repo = AsyncMock()
        order_repo.list_by_customer.return_value = [order]
        ctx.get_connector.side_effect = lambda name: {
            "ICustomerRepository": customer_repo,
            "IOrderRepository": order_repo,
        }[name]

        result = await svc.find_dormant_customers()
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_注文履歴なしの顧客を休眠として返す(self):
        svc, ctx = _make_service()
        customer = _make_customer()

        customer_repo = AsyncMock()
        customer_repo.list_all.return_value = [customer]
        order_repo = AsyncMock()
        order_repo.list_by_customer.return_value = []
        ctx.get_connector.side_effect = lambda name: {
            "ICustomerRepository": customer_repo,
            "IOrderRepository": order_repo,
        }[name]

        result = await svc.find_dormant_customers()
        assert len(result) == 1
        assert result[0][1] is None

    @pytest.mark.asyncio
    async def test_連絡先なしの顧客はスキップ(self):
        svc, ctx = _make_service()
        customer = _make_customer(line_user_id=None, email=None)

        customer_repo = AsyncMock()
        customer_repo.list_all.return_value = [customer]
        order_repo = AsyncMock()
        ctx.get_connector.side_effect = lambda name: {
            "ICustomerRepository": customer_repo,
            "IOrderRepository": order_repo,
        }[name]

        result = await svc.find_dormant_customers()
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_非アクティブ顧客はスキップ(self):
        svc, ctx = _make_service()
        customer = _make_customer(active=False)

        customer_repo = AsyncMock()
        customer_repo.list_all.return_value = [customer]
        order_repo = AsyncMock()
        ctx.get_connector.side_effect = lambda name: {
            "ICustomerRepository": customer_repo,
            "IOrderRepository": order_repo,
        }[name]

        result = await svc.find_dormant_customers()
        assert len(result) == 0


class TestPickRecommendedProduct:
    @pytest.mark.asyncio
    async def test_originとappealがある商品を優先(self):
        svc, ctx = _make_service()
        featured = _make_product(id="P1", origin="愛媛", appeal="旬です")
        plain = _make_product(id="P2", origin=None, appeal=None)

        product_master = AsyncMock()
        product_master.list_all.return_value = [plain, featured]
        ctx.get_connector.return_value = product_master

        with patch("src.services.dormant_customer_service.random") as mock_random:
            mock_random.choice.side_effect = lambda x: x[0]
            result = await svc.pick_recommended_product()

        assert result is not None
        assert result.id == "P1"

    @pytest.mark.asyncio
    async def test_商品がなければNone(self):
        svc, ctx = _make_service()
        product_master = AsyncMock()
        product_master.list_all.return_value = []
        ctx.get_connector.return_value = product_master

        result = await svc.pick_recommended_product()
        assert result is None


class TestSendOutreach:
    @pytest.mark.asyncio
    async def test_dry_runではメッセージ生成のみ(self):
        svc, ctx = _make_service()
        customer = _make_customer()
        product = _make_product()
        customers = [(customer, date.today() - timedelta(days=60))]

        results = await svc.send_outreach(customers, product, dry_run=True)
        assert len(results) == 1
        assert results[0]["status"] == "dry_run"
        assert results[0]["message"]
        assert results[0]["customer_id"] == "C001"

    @pytest.mark.asyncio
    async def test_MAX_DAILY_SENDSを超える顧客は送信しない(self):
        svc, ctx = _make_service()
        product = _make_product()
        customers = [(_make_customer(id=f"C{i:03d}"), None) for i in range(MAX_DAILY_SENDS + 5)]

        results = await svc.send_outreach(customers, product, dry_run=True)
        assert len(results) == MAX_DAILY_SENDS
