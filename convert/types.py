"""Convert 功能使用的共享数据类型。"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class UploadedFileInfo:
    filename: str
    content_type: str | None
    size_bytes: int


@dataclass(frozen=True)
class ConvertOptions:
    enable_ocr: bool = True
    normalize_markdown: bool = False


@dataclass(frozen=True)
class ConvertResult:
    markdown: str
    source_filename: str
    content_type: str | None
    used_ocr: bool
    normalized: bool
    warnings: list[str] = field(default_factory=list)
