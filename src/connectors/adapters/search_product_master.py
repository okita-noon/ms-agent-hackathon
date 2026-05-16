from __future__ import annotations

import logging
import os
import re
import unicodedata
from typing import Any

from src.models.order import TemperatureZone
from src.models.product import Product, UnitType
from src.models.tenant import ConnectorConfig

logger = logging.getLogger(__name__)

_INDEX_NAME = "products"


class SearchProductMaster:
    """Azure AI Search backed IProductMaster adapter.

    Uses the ``ja.microsoft`` analyzer on the ``name`` / ``display_name``
    fields to handle Japanese kanji ↔ kana ↔ rōmaji variations that SQL LIKE
    cannot resolve.

    Tenant-config keys used (all optional – env-var fallbacks apply):
      - ``endpoint``:        AI Search service URL
      - ``extra.api_key``:   Admin/query key
      - ``index``:           Index name (default: "products")
    """

    def __init__(self, config: ConnectorConfig) -> None:
        endpoint = config.endpoint or os.environ.get("AI_SEARCH_ENDPOINT", "")
        api_key = config.extra.get("api_key") or os.environ.get("AI_SEARCH_KEY", "")
        index_name = config.index or _INDEX_NAME

        if not endpoint or not api_key:
            logger.warning(
                "SearchProductMaster: AI_SEARCH_ENDPOINT or AI_SEARCH_KEY not set; all lookups will return None/empty."
            )
            self._client = None
            return

        try:
            from azure.core.credentials import AzureKeyCredential
            from azure.search.documents.aio import SearchClient

            self._client: Any = SearchClient(
                endpoint=endpoint,
                index_name=index_name,
                credential=AzureKeyCredential(api_key),
            )
        except ImportError:
            logger.error("azure-search-documents package is not installed; SearchProductMaster will not function.")
            self._client = None

    # ------------------------------------------------------------------
    # IProductMaster
    # ------------------------------------------------------------------

    async def fuzzy_match(self, tenant_id: str, raw_name: str) -> Product | None:
        """Search for the best-matching product by name using AI Search.

        Applies the same NFKC normalisation + quantity-stripping as the SQL
        adapter, then issues a full-text query so the ``ja.microsoft`` analyzer
        handles kana/kanji/rōmaji variation server-side.
        """
        if self._client is None:
            return None

        terms = _search_terms(raw_name)
        if not terms:
            return None

        filter_expr = f"tenant_id eq '{tenant_id}' and active eq true"

        for term in terms:
            try:
                results = await self._client.search(
                    search_text=term,
                    filter=filter_expr,
                    top=1,
                    query_type="simple",
                    search_fields=["name", "display_name", "search_text"],
                )
                async for doc in results:
                    return _doc_to_product(doc)
            except Exception as exc:
                logger.warning("SearchProductMaster.fuzzy_match error: %s", exc)
                return None

        return None

    async def get_by_id(self, tenant_id: str, product_id: str) -> Product | None:
        if self._client is None:
            return None

        try:
            doc = await self._client.get_document(key=product_id)
            if doc.get("tenant_id") != tenant_id:
                return None
            return _doc_to_product(doc)
        except Exception as exc:
            logger.warning("SearchProductMaster.get_by_id error: %s", exc)
            return None

    async def list_all(self, tenant_id: str) -> list[Product]:
        if self._client is None:
            return []

        filter_expr = f"tenant_id eq '{tenant_id}' and active eq true"
        products: list[Product] = []

        try:
            results = await self._client.search(
                search_text="*",
                filter=filter_expr,
                top=100,
            )
            async for doc in results:
                products.append(_doc_to_product(doc))
        except Exception as exc:
            logger.warning("SearchProductMaster.list_all error: %s", exc)

        return products


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _doc_to_product(doc: dict[str, Any]) -> Product:
    return Product(
        id=doc.get("product_id", ""),
        tenant_id=doc.get("tenant_id", ""),
        name=doc.get("name", ""),
        display_name=doc.get("display_name"),
        category=doc.get("category"),
        default_unit=UnitType(doc["default_unit"]) if doc.get("default_unit") else UnitType.KG,
        temperature_zone=(
            TemperatureZone(doc["temperature_zone"]) if doc.get("temperature_zone") else TemperatureZone.AMBIENT
        ),
        unit_weight_kg=doc.get("unit_weight_kg"),
        is_variable_weight=bool(doc.get("is_variable_weight", False)),
        price_per_unit=doc.get("price_per_unit"),
        active=bool(doc.get("active", True)),
    )


def _search_terms(raw_name: str) -> list[str]:
    """NFKC-normalise, strip trailing quantity expressions, deduplicate."""
    normalized = unicodedata.normalize("NFKC", raw_name).strip()
    if not normalized:
        return []

    terms = [normalized]
    stripped = re.sub(
        (
            r"[\s,、。:：;；]*\d+(?:\.\d+)?\s*"
            r"(?:kg|g|箱|個|パック|房|玉|ケース|袋|本|枚)?\s*$"
        ),
        "",
        normalized,
        flags=re.IGNORECASE,
    ).strip()
    if stripped:
        terms.append(stripped)

    compact = re.sub(r"\s+", "", stripped or normalized)
    if compact:
        terms.append(compact)

    deduped: list[str] = []
    for term in terms:
        if term and term not in deduped:
            deduped.append(term)
    return deduped
