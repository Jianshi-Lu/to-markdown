"""读写资信文件批次中的 MinIO 对象。"""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import urlparse
from uuid import UUID


@dataclass(frozen=True)
class OriginalObject:
    """待转换的 MinIO 原始对象。"""

    object_key: str
    filename: str
    content_type: str | None
    size_bytes: int


class MinioBatchObjectStorage:
    """封装 MinIO SDK，管理批次原文件和转换结果。"""

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
            client = Minio(
                host,
                access_key=access_key,
                secret_key=secret_key,
                secure=parsed.scheme == "https",
            )
        self._client = client
        self._bucket = bucket

    def list_original_objects(self, upload_batch_id: str) -> list[OriginalObject]:
        """按对象 Key 排序返回指定批次的 original 文件。"""

        batch_id = _normalize_batch_id(upload_batch_id)
        prefix = f"{batch_id}/original/"
        objects: list[OriginalObject] = []
        for item in self._client.list_objects(
            self._bucket,
            prefix=prefix,
            recursive=True,
        ):
            object_key = item.object_name
            if not object_key or object_key.endswith("/"):
                continue
            if not object_key.startswith(prefix):
                continue
            filename = Path(object_key).name
            objects.append(
                OriginalObject(
                    object_key=object_key,
                    filename=filename,
                    content_type=getattr(item, "content_type", None),
                    size_bytes=item.size,
                )
            )
        return sorted(objects, key=lambda item: item.object_key)

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


def _normalize_batch_id(upload_batch_id: str) -> str:
    try:
        return str(UUID(upload_batch_id))
    except (AttributeError, ValueError, TypeError) as exc:
        raise ValueError("uploadBatchId 必须是合法 UUID") from exc
