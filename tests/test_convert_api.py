"""验证纯文件流转换接口直接返回 Markdown 文件。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.convert import router
from api.dependencies import get_convert_service
from convert import ConvertResult


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
            normalized=False,
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
