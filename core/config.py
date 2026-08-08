"""进程级运行配置。"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """不可变的运行配置。"""

    omlx_base_url: str
    omlx_api_key: str
    omlx_model: str
    omlx_ocr_prompt: str
    omlx_ocr_max_tokens: int
    omlx_ocr_temperature: float
    omlx_ocr_repetition_penalty: float
    max_upload_mb: int
    on_demand_ocr_enabled: bool = True
    omlx_image_ocr_max_tokens: int = 768
    omlx_image_ocr_prompt: str = "document parsing."


SETTINGS = Settings(
    omlx_base_url=os.getenv("OMLX_BASE_URL", "http://127.0.0.1:8000/v1"),
    omlx_api_key=os.getenv("OMLX_API_KEY", "20020228"),
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
