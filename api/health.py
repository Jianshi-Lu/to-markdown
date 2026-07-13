"""健康检查接口。"""

from fastapi import APIRouter

from integrations.omlx import assert_omlx_reachable
from api.models.health import HealthResponse, OmlxHealthResponse
from core.config import SETTINGS

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/omlx", response_model=OmlxHealthResponse)
async def omlx_health() -> OmlxHealthResponse:
    assert_omlx_reachable(SETTINGS.omlx_base_url)
    return OmlxHealthResponse(
        status="ok",
        base_url=SETTINGS.omlx_base_url,
        model=SETTINGS.omlx_model,
    )
