"""文件转换响应模型。"""

from pydantic import BaseModel, ConfigDict, Field


class ConvertResponse(BaseModel):
    markdown: str
    source_filename: str
    content_type: str | None = None
    normalized: bool
    warnings: list[str] = Field(default_factory=list)


class BatchConvertRequest(BaseModel):
    """批次 Markdown 转换请求。"""

    model_config = ConfigDict(populate_by_name=True)

    upload_batch_id: str = Field(min_length=1, alias="uploadBatchId")


class BatchConvertedFileResponse(BaseModel):
    """批次中一个原始对象对应的已写入 Markdown 对象。"""

    model_config = ConfigDict(populate_by_name=True)

    original_object_key: str = Field(alias="originalObjectKey")
    original_filename: str = Field(alias="originalFilename")
    converted_object_key: str = Field(alias="convertedObjectKey")
    content_type: str | None = Field(default=None, alias="contentType")
    warnings: list[str] = Field(default_factory=list)


class BatchConvertResponse(BaseModel):
    """批次 Markdown 转换响应。"""

    model_config = ConfigDict(populate_by_name=True)

    upload_batch_id: str = Field(alias="uploadBatchId")
    files: list[BatchConvertedFileResponse]
