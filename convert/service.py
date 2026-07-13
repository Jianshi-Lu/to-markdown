"""文件转换业务服务。"""

from pathlib import Path

from integrations.markitdown import MarkItDownConverter
from integrations.omlx import OmlxOcrClient
from core.config import Settings
from convert.ocr_markdown_cleaner import OcrMarkdownCleaner
from convert.types import ConvertResult, SourceFile


class ConvertService:
    """编排一次本地文件到 Markdown 的同步转换。"""

    def __init__(
        self,
        settings: Settings,
        ocr_cleaner: OcrMarkdownCleaner | None = None,
    ):
        self._settings = settings
        self._ocr_cleaner = ocr_cleaner or OcrMarkdownCleaner()

    def convert(
        self,
        file_path: Path,
        source_file: SourceFile,
    ) -> ConvertResult:
        warnings: list[str] = []

        markitdown_converter, omlx_ocr_client = self._create_markitdown_converter()
        markdown = markitdown_converter.convert(file_path)
        warnings.extend(omlx_ocr_client.call_state.errors)

        markdown, normalized, cleaner_warnings = self._ocr_cleaner.clean(markdown)
        warnings.extend(cleaner_warnings)

        return ConvertResult(
            markdown=markdown,
            source_filename=source_file.filename,
            content_type=source_file.content_type,
            normalized=normalized,
            warnings=warnings,
        )

    def _create_markitdown_converter(
        self,
    ) -> tuple[MarkItDownConverter, OmlxOcrClient]:
        omlx_ocr_client = OmlxOcrClient(
            base_url=self._settings.omlx_base_url,
            api_key=self._settings.omlx_api_key,
            max_tokens=self._settings.omlx_ocr_max_tokens,
            temperature=self._settings.omlx_ocr_temperature,
            repetition_penalty=self._settings.omlx_ocr_repetition_penalty,
        )
        return (
            MarkItDownConverter(
                llm_client=omlx_ocr_client,
                llm_model=self._settings.omlx_model,
                llm_prompt=self._settings.omlx_ocr_prompt,
            ),
            omlx_ocr_client,
        )
