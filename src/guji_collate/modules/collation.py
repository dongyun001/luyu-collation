"""异文校勘阶段：底本与参校本比对，生成校勘记。"""
from __future__ import annotations

from ..config import Config
from ..schemas import NormalizedText, VariantRecord


class CollationEngine:
    """校勘引擎接口（占位）。"""

    def run(self, base: NormalizedText) -> list[VariantRecord]:
        raise NotImplementedError("请在子类中实现异文校勘")


class DummyCollationEngine(CollationEngine):
    """演示用引擎：返回一条固定校勘记，仅用于跑通流水线。"""

    def __init__(self, config: Config) -> None:
        self.config = config

    def run(self, base: NormalizedText) -> list[VariantRecord]:
        return [
            VariantRecord(
                location="卷一·页一·行一（示例）",
                base_text="學而時習之",
                variant_text="學而時習之",
                edition="示例参校本",
                note="演示数据，请替换为真实校勘逻辑。",
            )
        ]


# TODO: 实现真实校勘，参考思路：
# 1. 文本对齐：字符级 diff 或行级对齐（如 Myers diff / 序列对齐算法）
# 2. 差异判定：区分异文、讹字、衍文、脱文
# 3. LLM 辅助：对对齐结果做学术化按语生成
# 4. 输出：VariantRecord 列表，location 需回填卷/页/行定位
