import os
import socket
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import httpx
from markitdown import MarkItDown
from openai import APIConnectionError, OpenAI


# 当前文件所在目录是 demo/，parents[1] 回到项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# oMLX 负责加载和管理模型权重，Python demo 不再直接 import mlx_vlm，也不再 load 本地权重。
# 这里写的是 oMLX 暴露的 OpenAI-compatible API 地址：
#   http://127.0.0.1:8000/v1/chat/completions
# OpenAI SDK 会自动把 base_url + /chat/completions 拼成完整请求地址。
OMLX_BASE_URL = os.getenv("OMLX_BASE_URL", "http://127.0.0.1:8000/v1")

# oMLX 本地服务通常只需要一个占位 API key；是否校验取决于你启动 oMLX 时的配置。
# 这里默认沿用你之前 curl 里使用过的 Bearer token，后续也可以通过环境变量覆盖。
OMLX_API_KEY = os.getenv("OMLX_API_KEY", "20020228")

# 这里的 model 名称必须和 oMLX 服务里注册/启动的模型名称一致。
# 如果 oMLX 后台显示的名字不同，改这里或者运行前设置 OMLX_MODEL 即可。
OMLX_MODEL = os.getenv("OMLX_MODEL", "unlimited-ocr-mxfp8-mlx")

# 当前 demo 改回 PNG，目的是确认 MarkItDown 的图片 converter 会把图片交给 oMLX OCR。
# 如果换成 DOCX，MarkItDown 主要走自己的 DOCX converter，通常不会触发 llm_client。
INPUT_FILE = PROJECT_ROOT / "test_files/input/test_img.png"
OUTPUT_FILE = PROJECT_ROOT / "test_files/output/test_img_omlx.md"


def bytes_to_unicode() -> dict[int, str]:
    # 有些 tokenizer 会把原始 byte 映射成一组“可显示”的 Unicode 字符。
    # 这样模型输出时不会直接出现不可见控制字符，但中文可能看起来像乱码，
    # 例如“什么”可能被显示成类似“ä»Ģä¹Ī”的 byte-level 表示。
    bytes_values = (
        list(range(ord("!"), ord("~") + 1))
        + list(range(ord("¡"), ord("¬") + 1))
        + list(range(ord("®"), ord("ÿ") + 1))
    )
    unicode_values = bytes_values[:]
    next_value = 0

    # GPT-2/byte-level BPE 风格的映射会保留常见可见字符，
    # 再把剩余 byte 映射到 256 之后的 Unicode code point。
    for byte in range(256):
        if byte not in bytes_values:
            bytes_values.append(byte)
            unicode_values.append(256 + next_value)
            next_value += 1

    return dict(zip(bytes_values, map(chr, unicode_values)))


# bytes_to_unicode() 返回 byte -> 可见字符。
# 这里反过来生成 可见字符 -> byte，用来把模型输出还原成原始 UTF-8 byte。
BYTE_DECODER = {value: key for key, value in bytes_to_unicode().items()}


def decode_tokenizer_bytes(text: str) -> str:
    # oMLX 只是承载模型推理，不一定会替我们修复模型/tokenizer 的 byte-level 输出。
    # 如果 response 里已经是正常中文，这个函数基本不会改变结果；
    # 如果 response 里出现“ä»Ģä¹Ī...”这类文本，就会按 byte 映射还原成 UTF-8 中文。
    decoded_bytes = bytearray()

    for char in text:
        byte = BYTE_DECODER.get(char)
        if byte is None:
            # 如果字符不属于 byte-level 映射，就按普通 UTF-8 字符保留下来。
            decoded_bytes.extend(char.encode("utf-8"))
        else:
            # 如果字符属于映射表，就先还原成它代表的原始 byte。
            decoded_bytes.append(byte)

    # 最后再按 UTF-8 解码，中文就会从“ä»Ģä¹Ī...”恢复成正常文本。
    return decoded_bytes.decode("utf-8", errors="replace")


def assert_omlx_reachable(base_url: str) -> None:
    # MarkItDown 会把底层 HTTP 错误包成 FileConversionException，
    # 直接看 traceback 不容易判断是不是 oMLX 没启动。
    # 所以在真正转换前先做一次 TCP 连接检查：只确认 host:port 是否可连。
    parsed_url = urlparse(base_url)
    host = parsed_url.hostname
    port = parsed_url.port

    if host is None:
        raise SystemExit(f"Invalid OMLX_BASE_URL: {base_url}")

    if port is None:
        port = 443 if parsed_url.scheme == "https" else 80

    try:
        with socket.create_connection((host, port), timeout=3):
            return
    except OSError as exc:
        raise SystemExit(
            "\n".join(
                [
                    "Cannot connect to oMLX service.",
                    f"OMLX_BASE_URL: {base_url}",
                    f"Checked TCP endpoint: {host}:{port}",
                    "",
                    "Please make sure oMLX is running and exposing an OpenAI-compatible endpoint.",
                    "Expected chat completions endpoint:",
                    f"  {base_url.rstrip('/')}/chat/completions",
                    "",
                    "If your oMLX server uses another port, run for example:",
                    "  OMLX_BASE_URL=http://127.0.0.1:YOUR_PORT/v1 "
                    "python demo/convert_file_to_markdown.py",
                    "",
                    f"Original socket error: {exc}",
                ]
            )
        ) from exc


class DecodingChatCompletions:
    # MarkItDown 的图片 converter 期望调用：
    # client.chat.completions.create(model=..., messages=...)
    #
    # OpenAI SDK 本身已经有这个接口，但这里再包一层，目的有两个：
    # 1. 请求实际转发给 oMLX，而不是 OpenAI 云端；
    # 2. 拿到 oMLX 返回内容后，统一做一次 tokenizer byte 输出修复。
    def __init__(self, completions, base_url: str):
        self._completions = completions
        self._base_url = base_url

    def create(self, *args, **kwargs) -> SimpleNamespace:
        try:
            response = self._completions.create(*args, **kwargs)
        except APIConnectionError as exc:
            # 到这里说明 TCP 端口可连，但真正 POST /chat/completions 时连接失败。
            # 常见原因：
            # 1. oMLX 进程接到请求后崩溃或主动断开连接；
            # 2. oMLX 的 OpenAI-compatible 接口不支持 MarkItDown 传入的 image_url data URI；
            # 3. API path、模型名或鉴权配置和 oMLX 实际服务不一致。
            raise RuntimeError(
                "\n".join(
                    [
                        "oMLX chat completions request failed.",
                        f"Endpoint: {self._base_url.rstrip('/')}/chat/completions",
                        f"Model: {kwargs.get('model')}",
                        f"Messages summary: {summarize_messages(kwargs.get('messages', []))}",
                        "",
                        "TCP connection succeeded, but the HTTP request failed.",
                        "Please check the oMLX server log for the real server-side error.",
                        f"Original OpenAI SDK error: {exc}",
                    ]
                )
            ) from exc

        choices = []

        for choice in response.choices:
            content = choice.message.content or ""
            decoded_content = decode_tokenizer_bytes(content)

            # MarkItDown 只读取 response.choices[0].message.content。
            # 这里返回最小结构即可，避免依赖 OpenAI SDK response 对象是否允许原地修改。
            message = SimpleNamespace(content=decoded_content)
            choices.append(SimpleNamespace(message=message))

        return SimpleNamespace(choices=choices)


def summarize_messages(messages: list[dict]) -> str:
    # 排错时不要把整张图片的 base64 打到控制台，只输出结构和 data URI 大小。
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
    # 这是给 MarkItDown 使用的最小 OpenAI-compatible client。
    # 真实 HTTP 请求由 OpenAI SDK 发给 oMLX：
    #   POST {OMLX_BASE_URL}/chat/completions
    # 所以模型权重、内存占用、Metal/MLX 调度都发生在 oMLX 进程里，
    # 当前 Python 进程只负责把文件交给 MarkItDown，并把 OCR 结果写成 Markdown。
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


assert_omlx_reachable(OMLX_BASE_URL)
client = OmlxClient(base_url=OMLX_BASE_URL, api_key=OMLX_API_KEY)

# 这里把 oMLX 的 OpenAI-compatible API 接给 MarkItDown。
# 对 PNG/JPG 图片，MarkItDown 会构造 OpenAI chat completions 风格的 messages，
# 其中图片通常会被转成 data:image/...;base64,... 放在 image_url 里。
md = MarkItDown(
    llm_client=client,
    llm_model=OMLX_MODEL,
    # 这里不要手写 <image>。
    # MarkItDown 会把图片放到 OpenAI vision 格式的 image_url 字段里；
    # oMLX 收到 image_url 后会自己插入 image token。
    # 如果 prompt 里再写 <image>，服务端会看到 2 个 image token 但只有 1 张图片。
    llm_prompt="Free OCR.",
)
result = md.convert(str(INPUT_FILE))

# result.markdown 是 MarkItDown 的统一输出字段。
# 它更偏“结构/内容提取”，不保证一定生成排版很漂亮的 Markdown。
markdown = result.markdown

# 写文件前先创建父目录，避免 output 目录不存在时报错。
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE.write_text(markdown, encoding="utf-8")

print(markdown)
print(f"Wrote {OUTPUT_FILE}")
