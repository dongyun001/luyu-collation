"""全局配置加载。

约定：`configs/default.yaml` 为默认值；本地可复制为 `configs/local.yaml`（已被 .gitignore 忽略），
加载时 local 覆盖 default。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class Config:
    """简单的点号路径配置容器，避免各处直接散落读取 YAML。"""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data or {}

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        config_path = Path(path) if path else Path("configs/default.yaml")
        data: dict[str, Any] = {}
        if config_path.exists():
            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        # 本地覆盖文件（不入库）
        local_path = config_path.with_name("local.yaml")
        if local_path.exists():
            loaded = yaml.safe_load(local_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        return cls(data)

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """按点号路径取值，如 `get("collation.base_edition")`。"""
        node: Any = self._data
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def as_dict(self) -> dict[str, Any]:
        return self._data
