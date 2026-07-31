"""文件转换业务服务。"""

from typing import BinaryIO

from integrations.markitdown import MarkItDownConverter
from integrations.omlx import OmlxOcrClient
from core.config import Settings
from convert.ocr_markdown_cleaner import OcrMarkdownCleaner
from convert.types import ConvertResult, SourceFile


class ConvertService:
    """复用转换运行时并编排输入文件流到 Markdown 的同步转换。"""

    def __init__(
        self,
        settings: Settings,
        ocr_cleaner: OcrMarkdownCleaner | None = None,
        markitdown_converter: MarkItDownConverter | None = None,
        omlx_ocr_client: OmlxOcrClient | None = None,
    ):
        """装配一次转换运行时；可注入依赖用于测试。"""

        self._settings = settings
        self._ocr_cleaner = ocr_cleaner or OcrMarkdownCleaner()
        # 正式服务只在 lifespan 中构造一次，后续请求复用同一组第三方客户端。
        if markitdown_converter is None or omlx_ocr_client is None:
            (
                markitdown_converter,
                omlx_ocr_client,
            ) = self._build_conversion_runtime()
        self._markitdown_converter = markitdown_converter
        self._omlx_ocr_client = omlx_ocr_client

    def close(self) -> None:
        """释放第三方客户端持有的 HTTP 资源。"""

        self._omlx_ocr_client.close()

    def convert(
        self,
        file_stream: BinaryIO,
        source_file: SourceFile,
    ) -> ConvertResult:
        """把调用方提供的文件流转换为 Markdown，并隔离 OCR 调用状态。"""

        warnings: list[str] = []

        # 客户端共享连接，状态通过 ContextVar 按请求隔离，避免并发 warning 串线。
        request_token = self._omlx_ocr_client.begin_request()
        try:
            markdown = self._markitdown_converter.convert(
                file_stream,
                filename=source_file.filename,
                content_type=source_file.content_type,
            )
        finally:
            ocr_call_state = self._omlx_ocr_client.end_request(request_token)
        warnings.extend(ocr_call_state.errors)

        markdown, normalized, cleaner_warnings = self._ocr_cleaner.clean(markdown)
        warnings.extend(cleaner_warnings)

        return ConvertResult(
            markdown=markdown,
            source_filename=source_file.filename,
            content_type=source_file.content_type,
            normalized=normalized,
            warnings=warnings,
        )

    def _build_conversion_runtime(
        self,
    ) -> tuple[MarkItDownConverter, OmlxOcrClient]:
        """创建应用级复用的 MarkItDown 与 oMLX 运行时。"""

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
