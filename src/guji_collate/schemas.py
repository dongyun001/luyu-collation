"""项目核心数据结构（Pydantic 模型）。

所有流水线阶段之间的数据交换均使用这里的模型。
字段是草案，讨论后可增删；修改前请先同步 `docs/data-spec.md`。
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class PageImage(BaseModel):
    """一页古籍影像。"""

    path: Path
    page_no: int = 1
    source: str = ""  # 来源书名 / 档案号


class TextLine(BaseModel):
    """OCR 识别出的一行文本，带版面比例坐标（0~1）。"""

    text: str
    confidence: float = Field(ge=0, le=1, default=0)
    x: float = 0
    y: float = 0
    w: float = 1
    h: float = 1


class NormalizedText(BaseModel):
    """规整后的文本：繁简 / 异体字规范化之后的结果。"""

    page_no: int = 1
    lines: list[TextLine] = Field(default_factory=list)
    plain_text: str = ""  # 拼接后的全文

    @property
    def full_text(self) -> str:
        return self.plain_text or "\n".join(line.text for line in self.lines)


class SegmentedText(BaseModel):
    """断句结果：按句子切分，保留原文顺序。"""

    sentences: list[str] = Field(default_factory=list)


class PunctuatedText(BaseModel):
    """自动标点结果：在原文基础上插入现代标点。"""

    text: str = ""
    segments: list[tuple[str, str]] = Field(default_factory=list)  # (原文片段, 标点后片段)


class TranslationResult(BaseModel):
    """文白翻译结果。"""

    source: str = ""
    target: str = ""
    style: Literal["modern_zh", "english"] = "modern_zh"


class VariantRecord(BaseModel):
    """一条异文校勘记。"""

    location: str = ""  # 定位信息，如“卷一·页三·行四”
    base_text: str = ""  # 底本文字
    variant_text: str = ""  # 参校本异文
    edition: str = ""  # 异文出处（版本）
    note: str = ""  # 校勘说明 / 按语
    status: Literal["pending", "accepted", "rejected"] = "pending"


class CollationReport(BaseModel):
    """一次校勘的完整输出。"""

    base_edition: str = ""
    compare_editions: list[str] = Field(default_factory=list)
    normalized: NormalizedText | None = None
    segmented: SegmentedText | None = None
    punctuated: PunctuatedText | None = None
    variants: list[VariantRecord] = Field(default_factory=list)
    translation: TranslationResult | None = None
