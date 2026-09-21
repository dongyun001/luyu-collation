"""核心数据结构的单元测试。"""
from guji_collate.schemas import CollationReport, VariantRecord


def test_variant_record_defaults() -> None:
    v = VariantRecord(location="卷一")
    assert v.status == "pending"
    assert v.base_text == ""


def test_collation_report_json_roundtrip() -> None:
    report = CollationReport(
        base_edition="底本",
        variants=[VariantRecord(location="卷一·页一")],
    )
    data = report.model_dump_json()
    loaded = CollationReport.model_validate_json(data)
    assert loaded.base_edition == "底本"
    assert loaded.variants[0].location == "卷一·页一"
