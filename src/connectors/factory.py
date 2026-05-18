from __future__ import annotations

import logging
from typing import Any

from src.models.tenant import TenantConfig

logger = logging.getLogger(__name__)

_ADAPTER_REGISTRY: dict[str, dict[str, type]] = {}


def register_adapter(interface_name: str, adapter_type: str, cls: type) -> None:
    _ADAPTER_REGISTRY.setdefault(interface_name, {})[adapter_type] = cls


class ConnectorFactory:
    def __init__(self, tenant_config: TenantConfig):
        self._tenant_config = tenant_config
        self._cache: dict[str, Any] = {}

    def resolve(self, interface_name: str) -> Any:
        if interface_name in self._cache:
            return self._cache[interface_name]

        connector_cfg = self._tenant_config.connectors.get(interface_name)
        if not connector_cfg:
            raise ValueError(
                f"No connector config for {interface_name} in tenant {self._tenant_config.tenant_id}"
            )

        adapters = _ADAPTER_REGISTRY.get(interface_name, {})
        adapter_cls = adapters.get(connector_cfg.type)
        if not adapter_cls:
            raise ValueError(
                f"No adapter '{connector_cfg.type}' registered for {interface_name}. Available: {list(adapters.keys())}"
            )

        instance = adapter_cls(connector_cfg)
        self._cache[interface_name] = instance
        logger.info(
            "Resolved %s -> %s for tenant %s",
            interface_name,
            adapter_cls.__name__,
            self._tenant_config.tenant_id,
        )
        return instance
