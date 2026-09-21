"""命令行入口。

用法（安装后）：`guji-run`
或直接：`python -m guji_collate.cli`

当前用 dummy 引擎空跑一遍流水线，用于验证骨架可执行，无需真实模型/OCR。
"""
from __future__ import annotations

from pathlib import Path

from .config import Config
from .modules.collation import DummyCollationEngine
from .modules.ocr import DummyOCREngine
from .modules.punctuation import DummyPunctuationEngine
from .modules.segmentation import DummySegmentationEngine
from .modules.translation import DummyTranslationEngine
from .pipeline import Pipeline
from .schemas import PageImage


def main() -> None:
    cfg = Config.load()
    pipeline = Pipeline(config=cfg)
    pipeline.register("ocr", DummyOCREngine(cfg))
    pipeline.register("segment", DummySegmentationEngine(cfg))
    pipeline.register("punctuate", DummyPunctuationEngine(cfg))
    pipeline.register("collate", DummyCollationEngine(cfg))
    pipeline.register("translate", DummyTranslationEngine(cfg))

    sample = PageImage(path=Path("data/raw_images/sample.png"), page_no=1, source="示例底本")
    report = pipeline.run([sample])
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
