"""oMLX client 与 OCR 输出解码适配。"""

import socket
from types import SimpleNamespace
from urllib.parse import urlparse

import httpx
from openai import APIConnectionError, OpenAI

from core.errors import OmlxUnavailableError


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


class DecodingChatCompletions:
    """MarkItDown 所需的最小 ``chat.completions`` 兼容层。"""

    def __init__(self, completions, base_url: str):
        self._completions = completions
        self._base_url = base_url

    def create(self, *args, **kwargs) -> SimpleNamespace:
        try:
            response = self._completions.create(*args, **kwargs)
        except APIConnectionError as exc:
            raise OmlxUnavailableError(
                "\n".join(
                    [
                        "oMLX chat completions request failed.",
                        f"Endpoint: {self._base_url.rstrip('/')}/chat/completions",
                        f"Model: {kwargs.get('model')}",
                        f"Messages summary: {summarize_messages(kwargs.get('messages', []))}",
                        "TCP connection succeeded, but the HTTP request failed.",
                    ]
                )
            ) from exc

        choices = []
        for choice in response.choices:
            content = choice.message.content or ""
            message = SimpleNamespace(content=decode_tokenizer_bytes(content))
            choices.append(SimpleNamespace(message=message))

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


class OmlxClient:
    """提供给 MarkItDown 的 OpenAI-compatible client。"""

    def __init__(self, base_url: str, api_key: str):
        http_client = httpx.Client(trust_env=False)
        openai_client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            http_client=http_client,
            max_retries=0,
        )
        self.chat = SimpleNamespace(
            completions=DecodingChatCompletions(
                openai_client.chat.completions,
                base_url=base_url,
            )
        )
