"""上传文件的临时存储。"""

from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import UploadFile

from core.config import Settings
from core.errors import UploadTooLargeError


@dataclass(frozen=True)
class TempUploadedFile:
    path: Path
    size_bytes: int

    def cleanup(self) -> None:
        self.path.unlink(missing_ok=True)


async def save_upload_file(upload_file: UploadFile, settings: Settings) -> TempUploadedFile:
    """分块保存上传文件，并限制最大体积。"""

    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload_file.filename or "").suffix
    max_bytes = settings.max_upload_mb * 1024 * 1024
    written = 0

    with NamedTemporaryFile(
        delete=False,
        suffix=suffix,
        dir=settings.temp_dir,
    ) as tmp:
        path = Path(tmp.name)
        while chunk := await upload_file.read(1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                path.unlink(missing_ok=True)
                raise UploadTooLargeError(
                    f"Uploaded file is larger than {settings.max_upload_mb} MB."
                )
            tmp.write(chunk)

    return TempUploadedFile(path=path, size_bytes=written)
