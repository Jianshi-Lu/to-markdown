"""健康检查响应模型。"""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class OmlxHealthResponse(BaseModel):
    status: str
    base_url: str
    model: str
