"""验证嵌入位图按需 OCR：只处理图片，不替换 MarkItDown 内置转换器。"""

import io
from pathlib import Path
from types import SimpleNamespace

import fitz
from PIL import Image, ImageDraw

from core.config import Settings
from integrations.embedded_image_ocr import EmbeddedImageOcr


class FakeOmlxClient:
    """模拟 OpenAI-compatible 客户端的 chat.completions.create。"""

    def __init__(self, text: str = "OCR CONTENT") -> None:
        self.calls = 0
        self.text = text
        self.chat = SimpleNamespace(completions=self)

    def begin_request(self):
        return object()

    def end_request(self, _token):
        return SimpleNamespace(errors=[])

    def close(self) -> None:
        return None

    def create(self, **_kwargs):
        self.calls += 1
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.text)
                )
            ]
        )


def make_settings() -> Settings:
    """构造带默认按需 OCR 配置的测试 Settings。"""

    return Settings(
        omlx_base_url="http://127.0.0.1:8000/v1",
        omlx_api_key="test",
        omlx_model="unlimited-ocr-mxfp8-mlx",
        omlx_ocr_prompt="document parsing.",
        omlx_ocr_max_tokens=4096,
        omlx_ocr_temperature=0,
        omlx_ocr_repetition_penalty=1.1,
        max_upload_mb=100,
    )


def make_pdf_with_image() -> bytes:
    """生成一个带嵌入 PNG 位图的单页 PDF。"""

    image_buffer = io.BytesIO()
    image = Image.new("RGB", (240, 80), "white")
    draw = ImageDraw.Draw(image)
    draw.text((12, 24), "OCR CONTENT 123", fill="black")
    image.save(image_buffer, format="PNG")

    document = fitz.open()
    page = document.new_page(width=320, height=320)
    page.insert_image(
        fitz.Rect(40, 40, 280, 120),
        stream=image_buffer.getvalue(),
    )
    return document.tobytes()


def make_text_only_pdf() -> bytes:
    """生成一个只含文本、无嵌入位图的单页 PDF。"""

    document = fitz.open()
    page = document.new_page(width=320, height=320)
    page.insert_text((50, 60), "plain text page")
    return document.tobytes()


def test_ocr_pdf_page_returns_image_text() -> None:
    """含嵌入位图的页面应触发一次 OCR 并返回文本。"""

    client = FakeOmlxClient()
    ocr = EmbeddedImageOcr(
        omlx_client=client,
        model="unlimited-ocr-mxfp8-mlx",
        prompt="Extract text.",
    )

    results = ocr.ocr_pdf_page(make_pdf_with_image())

    assert client.calls == 1
    assert results == ["OCR CONTENT"]


def test_ocr_pdf_page_without_images_does_not_call_model() -> None:
    """无嵌入位图的页面不应发起任何 OCR 调用。"""

    client = FakeOmlxClient()
    ocr = EmbeddedImageOcr(
        omlx_client=client,
        model="unlimited-ocr-mxfp8-mlx",
        prompt="Extract text.",
    )

    results = ocr.ocr_pdf_page(make_text_only_pdf())

    assert client.calls == 0
    assert results == []


def test_insert_docx_ocr_after_image_tag() -> None:
    """DOCX 的 OCR 文本应紧跟对应 data URI 图片标签插入。"""

    docx_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "test_files"
        / "input"
        / "complex_docx.docx"
    )
    docx_bytes = docx_path.read_bytes()

    from markitdown import MarkItDown, StreamInfo

    markdown = MarkItDown(enable_plugins=False).convert_stream(
        io.BytesIO(docx_bytes),
        stream_info=StreamInfo(
            mimetype=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            extension=".docx",
            filename="complex_docx.docx",
        ),
    ).markdown
    assert "![](data:image/png;base64" in markdown

    client = FakeOmlxClient(text="DOCX OCR TEXT")
    ocr = EmbeddedImageOcr(
        omlx_client=client,
        model="unlimited-ocr-mxfp8-mlx",
        prompt="Extract text.",
    )

    inserted = ocr.insert_docx_ocr(markdown, docx_bytes)

    assert client.calls >= 1
    assert "[Image OCR]" in inserted
    assert inserted.index("[Image OCR]") > inserted.index("![](data:")


def test_insert_image_ocr_html() -> None:
    """HTML 的 data URI 图片应被 OCR，并把结果插回图片标签之后。"""

    html_bytes = (
        b'<html><body><img src="data:image/png;base64,AAA="></body></html>'
    )
    markdown = "before\n\n![img](data:image/png;base64...)\n\nafter"
    client = FakeOmlxClient(text="HTML OCR TEXT")
    ocr = EmbeddedImageOcr(
        omlx_client=client,
        model="unlimited-ocr-mxfp8-mlx",
        prompt="Extract text.",
    )

    inserted = ocr.insert_image_ocr(markdown, html_bytes, ".html")

    assert client.calls == 1
    assert "[Image OCR]" in inserted
    assert inserted.index("[Image OCR]") > inserted.index("![")


def test_insert_image_ocr_epub() -> None:
    """EPUB 内的图片应被提取 OCR，并回填到相对路径图片标签。"""

    import zipfile

    epub_buffer = io.BytesIO()
    with zipfile.ZipFile(epub_buffer, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            (
                '<?xml version="1.0"?>'
                '<container version="1.0" '
                'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                'media-type="application/oebps-package+xml"/></rootfiles>'
                "</container>"
            ),
        )
        archive.writestr(
            "OEBPS/content.opf",
            (
                '<?xml version="1.0"?>'
                '<package xmlns="http://www.idpf.org/2007/opf">'
                '<manifest>'
                '<item id="i1" href="images/cover.png" '
                'media-type="image/png"/>'
                "</manifest></package>"
            ),
        )
        archive.writestr("OEBPS/images/cover.png", b"fake-png")

    markdown = "cover\n\n![cover](images/cover.png)"
    client = FakeOmlxClient(text="EPUB OCR TEXT")
    ocr = EmbeddedImageOcr(
        omlx_client=client,
        model="unlimited-ocr-mxfp8-mlx",
        prompt="Extract text.",
    )

    inserted = ocr.insert_image_ocr(
        markdown,
        epub_buffer.getvalue(),
        ".epub",
    )

    assert client.calls == 1
    assert "[Image OCR]" in inserted
    assert inserted.index("[Image OCR]") > inserted.index("![cover]")
