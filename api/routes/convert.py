from fastapi import APIRouter, File, Form, UploadFile
from starlette.concurrency import run_in_threadpool

from api.schemas import ConvertResponse
from core.config import get_settings
from domain.models import ConversionOptions, UploadedFileInfo
from services.conversion_service import ConversionService
from storage.temp_files import save_upload_file

router = APIRouter(tags=["convert"])


@router.post("/convert", response_model=ConvertResponse)
async def convert_file(
    file: UploadFile = File(...),
    enable_ocr: bool = Form(True),
    normalize_markdown: bool = Form(False),
) -> ConvertResponse:
    settings = get_settings()
    temp_file = await save_upload_file(file, settings=settings)

    try:
        file_info = UploadedFileInfo(
            filename=file.filename or temp_file.path.name,
            content_type=file.content_type,
            size_bytes=temp_file.size_bytes,
        )
        options = ConversionOptions(
            enable_ocr=enable_ocr,
            normalize_markdown=normalize_markdown,
        )
        service = ConversionService.from_settings(settings)
        result = await run_in_threadpool(
            service.convert,
            temp_file.path,
            file_info,
            options,
        )
    finally:
        temp_file.cleanup()

    return ConvertResponse(
        markdown=result.markdown,
        source_filename=result.source_filename,
        content_type=result.content_type,
        used_ocr=result.used_ocr,
        normalized=result.normalized,
        warnings=result.warnings,
    )

