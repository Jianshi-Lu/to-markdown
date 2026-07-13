"""文件转换接口。"""

from fastapi import APIRouter, File, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from api.models.convert import ConvertResponse
from core.config import SETTINGS
from convert import ConvertService, SourceFile
from uploads.temp_uploads import save_upload_file

router = APIRouter(tags=["convert"])

@router.post("/convert", response_model=ConvertResponse)
async def convert_file(
    request: Request,
    file: UploadFile = File(...),
) -> ConvertResponse:
    """接收上传文件，并调用应用生命周期内复用的转换服务。"""

    temp_file = await save_upload_file(file, settings=SETTINGS)

    try:
        source_file = SourceFile(
            filename=file.filename or temp_file.path.name,
            content_type=file.content_type,
            size_bytes=temp_file.size_bytes,
        )
        # ConvertService 在应用启动时装配，这里只读取共享实例，不重复创建客户端。
        service: ConvertService = request.app.state.convert_service
        result = await run_in_threadpool(
            service.convert,
            temp_file.path,
            source_file,
        )
    finally:
        temp_file.cleanup()

    return ConvertResponse(
        markdown=result.markdown,
        source_filename=result.source_filename,
        content_type=result.content_type,
        normalized=result.normalized,
        warnings=result.warnings,
    )
