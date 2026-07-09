from fastapi import APIRouter

from api.schemas import HealthResponse, OmlxHealthResponse
from adapters.omlx_client import assert_omlx_reachable
from core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/v1/health/omlx", response_model=OmlxHealthResponse)
async def omlx_health() -> OmlxHealthResponse:
    settings = get_settings()
    assert_omlx_reachable(settings.omlx_base_url)
    return OmlxHealthResponse(
        status="ok",
        base_url=settings.omlx_base_url,
        model=settings.omlx_model,
    )

