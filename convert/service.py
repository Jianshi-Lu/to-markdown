"""文件转换业务服务。"""

import io
from pathlib import Path
from typing import BinaryIO

import pypdfium2 as pdfium

from integrations.embedded_image_ocr import EmbeddedImageOcr
from integrations.markitdown import MarkItDownConverter
from integrations.omlx import OmlxOcrClient
from convert.types import ConvertResult, SourceFile
from configuration.config import Settings


class ConvertService:
    """复用转换运行时并编排输入文件流到 Markdown 的同步转换。"""

    def __init__(
        self,
        settings: Settings,
        markitdown_converter: MarkItDownConverter | None = None,
        omlx_ocr_client: OmlxOcrClient | None = None,
        embedded_image_ocr: EmbeddedImageOcr | None = None,
    ):
        """装配一次转换运行时；可注入依赖用于测试。"""

        self._settings = settings
        # 正式服务只在 lifespan 中构造一次，后续请求复用同一组第三方客户端。
        if omlx_ocr_client is None:
            omlx_ocr_client = self._build_omlx_client()
        if markitdown_converter is None:
            markitdown_converter = MarkItDownConverter(
                llm_client=omlx_ocr_client,
                llm_model=self._settings.omlx_model,
                llm_prompt=self._settings.omlx_ocr_prompt,
            )
        self._markitdown_converter = markitdown_converter
        self._omlx_ocr_client = omlx_ocr_client
        self._embedded_image_ocr = embedded_image_ocr or EmbeddedImageOcr(
            omlx_client=omlx_ocr_client,
            model=settings.omlx_model,
            prompt=settings.omlx_image_ocr_prompt,
        )

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
            file_stream.seek(0)
            file_bytes = file_stream.read()
            markdown = self._convert_data(file_bytes, source_file)
        finally:
            ocr_call_state = self._omlx_ocr_client.end_request(request_token)
        warnings.extend(ocr_call_state.errors)

        return ConvertResult(
            markdown=markdown,
            source_filename=source_file.filename,
            content_type=source_file.content_type,
            warnings=warnings,
            warning_codes=getattr(ocr_call_state, "warning_codes", []),
        )

    def _convert_data(self, file_bytes: bytes, source_file: SourceFile) -> str:
        """按文件类型选择内置转换或内置转换 + 嵌入图片按需 OCR。"""

        extension = Path(source_file.filename).suffix.lower()
        if extension == ".pdf":
            return self._convert_pdf(file_bytes, source_file)

        markdown = self._markitdown_converter.convert(
            io.BytesIO(file_bytes),
            filename=source_file.filename,
            content_type=source_file.content_type,
        )
        if self._settings.on_demand_ocr_enabled:
            if extension == ".docx":
                return self._embedded_image_ocr.insert_docx_ocr(
                    markdown,
                    file_bytes,
                )
            if extension in {".html", ".htm", ".epub", ".zip"}:
                return self._embedded_image_ocr.insert_image_ocr(
                    markdown,
                    file_bytes,
                    extension,
                )
            if extension == ".xlsx":
                ocr_blocks = self._embedded_image_ocr.ocr_office_media(file_bytes)
                if ocr_blocks:
                    markdown = markdown.rstrip() + "\n\n" + "\n\n".join(ocr_blocks)
        # PPTX 内嵌图片由 MarkItDown 内置 PptxConverter 在配置 llm_client 时
        # 通过 llm_caption 内联描述，这里不再重复 OCR；其它格式直接透传。
        return markdown

    def _convert_pdf(self, file_bytes: bytes, source_file: SourceFile) -> str:
        """PDF 转换：无嵌入位图单遍转换，有位图才逐页 + 按需 OCR。

        无位图 PDF 直接整篇调用内置 PdfConverter，避免每页重复拆解和类型识别；
        含位图 PDF 才逐页转换，保证 OCR 结果能稳定归属到对应页面。
        """

        if not self._pdf_has_embedded_images(file_bytes):
            return self._markitdown_converter.convert(
                io.BytesIO(file_bytes),
                filename=source_file.filename,
                content_type="application/pdf",
            )

        page_chunks: list[str] = []
        stem = Path(source_file.filename).stem or "document"
        for page_number, page_bytes in enumerate(
            self._split_pdf_pages(file_bytes),
            start=1,
        ):
            page_markdown = self._markitdown_converter.convert(
                io.BytesIO(page_bytes),
                filename=f"{stem}-page{page_number}.pdf",
                content_type="application/pdf",
            )
            if self._settings.on_demand_ocr_enabled:
                for ocr_text in self._embedded_image_ocr.ocr_pdf_page(
                    page_bytes
                ):
                    page_markdown = (
                        page_markdown.rstrip()
                        + f"\n\n*[Image OCR]\n{ocr_text}\n[End OCR]*"
                    )
            page_chunks.append(
                f"## Page {page_number}\n\n{page_markdown.strip()}"
            )
        return "\n\n".join(page_chunks)

    @staticmethod
    def _pdf_has_embedded_images(file_bytes: bytes) -> bool:
        """快速扫描 PDF 是否包含任何嵌入位图。"""

        try:
            import pdfplumber

            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                return any(page.images for page in pdf.pages)
        except Exception:
            # 无法解析时按含位图处理，走逐页路径保证转换可用。
            return True

    @staticmethod
    def _split_pdf_pages(file_bytes: bytes) -> list[bytes]:
        """用 pypdfium2 把 PDF 拆成独立的单页内存流。"""

        source = pdfium.PdfDocument(file_bytes)
        try:
            page_count = len(source)
            pages: list[bytes] = []
            for page_index in range(page_count):
                single = pdfium.PdfDocument.new()
                try:
                    single.import_pages(source, pages=[page_index])
                    buffer = io.BytesIO()
                    single.save(buffer)
                    pages.append(buffer.getvalue())
                finally:
                    single.close()
            return pages
        finally:
            source.close()

    def _build_omlx_client(self) -> OmlxOcrClient:
        """创建应用级复用的 oMLX 运行时。"""

        return OmlxOcrClient(
            base_url=self._settings.omlx_base_url,
            api_key=self._settings.omlx_api_key,
            max_tokens=self._settings.omlx_ocr_max_tokens,
            image_max_tokens=self._settings.omlx_image_ocr_max_tokens,
            temperature=self._settings.omlx_ocr_temperature,
            repetition_penalty=self._settings.omlx_ocr_repetition_penalty,
        )
