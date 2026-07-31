"""历史 MinIO 对象存储适配器。

当前正式服务只接收调用方上传的文件流并返回 Markdown，不再导入本模块。文件
读取、目标路径生成和 Markdown 持久化均由调用方负责。
"""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import urlparse


@dataclass(frozen=True)
class OriginalObject:
    """待转换的 MinIO 原始对象。"""

    object_key: str
    filename: str
    content_type: str | None
    size_bytes: int


class MinioObjectStorage:
    """封装 MinIO SDK，管理单个原始文件和转换结果。"""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        client=None,
    ) -> None:
        if client is None:
            # 延迟导入，使单文件转换和纯业务单元测试不依赖 MinIO SDK。
            from minio import Minio

            parsed = urlparse(
                endpoint if "://" in endpoint else f"//{endpoint}"
            )
            if not parsed.hostname:
                raise ValueError("MINIO_ENDPOINT 必须包含主机地址")
            host = parsed.hostname
            if parsed.port:
                host = f"{host}:{parsed.port}"
            # 创建MinIO实例
            client = Minio(
                host,
                access_key=access_key,
                secret_key=secret_key,
                secure=parsed.scheme == "https",
            )
        self._client = client
        self._bucket = bucket

    def get_original_object(self, object_key: str) -> OriginalObject:
        """读取单个 original 对象的元数据。"""

        normalized_key = _normalize_original_object_key(object_key)
        item = self._client.stat_object(self._bucket, normalized_key)
        return OriginalObject(
            object_key=normalized_key,
            filename=Path(normalized_key).name,
            content_type=getattr(item, "content_type", None),
            size_bytes=item.size,
        )

    def download(self, object_key: str, destination: Path) -> None:
        """将指定原始对象流式下载到临时磁盘。"""

        response = self._client.get_object(
            self._bucket,
            object_key,
        )
        try:
            with destination.open("wb") as output:
                for chunk in response.stream(1024 * 1024):
                    output.write(chunk)
        finally:
            response.close()
            response.release_conn()

    def converted_object_key(self, original_object_key: str) -> str:
        """将 original 对象映射到同批次同层级的 converted Markdown 对象。"""

        marker = "/original/"
        if marker not in original_object_key:
            raise ValueError("原始对象 Key 必须位于 original/ 路径下")

        batch_prefix, relative_key = original_object_key.split(marker, 1)
        markdown_path = PurePosixPath(relative_key).with_suffix(".md")
        return f"{batch_prefix}/converted/{markdown_path.as_posix()}"

    def upload_markdown(self, object_key: str, markdown: str) -> None:
        """将 Markdown 写入 MinIO；converted 前缀不存在时会随对象自动形成。"""

        payload = markdown.encode("utf-8")
        self._client.put_object(
            self._bucket,
            object_key,
            BytesIO(payload),
            length=len(payload),
            content_type="text/markdown; charset=utf-8",
        )


def _normalize_original_object_key(object_key: str) -> str:
    if object_key is None or not object_key.strip():
        raise ValueError("originalObjectKey 不能为空")

    normalized = object_key.replace("\\", "/").strip("/")
    if "/original/" not in f"/{normalized}/":
        raise ValueError("原始对象 Key 必须位于 original/ 路径下")
    if normalized.endswith("/"):
        raise ValueError("原始对象 Key 不能是目录")
    if any(segment in {"", ".", ".."} for segment in normalized.split("/")):
        raise ValueError("原始对象 Key 不合法")
    return normalized
