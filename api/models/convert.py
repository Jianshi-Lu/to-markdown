"""文件转换响应模型。"""

from pydantic import BaseModel, Field


class ConvertResponse(BaseModel):
    markdown: str
    source_filename: str
    content_type: str | None = None
    used_ocr: bool
    normalized: bool
    warnings: list[str] = Field(default_factory=list)
