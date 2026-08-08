"""嵌入图片按需 OCR：复用 markitdown-ocr 的视觉服务，但不替换内置转换器。"""

from __future__ import annotations

import io
import base64
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, BinaryIO

import pdfplumber
from bs4 import BeautifulSoup
from markitdown_ocr import LLMVisionOCRService

_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
    ".webp",
}
_OFFICE_MEDIA_PATTERN = re.compile(r"^(?:word|ppt|xl)/media/")
_IMAGE_TAG_RE = re.compile(r"(!\[[^\]]*\]\(([^)]+)\))")
_DOCX_RELATIONSHIP_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
_HTML_EXTENSIONS = {".html", ".htm"}
_CONTAINER_EXTENSIONS = {".epub", ".zip"}
_REMOTE_SCHEMES = ("http://", "https://")


def _is_image(name: str) -> bool:
    """按扩展名判断是否是需要 OCR 的位图。"""

    suffix = name.rsplit(".", 1)[-1].lower()
    return f".{suffix}" in _IMAGE_EXTENSIONS


class EmbeddedImageOcr:
    """从文档中提取嵌入位图，按需调用本地 unlimited-ocr 进行识别。

    与 markitdown-ocr 插件的区别：本组件不注册任何转换器，不影响
    MarkItDown 内置 PDF/Office 转换器执行；只有检测到嵌入图片时才发起
    OCR 请求，实现“模型按需调用”。
    """

    def __init__(
        self,
        omlx_client: Any,
        model: str,
        prompt: str,
    ) -> None:
        """创建复用的视觉 OCR 服务。"""

        self._service = LLMVisionOCRService(
            client=omlx_client,
            model=model,
            default_prompt=prompt,
        )

    def ocr_pdf_page(self, page_bytes: bytes) -> list[str]:
        """识别单页 PDF 中的全部嵌入位图，返回按图片顺序排列的 OCR 文本。"""

        results: list[str] = []
        try:
            with pdfplumber.open(io.BytesIO(page_bytes)) as pdf:
                page = pdf.pages[0]
                for image in page.images:
                    x0, y0, x1, y1 = (
                        image["x0"],
                        image["top"],
                        image["x1"],
                        image["bottom"],
                    )
                    if x1 <= x0 or y1 <= y0:
                        continue
                    try:
                        crop = page.within_bbox((x0, y0, x1, y1))
                        image_stream = io.BytesIO()
                        crop.to_image(resolution=150).original.save(
                            image_stream,
                            format="PNG",
                        )
                        image_stream.seek(0)
                        ocr = self._service.extract_text(image_stream)
                        if ocr.text.strip():
                            results.append(ocr.text.strip())
                    except Exception:
                        # 单个图片失败不影响整页转换，错误由调用状态记录。
                        continue
        except Exception:
            # 无法解析页面时静默跳过，内置转换结果仍然可用。
            return results
        return results

    def ocr_office_media(self, file_bytes: bytes) -> list[str]:
        """识别 DOCX/PPTX/XLSX（ZIP）中 word/ppt/xl/media 下的位图。"""

        results: list[str] = []
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                media_names = sorted(
                    name
                    for name in archive.namelist()
                    if _OFFICE_MEDIA_PATTERN.match(name)
                    and _is_image(name)
                )
                for name in media_names:
                    try:
                        image_stream = io.BytesIO(archive.read(name))
                        ocr = self._service.extract_text(image_stream)
                        if ocr.text.strip():
                            results.append(
                                f"*[Image OCR] ({name})\n"
                                f"{ocr.text.strip()}\n"
                                f"[End OCR]*"
                            )
                    except Exception:
                        continue
        except zipfile.BadZipFile:
            return results
        return results

    def insert_docx_ocr(self, markdown: str, file_bytes: bytes) -> str:
        """识别 DOCX 内嵌位图，并把 OCR 文本插到对应图片标签之后。

        MarkItDown 内置 DocxConverter 只会输出 `![](data:image/png;base64...)`
        之类的占位标签（markdownify 默认移除 data URI），不调用模型。这里按
        document.xml 中图片的实际出现顺序与 Markdown 图片标签一一配对，OCR
        结果以 `*[Image OCR] ... [End OCR]*` 紧跟图片标签插入；顺序对不上时
        回退为追加到文档末尾，保证内容不丢失。
        """

        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                media = [
                    (name, archive.read(name))
                    for name in archive.namelist()
                    if name.startswith("word/media/")
                    and _is_image(name)
                ]
        except zipfile.BadZipFile:
            return markdown
        if not media:
            return markdown

        ocr_by_name: dict[str, str] = {}
        for name, data in media:
            image_stream = io.BytesIO(data)
            try:
                ocr = self._service.extract_text(image_stream)
            except Exception:
                continue
            if ocr.text.strip():
                ocr_by_name[name] = (
                    f"*[Image OCR] ({name})\n"
                    f"{ocr.text.strip()}\n"
                    f"[End OCR]*"
                )
        if not ocr_by_name:
            return markdown

        image_order = self._docx_image_order(file_bytes)
        tags = list(_IMAGE_TAG_RE.finditer(markdown))
        if not image_order or len(image_order) != len(tags):
            leftover = list(ocr_by_name.values())
            if leftover:
                return markdown.rstrip() + "\n\n" + "\n\n".join(leftover)
            return markdown

        ordered_names = [image_order[i] for i in range(len(tags))]
        inserted_parts: list[str] = []
        cursor = 0
        for index, tag_match in enumerate(tags):
            inserted_parts.append(markdown[cursor : tag_match.start()])
            inserted_parts.append(tag_match.group(1))
            name = ordered_names[index]
            block = ocr_by_name.get(name)
            if block:
                inserted_parts.append(f"\n\n{block}")
            cursor = tag_match.end()
        inserted_parts.append(markdown[cursor:])
        return "".join(inserted_parts)

    def insert_image_ocr(
        self,
        markdown: str,
        file_bytes: bytes,
        extension: str,
    ) -> str:
        """把 HTML/EPUB/ZIP 中图片的 OCR 结果回填到对应 Markdown 图片标签。

        MarkItDown 对 HTML/EPUB 只输出图片标签（data URI 占位或相对路径），
        不调用模型。这里按源文档中的图片顺序提取位图，逐张 OCR，并把结果
        紧跟对应 `![](...)` 标签插入；顺序对不上时回退为末尾追加。
        """

        images = self._extract_container_images(file_bytes, extension)
        if not images:
            return markdown

        ocr_blocks = [
            f"*[Image OCR]\n{block}\n[End OCR]*"
            for block in (self._ocr_bytes(data) for data in images)
            if block
        ]
        if not ocr_blocks:
            return markdown

        tags = [
            match
            for match in _IMAGE_TAG_RE.finditer(markdown)
            if not match.group(2).startswith(_REMOTE_SCHEMES)
        ]
        if not tags:
            return markdown.rstrip() + "\n\n" + "\n\n".join(ocr_blocks)

        parts: list[str] = []
        cursor = 0
        used = 0
        for tag in tags:
            parts.append(markdown[cursor : tag.start()])
            parts.append(tag.group(1))
            if used < len(ocr_blocks):
                parts.append(f"\n\n{ocr_blocks[used]}")
                used += 1
            cursor = tag.end()
        parts.append(markdown[cursor:])
        result = "".join(parts)

        if used < len(ocr_blocks):
            result = result.rstrip() + "\n\n" + "\n\n".join(ocr_blocks[used:])
        return result

    def _extract_container_images(
        self,
        file_bytes: bytes,
        extension: str,
    ) -> list[bytes]:
        """按源文档顺序提取 HTML/EPUB/ZIP 中可 OCR 的位图。"""

        ext = extension.lower()
        if ext in _HTML_EXTENSIONS:
            return self._html_image_bytes(file_bytes)
        if ext == ".epub":
            return self._epub_image_bytes(file_bytes)
        if ext == ".zip":
            return self._zip_image_bytes(file_bytes)
        return []

    @staticmethod
    def _html_image_bytes(file_bytes: bytes) -> list[bytes]:
        """提取 HTML 中 data URI 图片（相对/远程路径无法从单文件解析）。"""

        images: list[bytes] = []
        try:
            soup = BeautifulSoup(file_bytes, "html.parser")
            for image in soup.find_all("img"):
                src = image.get("src") or ""
                if not src.startswith("data:"):
                    continue
                try:
                    payload = src.split(",", 1)[1]
                    images.append(base64.b64decode(payload))
                except Exception:
                    continue
        except Exception:
            return images
        return images

    @staticmethod
    def _epub_image_bytes(file_bytes: bytes) -> list[bytes]:
        """按 EPUB content.opf manifest 顺序提取图片。"""

        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                container = ET.fromstring(archive.read("META-INF/container.xml"))
                rootfile = container.find(
                    ".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"
                )
                if rootfile is None:
                    return []
                opf_path = rootfile.get("full-path") or ""
                opf = ET.fromstring(archive.read(opf_path))
                base_dir = posixpath.dirname(opf_path)
                images: list[bytes] = []
                for item in opf.iter():
                    if not item.tag.endswith("}item"):
                        continue
                    media_type = item.get("media-type") or ""
                    href = item.get("href") or ""
                    if not media_type.startswith("image/"):
                        continue
                    full_path = posixpath.normpath(
                        posixpath.join(base_dir, href)
                    )
                    try:
                        images.append(archive.read(full_path))
                    except KeyError:
                        continue
                if images:
                    return images
        except (KeyError, ET.ParseError, zipfile.BadZipFile):
            pass
        return []

    @staticmethod
    def _zip_image_bytes(file_bytes: bytes) -> list[bytes]:
        """按路径排序提取 ZIP 中的位图。"""

        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                names = sorted(
                    name
                    for name in archive.namelist()
                    if _is_image(name) and not name.endswith("/")
                )
                return [archive.read(name) for name in names]
        except zipfile.BadZipFile:
            return []

    def _ocr_bytes(self, data: bytes) -> str | None:
        """对单张位图执行 OCR，失败或空结果返回 None。"""

        try:
            ocr = self._service.extract_text(io.BytesIO(data))
        except Exception:
            return None
        return ocr.text.strip() or None

    @staticmethod
    def _docx_image_order(file_bytes: bytes) -> list[str]:
        """按 document.xml 中 blip 的 r:embed 顺序返回 word/media 图片名。"""

        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                document = ET.fromstring(archive.read("word/document.xml"))
                relationships = ET.fromstring(
                    archive.read("word/_rels/document.xml.rels")
                )
        except (KeyError, ET.ParseError, zipfile.BadZipFile):
            return []

        target_by_id = {
            rel.get("Id"): rel.get("Target") or ""
            for rel in relationships
        }
        order: list[str] = []
        for element in document.iter():
            if not element.tag.endswith("}blip"):
                continue
            embed = element.get(
                f"{{{_DOCX_RELATIONSHIP_NS}}}embed"
            )
            target = target_by_id.get(embed or "")
            if target and "media/" in target:
                order.append(f"word/{target.lstrip('/')}")
        return order
