"""文件转换接口。"""

from fastapi import APIRouter, File, Form, UploadFile
from starlette.concurrency import run_in_threadpool

from api.models.convert import ConvertResponse
from core.config import get_settings
from convert import ConvertOptions, ConvertService, UploadedFileInfo
from storage.temp_files import save_upload_file

router = APIRouter(tags=["convert"])

# TODO： 流程上重新编排——目标：api只接收文件，是否开启ocr/ normalizer功能交给业务内部

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
        options = ConvertOptions(
            enable_ocr=enable_ocr,
            normalize_markdown=normalize_markdown,
        )
        service = ConvertService.from_settings(settings)
        result = await run_in_threadpool(   # 返回类型为 ConvertResult
            service.convert,
            temp_file.path,
            file_info,
            options,
        )
    finally:
        temp_file.cleanup()

    # 对ConvertResult的二次封装，封装为返回体格式
    return ConvertResponse(
        markdown=result.markdown,
        source_filename=result.source_filename,
        content_type=result.content_type,
        used_ocr=result.used_ocr,
        normalized=result.normalized,
        warnings=result.warnings,
    )
