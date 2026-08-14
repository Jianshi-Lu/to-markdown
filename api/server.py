"""to-markdown HTTP API 与 Uvicorn 启动入口。"""

import argparse
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api.convert import router as convert_router
from api.health import router as health_router
from configuration import (
    HttpServerSettings,
    get_conversion_settings,
    get_http_server_settings,
)
from core.errors import AppError
from convert import ConvertService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """在应用生命周期内复用转换服务及其外部客户端。"""

    # 启动阶段装配一次，避免每个请求重新初始化 MarkItDown/oMLX client。
    service = ConvertService(settings=get_conversion_settings())
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


def _build_parser(settings: HttpServerSettings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start the to-markdown HTTP service.",
    )
    parser.add_argument(
        "--host",
        default=settings.host,
        help="Address to bind (default: configured SERVER_HOST or 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.port,
        help="Port to bind (default: configured SERVER_PORT or 8081).",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Restart automatically after source changes; use only for development.",
    )
    parser.add_argument(
        "--log-level",
        choices=("critical", "error", "warning", "info", "debug", "trace"),
        default=settings.log_level.lower(),
        help="Uvicorn log level (default: configured SERVER_LOG_LEVEL or info).",
    )
    return parser


def main() -> int:
    """启动 HTTP 服务；热重载时向 Uvicorn 提供可重新导入的应用路径。"""

    settings = get_http_server_settings()
    args = _build_parser(settings).parse_args()
    target = "api.server:app" if args.reload else app
    uvicorn.run(
        target,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["app", "create_app", "lifespan", "main"]
