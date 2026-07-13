"""MarkItDown 转换集成。"""

from pathlib import Path
from typing import Any

from markitdown import MarkItDown

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

    def convert(self, file_path: Path) -> str:
        try:
            result = self._markitdown.convert(str(file_path))
        except Exception as exc:
            raise ConversionError(f"MarkItDown conversion failed: {exc}") from exc

        return result.markdown
