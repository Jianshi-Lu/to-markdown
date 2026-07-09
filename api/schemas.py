from pydantic import BaseModel, Field


class ConvertResponse(BaseModel):
    markdown: str
    source_filename: str
    content_type: str | None = None
    used_ocr: bool
    normalized: bool
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str


class OmlxHealthResponse(BaseModel):
    status: str
    base_url: str
    model: str

