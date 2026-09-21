"""自动断句阶段：文言文句子切分。"""
from __future__ import annotations

from ..config import Config
from ..schemas import NormalizedText, SegmentedText


class SegmentationEngine:
    """断句引擎接口（占位）。"""

    def run(self, text: NormalizedText) -> SegmentedText:
        raise NotImplementedError("请在子类中实现断句")


class DummySegmentationEngine(SegmentationEngine):
    """演示用引擎：以句读符号粗略切分，仅用于跑通流水线。"""

    def __init__(self, config: Config) -> None:
        self.config = config

    def run(self, text: NormalizedText) -> SegmentedText:
        raw = text.full_text
        # 简易规则示例；真实实现可用规则模型或 LLM
        parts = [s for s in raw.replace("，", "。").split("。") if s.strip()]
        return SegmentedText(sentences=[p + "。" for p in parts])


# TODO: 实现真实断句
# 参考思路：
# 1. 规则 / 统计模型：利用虚词、句式特征做候选切分点
# 2. LLM：提示词要求输出按句切分的文本，再解析回 SegmentedText
