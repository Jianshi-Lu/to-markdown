"""验证 MarkItDown 适配器直接消费调用方文件流。"""

import io
from io import BytesIO
from tempfile import SpooledTemporaryFile
from types import SimpleNamespace
from unittest.mock import Mock

from integrations.markitdown import MarkItDownConverter


def test_converter_passes_stream_and_file_metadata() -> None:
    """适配器不构造文件路径，只向 MarkItDown 传递流和格式提示。"""

    markitdown = Mock()
    markitdown.convert_stream.return_value = SimpleNamespace(markdown="# Result")
    converter = MarkItDownConverter.__new__(MarkItDownConverter)
    converter._markitdown = markitdown
    file_stream = BytesIO(b"source")

    result = converter.convert(
        file_stream,
        filename="contract.pdf",
        content_type="application/pdf",
    )

    assert result == "# Result"
    args, kwargs = markitdown.convert_stream.call_args
    assert args == (file_stream,)
    assert kwargs["stream_info"].filename == "contract.pdf"
    assert kwargs["stream_info"].extension == ".pdf"
    assert kwargs["stream_info"].mimetype == "application/pdf"


def test_converter_adapts_spooled_upload_to_buffered_binary_stream() -> None:
    """FastAPI 上传流应满足 Magika 对 BufferedIOBase 的严格类型要求。"""

    markitdown = Mock()

    def convert_stream(stream, **_):
        assert isinstance(stream, io.BufferedIOBase)
        assert stream.read() == b"uploaded-content"
        return SimpleNamespace(markdown="# Result")

    markitdown.convert_stream.side_effect = convert_stream
    converter = MarkItDownConverter.__new__(MarkItDownConverter)
    converter._markitdown = markitdown

    with SpooledTemporaryFile() as upload_stream:
        upload_stream.write(b"uploaded-content")
        upload_stream.seek(0)

        result = converter.convert(
            upload_stream,
            filename="contract.pdf",
            content_type="application/pdf",
        )

        assert result == "# Result"
        assert not upload_stream.closed
