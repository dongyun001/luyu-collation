"""文白翻译阶段：文言文 -> 现代汉语（可扩展为英文）。"""
from __future__ import annotations

from ..config import Config
from ..schemas import NormalizedText, TranslationResult


class TranslationEngine:
    """翻译引擎接口（占位）。"""

    def run(self, text: NormalizedText) -> TranslationResult:
        raise NotImplementedError("请在子类中实现文白翻译")


class DummyTranslationEngine(TranslationEngine):
    """演示用引擎：返回固定译文，仅用于跑通流水线。"""

    def __init__(self, config: Config) -> None:
        self.config = config

    def run(self, text: NormalizedText) -> TranslationResult:
        return TranslationResult(
            source=text.full_text,
            target="学习并且按时温习它，不也很高兴吗。（演示译文，请替换为真实翻译）",
        )


# TODO: 实现真实翻译
# 1. LLM：提示词要求文言 -> 现代汉语，保留专名与引文原貌
# 2. 术语表：人名 / 地名 / 官名等先查表再翻译，降低幻觉
