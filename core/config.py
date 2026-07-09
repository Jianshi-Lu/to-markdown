import os
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    omlx_base_url: str
    omlx_api_key: str
    omlx_model: str
    temp_dir: Path
    max_upload_mb: int


@lru_cache
def get_settings() -> Settings:
    return Settings(
        omlx_base_url=os.getenv("OMLX_BASE_URL", "http://127.0.0.1:8000/v1"),
        omlx_api_key=os.getenv("OMLX_API_KEY", "20020228"),
        omlx_model=os.getenv("OMLX_MODEL", "unlimited-ocr-mxfp8-mlx"),
        temp_dir=Path(os.getenv("TEMP_DIR", tempfile.gettempdir())) / "to-markdown",
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "100")),
    )

