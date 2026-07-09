from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api.routes.convert import router as convert_router
from api.routes.health import router as health_router
from core.errors import AppError


def create_app() -> FastAPI:
    app = FastAPI(title="to-markdown", version="0.1.0")
    app.include_router(health_router)
    app.include_router(convert_router, prefix="/v1")

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
