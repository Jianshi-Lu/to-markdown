"""Markdown 二次整理扩展点。"""

class MarkdownNormalizer:
    def normalize(self, markdown: str) -> tuple[str, bool, list[str]]:
        return markdown, False, [
            "normalize_markdown is reserved but not implemented in v1."
        ]
