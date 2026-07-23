import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from integrations.minio import MinioBatchObjectStorage


class FakeResponse:
    def __init__(self, content: bytes):
        self._content = content
        self.closed = False
        self.released = False

    def stream(self, _size: int):
        yield self._content

    def close(self):
        self.closed = True

    def release_conn(self):
        self.released = True


class FakeMinioClient:
    def __init__(self):
        self.batch_id = "550e8400-e29b-41d4-a716-446655440000"
        self.responses = {
            f"{self.batch_id}/original/b.pdf": FakeResponse(b"B"),
            f"{self.batch_id}/original/a.pdf": FakeResponse(b"A"),
        }
        self.uploads = {}

    def list_objects(self, _bucket, prefix, recursive):
        self.asserted_prefix = prefix
        self.asserted_recursive = recursive
        return [
            SimpleNamespace(object_name=key, size=len(response._content))
            for key, response in self.responses.items()
        ]

    def get_object(self, _bucket, object_key):
        return self.responses[object_key]

    def put_object(self, _bucket, object_key, data, length, content_type):
        self.uploads[object_key] = {
            "content": data.read(),
            "length": length,
            "content_type": content_type,
        }


class MinioBatchObjectStorageTest(unittest.TestCase):
    def test_lists_batch_original_objects_in_stable_order(self):
        client = FakeMinioClient()
        storage = MinioBatchObjectStorage(
            "http://minio:9000", "access", "secret", "credential-files", client
        )

        objects = storage.list_original_objects(
            "550e8400-e29b-41d4-a716-446655440000"
        )

        self.assertEqual(
            client.asserted_prefix,
            "550e8400-e29b-41d4-a716-446655440000/original/",
        )
        self.assertTrue(client.asserted_recursive)
        self.assertEqual(
            [item.object_key for item in objects],
            [
                "550e8400-e29b-41d4-a716-446655440000/original/a.pdf",
                "550e8400-e29b-41d4-a716-446655440000/original/b.pdf",
            ],
        )

    def test_downloads_object_to_temp_disk_and_closes_response(self):
        client = FakeMinioClient()
        storage = MinioBatchObjectStorage(
            "http://minio:9000", "access", "secret", "credential-files", client
        )

        with TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "a.pdf"
            storage.download(
                "550e8400-e29b-41d4-a716-446655440000/original/a.pdf",
                destination,
            )

            self.assertEqual(destination.read_bytes(), b"A")

        response = client.responses[
            "550e8400-e29b-41d4-a716-446655440000/original/a.pdf"
        ]
        self.assertTrue(response.closed)
        self.assertTrue(response.released)

    def test_rejects_invalid_batch_id(self):
        storage = MinioBatchObjectStorage(
            "http://minio:9000", "access", "secret", "credential-files", FakeMinioClient()
        )

        with self.assertRaises(ValueError):
            storage.list_original_objects("not-a-uuid")

    def test_maps_original_key_to_converted_markdown_key(self):
        storage = MinioBatchObjectStorage(
            "http://minio:9000", "access", "secret", "credential-files", FakeMinioClient()
        )

        self.assertEqual(
            storage.converted_object_key(
                "550e8400-e29b-41d4-a716-446655440000/original/contracts/a.pdf"
            ),
            "550e8400-e29b-41d4-a716-446655440000/converted/contracts/a.md",
        )

    def test_uploads_markdown_with_content_type(self):
        client = FakeMinioClient()
        storage = MinioBatchObjectStorage(
            "http://minio:9000", "access", "secret", "credential-files", client
        )

        storage.upload_markdown("batch/converted/a.md", "# Converted")

        self.assertEqual(
            client.uploads["batch/converted/a.md"],
            {
                "content": b"# Converted",
                "length": len(b"# Converted"),
                "content_type": "text/markdown; charset=utf-8",
            },
        )


if __name__ == "__main__":
    unittest.main()
