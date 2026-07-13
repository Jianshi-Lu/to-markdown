"""oMLX client 与 OCR 输出解码适配。"""

from __future__ import annotations

import socket
from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from types import SimpleNamespace
from urllib.parse import urlparse

import httpx
from openai import APIConnectionError, OpenAI

from core.errors import OmlxUnavailableError


DEGENERATE_RUN_LENGTH = 32


def bytes_to_unicode() -> dict[int, str]:
    """构造 GPT-2 byte-level tokenizer 的 byte 到 Unicode 映射。"""

    bytes_values = (
        list(range(ord("!"), ord("~") + 1))
        + list(range(ord("¡"), ord("¬") + 1))
        + list(range(ord("®"), ord("ÿ") + 1))
    )
    unicode_values = bytes_values[:]
    next_value = 0

    for byte in range(256):
        if byte not in bytes_values:
            bytes_values.append(byte)
            unicode_values.append(256 + next_value)
            next_value += 1

    return dict(zip(bytes_values, map(chr, unicode_values)))


BYTE_DECODER = {value: key for key, value in bytes_to_unicode().items()}


def decode_tokenizer_bytes(text: str) -> str:
    """恢复 byte-level tokenizer 文本，无效 UTF-8 字节使用替换字符。"""

    decoded_bytes = bytearray()

    for char in text:
        byte = BYTE_DECODER.get(char)
        if byte is None:
            decoded_bytes.extend(char.encode("utf-8"))
        else:
            decoded_bytes.append(byte)

    return decoded_bytes.decode("utf-8", errors="replace")


def assert_omlx_reachable(base_url: str) -> None:
    """检查 oMLX TCP 端点；不验证鉴权、模型或推理能力。"""

    parsed_url = urlparse(base_url)
    host = parsed_url.hostname
    port = parsed_url.port

    if host is None:
        raise OmlxUnavailableError(f"Invalid OMLX_BASE_URL: {base_url}")

    if port is None:
        port = 443 if parsed_url.scheme == "https" else 80

    try:
        with socket.create_connection((host, port), timeout=3):
            return
    except OSError as exc:
        raise OmlxUnavailableError(
            "\n".join(
                [
                    "Cannot connect to oMLX service.",
                    f"OMLX_BASE_URL: {base_url}",
                    f"Checked TCP endpoint: {host}:{port}",
                ]
            )
        ) from exc


class OmlxChatCompletions:
    """MarkItDown 所需的最小 ``chat.completions`` 兼容层。"""

    def __init__(
        self,
        openai_completions,
        omlx_base_url: str,
        ocr_call_state: "OmlxOcrCallState" | None = None,
        max_tokens: int = 4096,
        temperature: float = 0,
        repetition_penalty: float = 1.1,
        call_state_provider: Callable[[], "OmlxOcrCallState"] | None = None,
    ):
        """保存共享 completions 连接，并接收请求状态提供器。"""

        self._openai_completions = openai_completions
        self._omlx_base_url = omlx_base_url
        if call_state_provider is None:
            if ocr_call_state is None:
                raise ValueError("ocr_call_state or call_state_provider is required")
            call_state_provider = lambda: ocr_call_state
        self._call_state_provider = call_state_provider
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._repetition_penalty = repetition_penalty

    def create(self, *args, **kwargs) -> SimpleNamespace:
        """转发一次 OCR 请求，并把结果和 warning 写入当前请求状态。"""

        call_state = self._call_state_provider()
        call_state.request_count += 1
        kwargs.setdefault("max_tokens", self._max_tokens)
        kwargs.setdefault("temperature", self._temperature)
        extra_body = dict(kwargs.get("extra_body") or {})
        extra_body.setdefault("repetition_penalty", self._repetition_penalty)
        kwargs["extra_body"] = extra_body

        try:
            response = self._openai_completions.create(*args, **kwargs)
        except APIConnectionError as exc:
            message = "\n".join(
                [
                    "oMLX chat completions request failed.",
                    f"Endpoint: {self._omlx_base_url.rstrip('/')}/chat/completions",
                    f"Model: {kwargs.get('model')}",
                    f"Messages summary: {summarize_messages(kwargs.get('messages', []))}",
                    "The oMLX request could not be completed.",
                ]
            )
            call_state.add_error(message)
            raise OmlxUnavailableError(message) from exc
        except Exception as exc:
            message = "\n".join(
                [
                    "oMLX chat completions request failed.",
                    f"Endpoint: {self._omlx_base_url.rstrip('/')}/chat/completions",
                    f"Model: {kwargs.get('model')}",
                    f"Error: {type(exc).__name__}: {exc}",
                ]
            )
            call_state.add_error(message)
            raise

        choices = []
        for choice in response.choices:
            content = choice.message.content or ""
            decoded_content = decode_tokenizer_bytes(content)
            finish_reason = getattr(choice, "finish_reason", None)

            if has_degenerate_character_run(decoded_content):
                call_state.add_error(
                    "oMLX returned degenerate OCR output with a repeated character; "
                    "the OCR text was discarded."
                )
                decoded_content = ""
            elif finish_reason == "length":
                call_state.add_error(
                    f"oMLX OCR reached the {kwargs['max_tokens']}-token output limit; "
                    "the returned text may be incomplete."
                )

            message = SimpleNamespace(content=decoded_content)
            choices.append(
                SimpleNamespace(message=message, finish_reason=finish_reason)
            )

        return SimpleNamespace(choices=choices)


def summarize_messages(messages: list[dict]) -> str:
    """生成消息摘要，仅记录图片 data URI 长度。"""

    parts = []

    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            parts.append(f"text({len(content)} chars)")
            continue

        for item in content:
            item_type = item.get("type")
            if item_type == "text":
                parts.append(f"text({len(item.get('text', ''))} chars)")
            elif item_type == "image_url":
                image_url = item.get("image_url", {}).get("url", "")
                parts.append(f"image_url({len(image_url)} chars)")
            else:
                parts.append(str(item_type))

    return ", ".join(parts)


def has_degenerate_character_run(text: str) -> bool:
    """识别模型陷入单字符循环的明显退化输出。"""

    previous = None
    run_length = 0

    for char in text:
        if char == previous:
            run_length += 1
        else:
            previous = char
            run_length = 1

        if run_length >= DEGENERATE_RUN_LENGTH:
            return True

    return False


@dataclass
class OmlxOcrCallState:
    """记录一次转换期间实际发生的 oMLX 调用。"""

    request_count: int = 0
    errors: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        if message not in self.errors:
            self.errors.append(message)


class OmlxOcrClient:
    """提供给 MarkItDown 的可复用 OpenAI-compatible client。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        max_tokens: int,
        temperature: float,
        repetition_penalty: float,
    ):
        """创建可复用的 OpenAI-compatible client，不在此处发起网络请求。"""

        # ContextVar 让共享的 completions 连接拥有请求级状态。
        self._call_state: ContextVar[OmlxOcrCallState | None] = ContextVar(
            "omlx_ocr_call_state",
            default=None,
        )
        self._openai_http_client = httpx.Client(trust_env=False)
        self._openai_api_client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            http_client=self._openai_http_client,
            max_retries=0,
        )
        self.chat = SimpleNamespace(
            completions=OmlxChatCompletions(
                self._openai_api_client.chat.completions,
                omlx_base_url=base_url,
                call_state_provider=self._get_call_state,
                max_tokens=max_tokens,
                temperature=temperature,
                repetition_penalty=repetition_penalty,
            )
        )

    def begin_request(self) -> Token:
        """为一次转换建立隔离的 OCR 调用状态。"""

        return self._call_state.set(OmlxOcrCallState())

    def end_request(self, token: Token) -> OmlxOcrCallState:
        """读取并清理当前转换的 OCR 调用状态。"""

        state = self._get_call_state()
        self._call_state.reset(token)
        return state

    def _get_call_state(self) -> OmlxOcrCallState:
        """读取当前请求状态；未进入转换上下文时创建兜底状态。"""

        state = self._call_state.get()
        if state is None:
            state = OmlxOcrCallState()
            self._call_state.set(state)
        return state

    def close(self) -> None:
        """释放 OpenAI SDK 和底层 HTTP client。"""

        # 只在应用 shutdown 时调用；请求处理期间不要关闭共享连接。
        self._openai_api_client.close()
