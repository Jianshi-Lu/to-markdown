"""使用FastAPI打包应用。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api.convert import router as convert_router
from api.health import router as health_router
from core.config import SETTINGS
from core.errors import AppError
from convert import ConvertService
from integrations.minio import MinioObjectStorage


@asynccontextmanager
async def lifespan(app: FastAPI):
    """在应用生命周期内复用转换服务及其外部客户端。"""

    # 启动阶段装配一次，避免每个请求重新初始化 MarkItDown/oMLX client。
    service = ConvertService(settings=SETTINGS)
    app.state.minio_object_storage = MinioObjectStorage(
        endpoint=SETTINGS.minio_endpoint,
        access_key=SETTINGS.minio_access_key,
        secret_key=SETTINGS.minio_secret_key,
        bucket=SETTINGS.minio_bucket,
    )
    app.state.convert_service = service
    try:
        yield
    finally:
        # Uvicorn 关闭应用时释放共享 HTTP 连接。
        service.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="to-markdown",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(convert_router)

    @app.exception_handler(AppError)
    async def handle_app_error(_, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.code,
                "message": str(exc),
            },
        )

    return app


app = create_app()
