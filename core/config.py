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


SETTINGS = Settings(
    omlx_base_url=os.getenv("OMLX_BASE_URL", "http://127.0.0.1:8000/v1"),
    omlx_api_key=os.getenv("OMLX_API_KEY", "20020228"),
    omlx_model=os.getenv("OMLX_MODEL", "unlimited-ocr-mxfp8-mlx"),
    omlx_ocr_prompt=os.getenv("OMLX_OCR_PROMPT", "Free OCR."),
    omlx_ocr_max_tokens=int(os.getenv("OMLX_OCR_MAX_TOKENS", "4096")),
    omlx_ocr_temperature=float(os.getenv("OMLX_OCR_TEMPERATURE", "0")),
    omlx_ocr_repetition_penalty=float(
        os.getenv("OMLX_OCR_REPETITION_PENALTY", "1.1")
    ),
    max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "100")),
)
