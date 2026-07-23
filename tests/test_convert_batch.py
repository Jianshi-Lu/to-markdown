import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock

from core.config import Settings
from convert.service import ConvertService


class FakeBatchStorage:
    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        self.objects = [
            SimpleNamespace(
                object_key="batch/original/b.pdf",
                filename="b.pdf",
                content_type="application/pdf",
                size_bytes=1,
            ),
            SimpleNamespace(
                object_key="batch/original/a.pdf",
                filename="a.pdf",
                content_type="application/pdf",
                size_bytes=1,
            ),
        ]
        self.uploads = []

    def list_original_objects(self, _upload_batch_id):
        return self.objects

    def download(self, _object_key, destination: Path):
        destination.write_bytes(b"input")

    def converted_object_key(self, object_key):
        return object_key.replace("/original/", "/converted/").replace(
            ".pdf", ".md"
        )

    def upload_markdown(self, object_key, markdown):
        self.uploads.append((object_key, markdown))


class ConvertBatchTest(unittest.TestCase):
    def test_converts_and_uploads_each_object_in_order(self):
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            markitdown_converter = Mock()
            markitdown_converter.convert.side_effect = ["B markdown", "A markdown"]
            omlx_ocr_client = Mock()
            omlx_ocr_client.begin_request.side_effect = [object(), object()]
            omlx_ocr_client.end_request.return_value = SimpleNamespace(errors=[])
            service = ConvertService(
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
                markitdown_converter=markitdown_converter,
                omlx_ocr_client=omlx_ocr_client,
            )
            storage = FakeBatchStorage(temp_path)

            result = service.convert_batch("batch", storage)

            self.assertEqual(
                storage.uploads,
                [
                    ("batch/converted/b.md", "B markdown"),
                    ("batch/converted/a.md", "A markdown"),
                ],
            )
            self.assertEqual(
                [file.converted_object_key for file in result.files],
                ["batch/converted/b.md", "batch/converted/a.md"],
            )
            self.assertEqual(list(temp_path.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
