"""MarkItDown 转换集成。"""

import io
from pathlib import Path
from typing import Any, BinaryIO

from markitdown import MarkItDown, StreamInfo

from core.errors import ConversionError


class MarkItDownConverter:
    """封装 MarkItDown 的参数、结果和异常。"""

    def __init__(
        self,
        llm_client: Any | None = None,
        llm_model: str | None = None,
        llm_prompt: str | None = None,
    ):
        kwargs: dict[str, Any] = {"enable_plugins": True}
        if llm_client is not None:
            kwargs["llm_client"] = llm_client
        if llm_model is not None:
            kwargs["llm_model"] = llm_model
        if llm_prompt is not None:
            kwargs["llm_prompt"] = llm_prompt

        self._markitdown = MarkItDown(**kwargs)

    def convert(
        self,
        file_stream: BinaryIO,
        *,
        filename: str,
        content_type: str | None,
    ) -> str:
        """根据文件流和请求元信息执行格式识别与 Markdown 转换。"""

        buffered_stream: BinaryIO
        should_detach = False
        if isinstance(file_stream, io.BufferedIOBase):
            buffered_stream = file_stream
        else:
            # FastAPI 的 UploadFile 默认使用 SpooledTemporaryFile。该对象虽然
            # 提供完整的二进制读取接口，但不继承 BufferedIOBase；MarkItDown
            # 内部的 Magika 会因此拒绝它。包装为 BufferedReader 既满足类型
            # 契约，也避免为了适配第三方库把整个上传文件复制到内存。
            buffered_stream = io.BufferedReader(file_stream)
            should_detach = True

        try:
            result = self._markitdown.convert_stream(
                buffered_stream,
                stream_info=StreamInfo(
                    mimetype=content_type,
                    extension=Path(filename).suffix or None,
                    filename=filename,
                ),
            )
        except Exception as exc:
            raise ConversionError(f"MarkItDown conversion failed: {exc}") from exc
        finally:
            if should_detach:
                # 文件流由 FastAPI/上层调用方持有，适配层不能提前关闭它。
                buffered_stream.detach()

        return result.markdown
