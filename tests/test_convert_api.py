"""验证纯文件流转换接口直接返回 Markdown 文件。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.convert import router
from api.dependencies import get_convert_service
from convert import ConvertResult
from api.server import app


class FakeConvertService:
    """记录上传文件流，并返回固定 Markdown。"""

    def __init__(self) -> None:
        self.content: bytes | None = None
        self.source_file = None

    def convert(self, file_stream, source_file):
        self.content = file_stream.read()
        self.source_file = source_file
        return ConvertResult(
            markdown="# 转换结果",
            source_filename=source_file.filename,
            content_type=source_file.content_type,
            warnings=[],
        )


def create_test_client(service: FakeConvertService) -> TestClient:
    """创建只包含转换路由的测试应用。"""

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_convert_service] = lambda: service
    return TestClient(app)


def test_convert_returns_markdown_file() -> None:
    """multipart 文件应转换为可下载的单个 Markdown 响应。"""

    service = FakeConvertService()
    client = create_test_client(service)

    response = client.post(
        "/convert",
        files={
            "file": (
                "采购文件.pdf",
                b"input bytes",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200
    assert response.text == "# 转换结果"
    assert response.headers["content-type"] == "text/markdown; charset=utf-8"
    assert "filename*=UTF-8''%E9%87%87%E8%B4%AD%E6%96%87%E4%BB%B6.md" in (
        response.headers["content-disposition"]
    )
    assert service.content == b"input bytes"
    assert service.source_file.filename == "采购文件.pdf"
    assert service.source_file.content_type == "application/pdf"


def test_convert_removes_client_path_from_filename() -> None:
    """调用方携带的目录信息不能进入响应文件名或转换元数据。"""

    service = FakeConvertService()
    client = create_test_client(service)

    response = client.post(
        "/convert",
        files={"file": ("../contracts/a.docx", b"doc", "application/octet-stream")},
    )

    assert response.status_code == 200
    assert service.source_file.filename == "a.docx"
    assert "a.md" in response.headers["content-disposition"]


def test_object_storage_endpoint_is_not_exposed() -> None:
    """纯转换服务不再提供对象存储读取和写回接口。"""

    client = create_test_client(FakeConvertService())

    response = client.post(
        "/convert/object",
        json={"originalObjectKey": "batch/original/a.pdf"},
    )

    assert response.status_code == 404


def test_convert_exposes_ocr_warning_headers() -> None:
    """退化输出被丢弃后，调用方可以从响应头识别降级结果。"""

    class WarningService(FakeConvertService):
        def convert(self, file_stream, source_file):
            file_stream.read()
            return ConvertResult(
                markdown="# 内置转换结果",
                source_filename=source_file.filename,
                content_type=source_file.content_type,
                warnings=["OCR 输出疑似退化，已丢弃"],
                warning_codes=["OCR_OUTPUT_DEGENERATED"],
            )

    response = create_test_client(WarningService()).post(
        "/convert",
        files={"file": ("a.pdf", b"input", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.headers["x-conversion-partial"] == "true"
    assert response.headers["x-conversion-warnings"] == "OCR_OUTPUT_DEGENERATED"


def test_invalid_pdf_uses_safe_conversion_error_contract() -> None:
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/convert",
            files={"file": ("broken.pdf", b"not a pdf", "application/pdf")},
        )

    assert response.status_code == 422
    assert response.json() == {
        "error": "conversion_failed",
        "message": "File conversion failed.",
    }
