"""文件转换接口。"""

from fastapi import APIRouter, Depends, File, UploadFile
from starlette.concurrency import run_in_threadpool

from api.dependencies import (
    get_convert_service,
    get_minio_batch_object_storage,
)
from api.models.convert import (
    BatchConvertRequest,
    BatchConvertResponse,
    BatchConvertedFileResponse,
    ConvertResponse,
)
from core.config import SETTINGS
from convert import ConvertService, SourceFile
from integrations.minio import MinioBatchObjectStorage
from uploads.temp_uploads import save_upload_file

router = APIRouter(tags=["convert"])


@router.post("/convert/batch", response_model=BatchConvertResponse)
async def convert_batch(
    request: BatchConvertRequest,
    service: ConvertService = Depends(get_convert_service),
    object_storage: MinioBatchObjectStorage = Depends(
        get_minio_batch_object_storage
    ),
) -> BatchConvertResponse:
    """按 uploadBatchId 逐个转换 original 文件并写入 converted 路径。"""

    result = await run_in_threadpool(
        service.convert_batch,
        request.upload_batch_id,
        object_storage,
    )
    return BatchConvertResponse(
        upload_batch_id=result.upload_batch_id,
        files=[
            BatchConvertedFileResponse(
                original_object_key=file.original_object_key,
                original_filename=file.original_filename,
                converted_object_key=file.converted_object_key,
                content_type=file.content_type,
                warnings=file.warnings,
            )
            for file in result.files
        ],
    )


@router.post("/convert", response_model=ConvertResponse)
async def convert_file(
    file: UploadFile = File(...),
    service: ConvertService = Depends(get_convert_service),
) -> ConvertResponse:
    """接收上传文件，并调用应用生命周期内复用的转换服务。"""

    temp_file = await save_upload_file(file, settings=SETTINGS)

    try:
        source_file = SourceFile(
            filename=file.filename or temp_file.path.name,
            content_type=file.content_type,
            size_bytes=temp_file.size_bytes,
        )
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
