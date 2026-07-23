"""文件转换业务服务。"""

from pathlib import Path

from integrations.markitdown import MarkItDownConverter
from integrations.minio import MinioBatchObjectStorage
from integrations.omlx import OmlxOcrClient
from core.config import Settings
from convert.ocr_markdown_cleaner import OcrMarkdownCleaner
from convert.types import (
    BatchConvertResult,
    BatchConvertedFile,
    ConvertResult,
    SourceFile,
)


class ConvertService:
    """复用转换运行时并编排本地文件到 Markdown 的同步转换。"""

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
        file_path: Path,
        source_file: SourceFile,
    ) -> ConvertResult:
        """执行一次转换，并隔离本次请求的 OCR 调用状态。"""

        warnings: list[str] = []

        # 客户端共享连接，状态通过 ContextVar 按请求隔离，避免并发 warning 串线。
        request_token = self._omlx_ocr_client.begin_request()
        try:
            markdown = self._markitdown_converter.convert(file_path)
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

    def convert_batch(
        self,
        upload_batch_id: str,
        object_storage: MinioBatchObjectStorage,
    ) -> BatchConvertResult:
        """从 MinIO 读取一个批次的 original 文件并逐个转换。"""

        objects = object_storage.list_original_objects(upload_batch_id)
        if not objects:
            raise ValueError("指定上传批次没有可转换的 original 文件")

        self._settings.temp_dir.mkdir(parents=True, exist_ok=True)
        converted_files: list[BatchConvertedFile] = []
        for index, original in enumerate(objects):
            suffix = Path(original.filename).suffix
            temp_path = self._settings.temp_dir / (
                f"{upload_batch_id}_{index}{suffix}"
            )
            try:
                object_storage.download(original.object_key, temp_path)
                result = self.convert(
                    temp_path,
                    SourceFile(
                        filename=original.filename,
                        content_type=original.content_type,
                        size_bytes=original.size_bytes,
                    ),
                )
                converted_object_key = object_storage.converted_object_key(
                    original.object_key
                )
                # MinIO 以对象前缀表示目录；首次上传时 converted 前缀会自动形成。
                object_storage.upload_markdown(converted_object_key, result.markdown)
                converted_files.append(
                    BatchConvertedFile(
                        original_object_key=original.object_key,
                        original_filename=original.filename,
                        converted_object_key=converted_object_key,
                        content_type=result.content_type,
                        warnings=result.warnings,
                    )
                )
            finally:
                temp_path.unlink(missing_ok=True)

        return BatchConvertResult(
            upload_batch_id=str(upload_batch_id),
            files=converted_files,
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
