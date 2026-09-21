"""自动标点阶段：在原文基础上插入现代标点。"""
from __future__ import annotations

from ..config import Config
from ..schemas import PunctuatedText, SegmentedText


class PunctuationEngine:
    """标点引擎接口（占位）。"""

    def run(self, text: SegmentedText) -> PunctuatedText:
        raise NotImplementedError("请在子类中实现自动标点")


class DummyPunctuationEngine(PunctuationEngine):
    """演示用引擎：直接拼接已有句子，仅用于跑通流水线。"""

    def __init__(self, config: Config) -> None:
        self.config = config

    def run(self, text: SegmentedText) -> PunctuatedText:
        joined = "".join(text.sentences)
        return PunctuatedText(text=joined, segments=[(s, s) for s in text.sentences])


# TODO: 实现真实标点
# 1. LLM：输入无标点文言，要求只加标点不改字，返回带标点文本
# 2. 解析 LLM 输出为 (原文片段, 标点后片段) 列表，便于前端高亮对照
