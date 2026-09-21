"""校勘流水线。

设计目标：
- 阶段可插拔：每个阶段实现 `run()` 方法，通过 `Pipeline.register(name, stage)` 注册。
- 默认提供 dummy 引擎，保证空跑可执行；替换为真实引擎时只改注册处 / 配置。
"""
from __future__ import annotations

from typing import Any

from .config import Config
from .schemas import (
    CollationReport,
    NormalizedText,
    PageImage,
    PunctuatedText,
    SegmentedText,
    TranslationResult,
    VariantRecord,
)


class Pipeline:
    """把 OCR -> 规整 -> 断句 -> 标点 -> 校勘 -> 翻译 串成一条链。"""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.stages: dict[str, Any] = {}

    def register(self, name: str, stage: Any) -> None:
        """注册一个阶段，例如 `pipeline.register("ocr", PaddleOCREngine(cfg))`。"""
        self.stages[name] = stage

    def run(self, pages: list[PageImage]) -> CollationReport:
        """执行流水线，返回完整校勘报告。"""
        normalized_pages: list[NormalizedText] = [
            self._run_stage("ocr", page) for page in pages
        ]
        base = normalized_pages[0] if normalized_pages else NormalizedText()

        segmented: SegmentedText | None = self._run_stage("segment", base)
        punctuated: PunctuatedText | None = self._run_stage("punctuate", segmented)
        variants: list[VariantRecord] | None = self._run_stage("collate", base)
        translation: TranslationResult | None = self._run_stage("translate", base)

        return CollationReport(
            base_edition=self.config.get("collation.base_edition", ""),
            compare_editions=self.config.get("collation.compare_editions", []),
            normalized=base,
            segmented=segmented,
            punctuated=punctuated,
            variants=variants or [],
            translation=translation,
        )

    def _run_stage(self, name: str, payload: Any) -> Any:
        stage = self.stages.get(name)
        if stage is None:
            # TODO: 记录日志“阶段未注册，跳过”
            return None
        return stage.run(payload)
