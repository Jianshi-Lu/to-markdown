"""验证 ConvertService：内置 MarkItDown 表格能力恢复 + OCR 按需调用。"""

import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from convert.service import ConvertService
from convert.types import SourceFile
from integrations.embedded_image_ocr import EmbeddedImageOcr
from tests.test_embedded_image_ocr import (
    FakeOmlxClient,
    make_pdf_with_image,
    make_settings,
)


def build_service(client: FakeOmlxClient) -> ConvertService:
    """构造真实转换器 + 真实按需 OCR（使用模拟 oMLX 客户端）。"""

    return ConvertService(
        settings=make_settings(),
        omlx_ocr_client=client,
    )


def convert_pdf(service: ConvertService, data: bytes) -> str:
    """以 PDF 源文件调用服务并返回 Markdown。"""

    result = service.convert(
        io.BytesIO(data),
        SourceFile(
            filename="测试知识文件.pdf",
            content_type="application/pdf",
            size_bytes=len(data),
        ),
    )
    return result.markdown


def test_builtin_tables_preserved_and_ocr_not_called() -> None:
    """数字版测试 PDF：表格保留，且无嵌入位图时不调用 OCR。"""

    desktop_pdf = Path("/Users/lujianshi/Desktop/测试知识文件.pdf")
    if not desktop_pdf.exists():
        pytest.skip("桌面测试 PDF 不存在")

    client = FakeOmlxClient()
    markdown = convert_pdf(build_service(client), desktop_pdf.read_bytes())

    # 无嵌入位图时走单遍转换，不再输出逐页分页标记
    assert "## Page" not in markdown
    assert "| 项目" in markdown
    assert "| 评分维度" in markdown
    assert client.calls == 0


def test_pdf_with_image_uses_ocr_on_demand() -> None:
    """含嵌入位图的 PDF：OCR 被调用，结果插回对应页面。"""

    client = FakeOmlxClient(text="OCR CONTENT")
    markdown = convert_pdf(build_service(client), make_pdf_with_image())

    assert "*[Image OCR]" in markdown
    assert "OCR CONTENT" in markdown
    assert "[End OCR]*" in markdown
    assert client.calls == 1


def test_docx_ocr_inserted_after_image_tag() -> None:
    """DOCX 转换后 OCR 文本应紧跟图片标签，而不是只在末尾追加。"""

    docx_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "test_files"
        / "input"
        / "complex_docx.docx"
    )
    docx_bytes = docx_path.read_bytes()
    client = FakeOmlxClient(text="DOCX OCR TEXT")
    service = build_service(client)

    result = service.convert(
        io.BytesIO(docx_bytes),
        SourceFile(
            filename="complex_docx.docx",
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            size_bytes=len(docx_bytes),
        ),
    )

    markdown = result.markdown
    assert "[Image OCR]" in markdown
    assert markdown.index("[Image OCR]") > markdown.index("![](data:")
    assert client.calls >= 1


def test_html_image_ocr_inserted_after_tag() -> None:
    """HTML 图片应被 OCR，结果紧跟图片标签。"""

    html_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "test_files"
        / "input"
        / "complex.html"
    )
    html_bytes = html_path.read_bytes()
    client = FakeOmlxClient(text="HTML OCR TEXT")

    result = build_service(client).convert(
        io.BytesIO(html_bytes),
        SourceFile(
            filename="complex.html",
            content_type="text/html",
            size_bytes=len(html_bytes),
        ),
    )

    markdown = result.markdown
    assert "[Image OCR]" in markdown
    assert markdown.index("[Image OCR]") > markdown.index("![")
    assert client.calls >= 1


def test_epub_image_ocr_inserted_after_tag() -> None:
    """EPUB 图片应被 OCR，结果紧跟相对路径图片标签。"""

    epub_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "test_files"
        / "input"
        / "complex.epub"
    )
    epub_bytes = epub_path.read_bytes()
    client = FakeOmlxClient(text="EPUB OCR TEXT")

    result = build_service(client).convert(
        io.BytesIO(epub_bytes),
        SourceFile(
            filename="complex.epub",
            content_type="application/epub+zip",
            size_bytes=len(epub_bytes),
        ),
    )

    markdown = result.markdown
    assert "[Image OCR]" in markdown
    assert markdown.index("[Image OCR]") > markdown.index("![")
    assert client.calls >= 1


def test_zip_image_ocr_inserted_after_tag() -> None:
    """ZIP 内嵌 HTML 的图片应被 OCR，结果紧跟图片标签。"""

    zip_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "test_files"
        / "input"
        / "complex.zip"
    )
    zip_bytes = zip_path.read_bytes()
    client = FakeOmlxClient(text="ZIP OCR TEXT")

    result = build_service(client).convert(
        io.BytesIO(zip_bytes),
        SourceFile(
            filename="complex.zip",
            content_type="application/zip",
            size_bytes=len(zip_bytes),
        ),
    )

    markdown = result.markdown
    assert "[Image OCR]" in markdown
    assert markdown.index("[Image OCR]") > markdown.index("![")
    assert client.calls >= 1
