"""文件转换业务服务。"""

from pathlib import Path

from adapters.markitdown_adapter import MarkItDownAdapter
from adapters.omlx_client import OmlxClient, assert_omlx_reachable
from core.config import Settings
from convert.markdown_normalizer import MarkdownNormalizer
from convert.types import ConvertOptions, ConvertResult, UploadedFileInfo


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


class ConvertService:
    """编排一次本地文件到 Markdown 的同步转换。"""

    def __init__(
        self,
        settings: Settings,
        normalizer: MarkdownNormalizer | None = None,
    ):
        self._settings = settings
        self._normalizer = normalizer or MarkdownNormalizer()

    @classmethod
    def from_settings(cls, settings: Settings) -> "ConvertService":
        return cls(settings=settings)

    def convert(
        self,
        file_path: Path,
        file_info: UploadedFileInfo,
        options: ConvertOptions,
    ) -> ConvertResult:
        warnings: list[str] = []
        likely_uses_ocr = options.enable_ocr and self._is_image(file_info, file_path)

        if likely_uses_ocr:
            assert_omlx_reachable(self._settings.omlx_base_url)

        # 建立markitdown依赖实例，包含模型服务omlx
        adapter = self._build_markitdown_adapter(enable_ocr=options.enable_ocr)
        markdown = adapter.convert(file_path)

        normalized = False
        if options.normalize_markdown:
            markdown, normalized, normalizer_warnings = self._normalizer.normalize(markdown)
            warnings.extend(normalizer_warnings)

        return ConvertResult(
            markdown=markdown,
            source_filename=file_info.filename,
            content_type=file_info.content_type,
            used_ocr=likely_uses_ocr,
            normalized=normalized,
            warnings=warnings,
        )

    def _build_markitdown_adapter(self, enable_ocr: bool) -> MarkItDownAdapter:
        if not enable_ocr:
            return MarkItDownAdapter()

        omlx_client = OmlxClient(
            base_url=self._settings.omlx_base_url,
            api_key=self._settings.omlx_api_key,
        )
        return MarkItDownAdapter(
            llm_client=omlx_client,
            llm_model=self._settings.omlx_model,
            llm_prompt="Free OCR.",
        )

    @staticmethod
    def _is_image(file_info: UploadedFileInfo, file_path: Path) -> bool:
        if file_info.content_type and file_info.content_type.startswith("image/"):
            return True
        return file_path.suffix.lower() in IMAGE_SUFFIXES
