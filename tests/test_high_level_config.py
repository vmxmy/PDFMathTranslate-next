import pytest

from pdf2zh_next.config.model import SettingsModel
from pdf2zh_next.high_level import LLM_ONLY_DOC_LAYOUT_MODEL
from pdf2zh_next.high_level import _build_split_strategy
from pdf2zh_next.high_level import _build_table_model
from pdf2zh_next.high_level import _map_watermark_mode
from pdf2zh_next.high_level import _select_doc_layout_model
from babeldoc.format.pdf.translation_config import (
    WatermarkOutputMode as BabelDOCWatermarkMode,
)


class TestHighLevelConfigHelpers:
    def test_map_watermark_mode_known_values(self):
        assert _map_watermark_mode("no_watermark") == BabelDOCWatermarkMode.NoWatermark
        assert _map_watermark_mode("both") == BabelDOCWatermarkMode.Both
        assert _map_watermark_mode("watermarked") == BabelDOCWatermarkMode.Watermarked

    def test_map_watermark_mode_default_fallback(self):
        # 未知值回退到带水印，避免异常
        assert _map_watermark_mode("unknown") == BabelDOCWatermarkMode.Watermarked

    def test_build_split_strategy(self):
        settings = SettingsModel()
        assert _build_split_strategy(settings) is None

        settings.pdf.max_pages_per_part = 5
        strategy = _build_split_strategy(settings)
        assert strategy is not None

    def test_build_table_model_no_load_when_disabled(self):
        settings = SettingsModel()
        settings.pdf.translate_table_text = False
        assert _build_table_model(settings) is None

        settings.pdf.translate_table_text = True
        settings.pdf.disable_rapidocr = True
        # 禁用 RapidOCR 时不应加载模型
        assert _build_table_model(settings) is None

    def test_select_doc_layout_model_returns_stub(self):
        settings = SettingsModel()
        assert _select_doc_layout_model(settings) is LLM_ONLY_DOC_LAYOUT_MODEL

    def test_select_doc_layout_model_use_default_when_table_translation(self):
        settings = SettingsModel()
        settings.pdf.translate_table_text = True
        settings.pdf.disable_rapidocr = False
        # 启用表格翻译时返回 None，让 BabelDOC 使用默认 doc layout
        assert _select_doc_layout_model(settings) is None
