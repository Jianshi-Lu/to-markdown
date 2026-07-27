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
class ObjectConvertResult:
    """一个 MinIO 原始对象对应的转换结果。"""

    original_object_key: str
    original_filename: str
    converted_object_key: str | None
    content_type: str | None
    status: str
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

