"""OCR 识别阶段：古籍书页影像 -> 文本行。"""
from __future__ import annotations

from ..config import Config
from ..schemas import NormalizedText, PageImage, TextLine


class OCREngine:
    """OCR 引擎接口（占位）。"""

    def run(self, page: PageImage) -> NormalizedText:
        raise NotImplementedError("请在子类中实现 OCR 识别")


class DummyOCREngine(OCREngine):
    """演示用引擎：返回固定文本，便于流水线空跑。"""

    def __init__(self, config: Config) -> None:
        self.config = config

    def run(self, page: PageImage) -> NormalizedText:
        return NormalizedText(
            page_no=page.page_no,
            lines=[TextLine(text="學而時習之，不亦說乎。", confidence=0.98)],
            plain_text="學而時習之，不亦說乎。",
        )


# TODO: 接入 PaddleOCR / 其他 OCR 服务
# class PaddleOCREngine(OCREngine):
#     def run(self, page: PageImage) -> NormalizedText:
#         # 1. 读取影像 2. 版面分析 3. 逐行识别 -> TextLine 列表
#         # 4. 可在此处接“文本规整”（繁简 / 异体字 / 避讳字）
#         ...
