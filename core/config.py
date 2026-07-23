"""进程级运行配置。"""

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


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
    temp_dir: Path
    max_upload_mb: int
    minio_endpoint: str = "http://10.0.0.100:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "credential-files"


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
    temp_dir=Path(os.getenv("TEMP_DIR", PROJECT_ROOT / ".runtime" / "uploads")),
    max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "100")),
    minio_endpoint=os.getenv("MINIO_ENDPOINT", "http://10.0.0.100:9000"),
    minio_access_key=os.getenv("MINIO_ACCESS_KEY", "jianshi"),
    minio_secret_key=os.getenv("MINIO_SECRET_KEY", "20020228"),
    minio_bucket=os.getenv("MINIO_BUCKET", "credential-files"),
)
