"""OCR 输出中 Markdown 协议标记的轻量清理。"""

import re


class OcrMarkdownCleaner:
    _OCR_BLOCK = re.compile(
        r"\*?\[Image OCR\]\s*(.*?)\s*\[End OCR\]\*?",
        re.DOTALL,
    )
    _DETECTION = re.compile(
        r"<\|det\|>\s*(title|text|image)\s*\[[^\]\r\n]*\]\s*<\|/det\|>",
        re.IGNORECASE,
    )
    _LEADING_MODEL_ARTIFACT = re.compile(
        r"(?m)^[ \t]*筆[ \t]*\r?\n(?=<\|det\|>)",
    )

    def clean(self, markdown: str) -> tuple[str, bool, list[str]]:
        normalized, block_count = self._OCR_BLOCK.subn(
            self._normalize_ocr_block,
            markdown,
        )
        normalized, artifact_count = self._LEADING_MODEL_ARTIFACT.subn("", normalized)
        normalized, detection_count = self._DETECTION.subn(
            self._replace_detection,
            normalized,
        )
        if detection_count:
            normalized = re.sub(r"\n{3,}", "\n\n", normalized)

        changed = (block_count + artifact_count + detection_count) > 0
        return normalized, changed and normalized != markdown, []

    @staticmethod
    def _replace_detection(match: re.Match[str]) -> str:
        if match.group(1).lower() == "title":
            return "# "
        return ""

    def _normalize_ocr_block(self, match: re.Match[str]) -> str:
        content = match.group(1).strip()
        detections = list(self._DETECTION.finditer(content))
        if not detections:
            return content

        parts: list[str] = []
        leading_text = content[: detections[0].start()].strip()
        if leading_text and leading_text != "筆":
            parts.append(leading_text)

        for index, detection in enumerate(detections):
            value_start = detection.end()
            value_end = (
                detections[index + 1].start()
                if index + 1 < len(detections)
                else len(content)
            )
            value = content[value_start:value_end].strip()
            if not value:
                continue

            detection_type = detection.group(1).lower()
            if detection_type == "title":
                parts.append(f"# {value}")
            else:
                parts.append(value)

        return "\n\n".join(parts)
