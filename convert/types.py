"""Convert 功能使用的共享数据类型。"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceFile:
    filename: str
    content_type: str | None
    size_bytes: int


@dataclass(frozen=True)
class ConvertResult:
    markdown: str
    source_filename: str
    content_type: str | None
    normalized: bool
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BatchConvertedFile:
    """一个原始对象对应的已写入 Markdown 对象。"""

    original_object_key: str
    original_filename: str
    converted_object_key: str
    content_type: str | None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BatchConvertResult:
    """一个上传批次的逐文件转换结果。"""

    upload_batch_id: str
    files: list[BatchConvertedFile] = field(default_factory=list)
