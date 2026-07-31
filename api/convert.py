"""接收调用方上传的单个文件，并返回 Markdown 文件。"""

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from api.dependencies import get_convert_service
from core.config import SETTINGS
from core.errors import UploadTooLargeError
from convert import ConvertService, SourceFile

router = APIRouter(tags=["convert"])


@router.post(
    "/convert",
    response_class=Response,
    responses={
        200: {
            "content": {"text/markdown": {}},
            "description": "转换后的单个 Markdown 文件。",
        }
    },
)
async def convert_file(
    file: UploadFile = File(...),
    service: ConvertService = Depends(get_convert_service),
) -> Response:
    """转换一个 multipart 文件流，直接返回 Markdown 文件内容。"""

    _validate_upload_size(file)
    source_filename = _source_filename(file.filename)
    await file.seek(0)

    result = await run_in_threadpool(
        service.convert,
        file.file,
        SourceFile(
            filename=source_filename,
            content_type=file.content_type,
            size_bytes=file.size or 0,
        ),
    )
    markdown_filename = f"{Path(source_filename).stem or 'converted'}.md"
    return Response(
        content=result.markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": (
                "attachment; filename=\"converted.md\"; "
                f"filename*=UTF-8''{quote(markdown_filename)}"
            )
        },
    )


def _validate_upload_size(file: UploadFile) -> None:
    """根据 multipart 解析器记录的文件大小拒绝超限请求。"""

    max_bytes = SETTINGS.max_upload_mb * 1024 * 1024
    if file.size is not None and file.size > max_bytes:
        raise UploadTooLargeError(
            f"Uploaded file is larger than {SETTINGS.max_upload_mb} MB."
        )


def _source_filename(filename: str | None) -> str:
    """去掉调用方路径信息，只保留用于格式识别和响应命名的文件名。"""

    normalized = (filename or "document").replace("\\", "/")
    return normalized.rsplit("/", 1)[-1] or "document"
