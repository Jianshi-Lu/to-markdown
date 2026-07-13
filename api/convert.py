"""文件转换接口。"""

from fastapi import APIRouter, File, UploadFile
from starlette.concurrency import run_in_threadpool

from api.models.convert import ConvertResponse
from core.config import SETTINGS
from convert import ConvertService, SourceFile
from uploads.temp_uploads import save_upload_file

router = APIRouter(tags=["convert"])

@router.post("/convert", response_model=ConvertResponse)
async def convert_file(
    file: UploadFile = File(...),
) -> ConvertResponse:
    temp_file = await save_upload_file(file, settings=SETTINGS)

    try:
        source_file = SourceFile(
            filename=file.filename or temp_file.path.name,
            content_type=file.content_type,
            size_bytes=temp_file.size_bytes,
        )
        service = ConvertService(settings=SETTINGS)
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
