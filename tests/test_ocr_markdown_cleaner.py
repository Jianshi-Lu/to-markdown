import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

from core.config import Settings
from convert.ocr_markdown_cleaner import OcrMarkdownCleaner
from convert.service import ConvertService
from convert.types import SourceFile


class OcrMarkdownCleanerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cleaner = OcrMarkdownCleaner()

    def test_cleans_detection_protocol_and_preserves_text(self) -> None:
        markdown = (
            "*[Image OCR] 筆記 "
            "<|det|>title [344, 294, 666, 422]<|/det|>SQL 教程 "
            "<|det|>text [412, 674, 575, 730]<|/det|>作者：廖雪峰 "
            "<|det|>image [48, 808, 144, 952]<|/det|> "
            "<|det|>image [159, 808, 237, 952]<|/det|> [End OCR]*"
        )

        result, normalized, warnings = self.cleaner.clean(markdown)

        self.assertEqual(result, "筆記\n\n### SQL 教程\n\n作者：廖雪峰")
        self.assertTrue(normalized)
        self.assertEqual(warnings, [])

    def test_removes_only_ocr_wrapper_when_output_has_no_detections(self) -> None:
        result, normalized, _ = self.cleaner.clean(
            "Before\n\n*[Image OCR]\nInvoice number: A-123\n[End OCR]*\n\nAfter"
        )

        self.assertEqual(
            result,
            "Before\n\nInvoice number: A-123\n\nAfter",
        )
        self.assertTrue(normalized)

    def test_does_not_modify_regular_markdown(self) -> None:
        markdown = (
            "# Report\n\n"
            "Keep [Image OCR] in an ordinary sentence.\n\n"
            "Coordinates: [48, 808, 144, 952]"
        )

        result, normalized, warnings = self.cleaner.clean(markdown)

        self.assertEqual(result, markdown)
        self.assertFalse(normalized)
        self.assertEqual(warnings, [])

    def test_cleans_direct_image_description(self) -> None:
        markdown = (
            "# Description:\n"
            "筆\n"
            "<|det|>title [72, 168, 668, 258]<|/det|>OCR TEST DOCUMENT\n"
            "<|det|>text [70, 380, 551, 452]<|/det|>Supplier: Example Co.\n"
        )

        result, normalized, warnings = self.cleaner.clean(markdown)

        self.assertEqual(
            result,
            "# Description:\n### OCR TEST DOCUMENT\nSupplier: Example Co.\n",
        )
        self.assertTrue(normalized)
        self.assertEqual(warnings, [])

    def test_removes_single_model_artifact_from_plugin_block(self) -> None:
        markdown = (
            "*[Image OCR] 筆\n"
            "<|det|>title [1, 2, 3, 4]<|/det|>OCR TEST DOCUMENT\n"
            "<|det|>text [1, 2, 3, 4]<|/det|>Supplier: Example Co.\n"
            "[End OCR]*"
        )

        result, normalized, _ = self.cleaner.clean(markdown)

        self.assertEqual(
            result,
            "### OCR TEST DOCUMENT\n\nSupplier: Example Co.",
        )
        self.assertTrue(normalized)

    def test_keeps_unrecognized_detection_markup(self) -> None:
        markdown = (
            "*[Image OCR]\n"
            "<|det|>table [1, 2, 3, 4]<|/det|>A | B\n"
            "[End OCR]*"
        )

        result, normalized, _ = self.cleaner.clean(markdown)

        self.assertEqual(
            result,
            "<|det|>table [1, 2, 3, 4]<|/det|>A | B",
        )
        self.assertTrue(normalized)

    def test_service_always_runs_ocr_cleaner(self) -> None:
        cleaner = Mock()
        cleaner.clean.return_value = ("cleaned", True, [])
        markitdown_converter = Mock()
        markitdown_converter.convert.return_value = "raw markdown"
        ocr_call_state = SimpleNamespace(errors=[])
        omlx_ocr_client = Mock()
        omlx_ocr_client.begin_request.return_value = object()
        omlx_ocr_client.end_request.return_value = ocr_call_state
        service = ConvertService(
            settings=Settings(
                omlx_base_url="http://127.0.0.1:8000/v1",
                omlx_api_key="test",
                omlx_model="test",
                omlx_ocr_prompt="Free OCR.",
                omlx_ocr_max_tokens=4096,
                omlx_ocr_temperature=0,
                omlx_ocr_repetition_penalty=1.1,
                max_upload_mb=100,
            ),
            ocr_cleaner=cleaner,
            markitdown_converter=markitdown_converter,
            omlx_ocr_client=omlx_ocr_client,
        )

        result = service.convert(
            BytesIO(b"document"),
            SourceFile(
                filename="document.docx",
                content_type=None,
                size_bytes=1,
            ),
        )

        markitdown_converter.convert.assert_called_once()
        _, call_kwargs = markitdown_converter.convert.call_args
        self.assertEqual(call_kwargs["filename"], "document.docx")
        self.assertIsNone(call_kwargs["content_type"])
        cleaner.clean.assert_called_once_with("raw markdown")
        self.assertEqual(result.markdown, "cleaned")
        self.assertTrue(result.normalized)


if __name__ == "__main__":
    unittest.main()
