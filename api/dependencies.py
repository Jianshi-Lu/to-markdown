"""FastAPI 依赖提供器。"""

from fastapi import Request

from convert import ConvertService


def get_convert_service(request: Request) -> ConvertService:
    """返回应用生命周期内创建的共享转换服务。"""

    return request.app.state.convert_service
