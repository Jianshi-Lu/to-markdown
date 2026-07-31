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
