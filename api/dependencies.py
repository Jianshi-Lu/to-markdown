"""FastAPI 依赖提供器。"""

from fastapi import Request

from convert import ConvertService
from integrations.minio import MinioObjectStorage


def get_convert_service(request: Request) -> ConvertService:
    """返回应用生命周期内创建的共享转换服务。"""

    return request.app.state.convert_service


def get_minio_object_storage(
    request: Request,
) -> MinioObjectStorage:
    """返回应用生命周期内复用的 MinIO 对象存储。"""

    return request.app.state.minio_object_storage
