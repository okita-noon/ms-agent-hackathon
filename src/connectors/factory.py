from __future__ import annotations

import logging
from importlib import import_module
from typing import Any

from src.models.tenant import TenantConfig

logger = logging.getLogger(__name__)

AdapterRef = type | str

_ADAPTER_REGISTRY: dict[str, dict[str, AdapterRef]] = {}
_ADAPTER_CLASS_CACHE: dict[str, type] = {}


def register_adapter(interface_name: str, adapter_type: str, cls: AdapterRef) -> None:
    _ADAPTER_REGISTRY.setdefault(interface_name, {})[adapter_type] = cls


def _load_adapter_class(adapter_ref: AdapterRef) -> type:
    if isinstance(adapter_ref, type):
        return adapter_ref

    if adapter_ref in _ADAPTER_CLASS_CACHE:
        return _ADAPTER_CLASS_CACHE[adapter_ref]

    module_name, class_name = adapter_ref.rsplit(".", 1)
    module = import_module(module_name)
    adapter_cls = getattr(module, class_name)
    _ADAPTER_CLASS_CACHE[adapter_ref] = adapter_cls
    return adapter_cls


class ConnectorFactory:
    def __init__(self, tenant_config: TenantConfig):
        self._tenant_config = tenant_config
        self._cache: dict[str, Any] = {}

    def resolve(self, interface_name: str) -> Any:
        if interface_name in self._cache:
            return self._cache[interface_name]

        connector_cfg = self._tenant_config.connectors.get(interface_name)
        if not connector_cfg:
            raise ValueError(f"No connector config for {interface_name} in tenant {self._tenant_config.tenant_id}")

        adapters = _ADAPTER_REGISTRY.get(interface_name, {})
        adapter_ref = adapters.get(connector_cfg.type)
        if not adapter_ref:
            raise ValueError(
                f"No adapter '{connector_cfg.type}' registered for {interface_name}. Available: {list(adapters.keys())}"
            )

        adapter_cls = _load_adapter_class(adapter_ref)
        instance = adapter_cls(connector_cfg)
        self._cache[interface_name] = instance
        logger.info(
            "Resolved %s -> %s for tenant %s",
            interface_name,
            adapter_cls.__name__,
            self._tenant_config.tenant_id,
        )
        return instance
