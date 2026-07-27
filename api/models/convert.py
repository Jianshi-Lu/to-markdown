"""文件转换响应模型。"""

from pydantic import BaseModel, ConfigDict, Field


class ConvertResponse(BaseModel):
    markdown: str
    source_filename: str
    content_type: str | None = None
    normalized: bool
    warnings: list[str] = Field(default_factory=list)


class ObjectConvertRequest(BaseModel):
    """单个 MinIO 原始对象转换请求。"""

    model_config = ConfigDict(populate_by_name=True)

    original_object_key: str = Field(min_length=1, alias="originalObjectKey")


class ObjectConvertResponse(BaseModel):
    """单个 MinIO 原始对象的转换结果。"""

    model_config = ConfigDict(populate_by_name=True)

    original_object_key: str = Field(alias="originalObjectKey")
    original_filename: str = Field(alias="originalFilename")
    converted_object_key: str | None = Field(
        default=None,
        alias="convertedObjectKey",
    )
    content_type: str | None = Field(default=None, alias="contentType")
    status: str
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None

