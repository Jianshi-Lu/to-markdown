"""进程级运行配置。"""

from dataclasses import dataclass, field
from functools import lru_cache
import os
from pathlib import Path


def _load_local_environment() -> None:
    """读取与本配置模块同目录的 .env，不覆盖进程或 IDE 已设置的变量。"""

    env_file = Path(__file__).with_name(".env")
    if not env_file.is_file():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if name:
            os.environ.setdefault(name, value)


_load_local_environment()


@dataclass(frozen=True, slots=True)
class Settings:
    """不可变的运行配置。"""

    omlx_base_url: str
    omlx_api_key: str = field(repr=False)
    omlx_model: str
    omlx_ocr_prompt: str
    omlx_ocr_max_tokens: int
    omlx_ocr_temperature: float
    omlx_ocr_repetition_penalty: float
    max_upload_mb: int
    on_demand_ocr_enabled: bool = True
    omlx_image_ocr_max_tokens: int = 768
    omlx_image_ocr_prompt: str = "document parsing."


@dataclass(frozen=True, slots=True)
class HttpServerSettings:
    """承载 to-markdown HTTP Server 的监听配置。"""

    host: str = "127.0.0.1"
    port: int = 8081
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_conversion_settings() -> Settings:
    """返回进程内复用的转换配置实例。"""

    return Settings(
        omlx_base_url=os.getenv("OMLX_BASE_URL", "http://127.0.0.1:8000/v1"),
        # 本地无鉴权兼容服务可使用占位值；真实凭据只能由环境变量注入。
        omlx_api_key=os.getenv("OMLX_API_KEY", "local"),
        omlx_model=os.getenv("OMLX_MODEL", "unlimited-ocr-mxfp8-mlx"),
        # unlimited-ocr 的模型模板要求使用固定短提示词，禁止被外部长提示词覆盖。
        omlx_ocr_prompt="document parsing.",
        # 结构化输出 token 消耗远高于纯文本 OCR，官方默认 32768，当前先提到 16384。
        omlx_ocr_max_tokens=int(os.getenv("OMLX_OCR_MAX_TOKENS", "16384")),
        omlx_ocr_temperature=float(os.getenv("OMLX_OCR_TEMPERATURE", "0")),
        omlx_ocr_repetition_penalty=float(
            os.getenv("OMLX_OCR_REPETITION_PENALTY", "1.1")
        ),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "100")),
        on_demand_ocr_enabled=os.getenv("ON_DEMAND_OCR_ENABLED", "1") == "1",
        omlx_image_ocr_max_tokens=int(
            os.getenv("OMLX_IMAGE_OCR_MAX_TOKENS", "768")
        ),
        omlx_image_ocr_prompt="document parsing.",
    )


@lru_cache(maxsize=1)
def get_http_server_settings() -> HttpServerSettings:
    """返回进程内复用的 HTTP Server 配置实例。"""

    return HttpServerSettings(
        host=os.environ.get("SERVER_HOST", "127.0.0.1"),
        port=int(os.environ.get("SERVER_PORT", "8081")),
        log_level=os.environ.get("SERVER_LOG_LEVEL", "INFO").upper(),
    )


__all__ = [
    "HttpServerSettings",
    "Settings",
    "get_conversion_settings",
    "get_http_server_settings",
]
