"""流水线空跑测试：验证 dummy 引擎串联可用。"""
from pathlib import Path

from guji_collate.config import Config
from guji_collate.modules.collation import DummyCollationEngine
from guji_collate.modules.ocr import DummyOCREngine
from guji_collate.modules.punctuation import DummyPunctuationEngine
from guji_collate.modules.segmentation import DummySegmentationEngine
from guji_collate.modules.translation import DummyTranslationEngine
from guji_collate.pipeline import Pipeline
from guji_collate.schemas import PageImage


def _make_pipeline() -> Pipeline:
    cfg = Config({})
    p = Pipeline(config=cfg)
    p.register("ocr", DummyOCREngine(cfg))
    p.register("segment", DummySegmentationEngine(cfg))
    p.register("punctuate", DummyPunctuationEngine(cfg))
    p.register("collate", DummyCollationEngine(cfg))
    p.register("translate", DummyTranslationEngine(cfg))
    return p


def test_dummy_pipeline_runs() -> None:
    report = _make_pipeline().run([PageImage(path=Path("sample.png"), page_no=1)])
    assert report.normalized is not None
    assert report.normalized.full_text
    assert report.punctuated is not None
    assert report.variants
    assert report.translation is not None
