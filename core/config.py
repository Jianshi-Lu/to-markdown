"""进程级运行配置。"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    """不可变的运行配置。"""

    omlx_base_url: str
    omlx_api_key: str
    omlx_model: str
    temp_dir: Path
    max_upload_mb: int


@lru_cache
def get_settings() -> Settings:
    """读取并缓存环境变量；重新读取前需调用 ``cache_clear()``。"""

    return Settings(
        omlx_base_url=os.getenv("OMLX_BASE_URL", "http://127.0.0.1:8000/v1"),
        omlx_api_key=os.getenv("OMLX_API_KEY", "20020228"),
        omlx_model=os.getenv("OMLX_MODEL", "unlimited-ocr-mxfp8-mlx"),
        temp_dir=Path(os.getenv("TEMP_DIR", PROJECT_ROOT / ".runtime" / "uploads")),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "100")),
    )
