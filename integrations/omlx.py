"""oMLX client 与 OCR 输出解码适配。"""

import socket
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
        ocr_call_state: "OmlxOcrCallState",
        max_tokens: int,
        temperature: float,
        repetition_penalty: float,
    ):
        self._openai_completions = openai_completions
        self._omlx_base_url = omlx_base_url
        self._ocr_call_state = ocr_call_state
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._repetition_penalty = repetition_penalty

    def create(self, *args, **kwargs) -> SimpleNamespace:
        self._ocr_call_state.request_count += 1
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
            self._ocr_call_state.add_error(message)
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
            self._ocr_call_state.add_error(message)
            raise

        choices = []
        for choice in response.choices:
            content = choice.message.content or ""
            decoded_content = decode_tokenizer_bytes(content)
            finish_reason = getattr(choice, "finish_reason", None)

            if has_degenerate_character_run(decoded_content):
                self._ocr_call_state.add_error(
                    "oMLX returned degenerate OCR output with a repeated character; "
                    "the OCR text was discarded."
                )
                decoded_content = ""
            elif finish_reason == "length":
                self._ocr_call_state.add_error(
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
    """提供给 MarkItDown 的 OpenAI-compatible client。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        max_tokens: int,
        temperature: float,
        repetition_penalty: float,
    ):
        self.call_state = OmlxOcrCallState()
        openai_http_client = httpx.Client(trust_env=False)
        openai_api_client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            http_client=openai_http_client,
            max_retries=0,
        )
        self.chat = SimpleNamespace(
            completions=OmlxChatCompletions(
                openai_api_client.chat.completions,
                omlx_base_url=base_url,
                ocr_call_state=self.call_state,
                max_tokens=max_tokens,
                temperature=temperature,
                repetition_penalty=repetition_penalty,
            )
        )
