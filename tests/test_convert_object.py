import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock

from core.config import Settings
from convert.service import ConvertService


class FakeObjectStorage:
    def __init__(self):
        self.original = SimpleNamespace(
            object_key="batch/original/a.pdf",
            filename="a.pdf",
            content_type="application/pdf",
            size_bytes=1,
        )
        self.uploads = []

    def get_original_object(self, _object_key):
        return self.original

    def download(self, _object_key, destination: Path):
        destination.write_bytes(b"input")

    def converted_object_key(self, object_key):
        return object_key.replace("/original/", "/converted/").replace(
            ".pdf", ".md"
        )

    def upload_markdown(self, object_key, markdown):
        self.uploads.append((object_key, markdown))


def create_service(temp_path: Path, converter):
    omlx_ocr_client = Mock()
    omlx_ocr_client.begin_request.return_value = object()
    omlx_ocr_client.end_request.return_value = SimpleNamespace(errors=[])
    return ConvertService(
        settings=Settings(
            omlx_base_url="http://127.0.0.1:8000/v1",
            omlx_api_key="test",
            omlx_model="test",
            omlx_ocr_prompt="Free OCR.",
            omlx_ocr_max_tokens=4096,
            omlx_ocr_temperature=0,
            omlx_ocr_repetition_penalty=1.1,
            temp_dir=temp_path,
            max_upload_mb=100,
        ),
        markitdown_converter=converter,
        omlx_ocr_client=omlx_ocr_client,
    )


class ConvertObjectTest(unittest.TestCase):
    def test_converts_one_object_and_uploads_markdown(self):
        with TemporaryDirectory() as temp_dir:
            converter = Mock()
            converter.convert.return_value = "A markdown"
            storage = FakeObjectStorage()
            service = create_service(Path(temp_dir), converter)

            result = service.convert_object(
                "batch/original/a.pdf",
                storage,
            )

            self.assertEqual(
                storage.uploads,
                [("batch/converted/a.md", "A markdown")],
            )
            self.assertEqual(result.original_object_key, "batch/original/a.pdf")
            self.assertEqual(result.converted_object_key, "batch/converted/a.md")
            self.assertEqual(result.status, "COMPLETED")
            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_removes_temp_file_when_conversion_fails(self):
        with TemporaryDirectory() as temp_dir:
            converter = Mock()
            converter.convert.side_effect = RuntimeError("bad input")
            service = create_service(Path(temp_dir), converter)

            with self.assertRaises(RuntimeError):
                service.convert_object("batch/original/a.pdf", FakeObjectStorage())

            self.assertEqual(list(Path(temp_dir).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
