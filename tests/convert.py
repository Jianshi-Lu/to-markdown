"""通过 HTTP 接口转换单个测试文件。"""

import mimetypes
import os
from pathlib import Path
import sys

import httpx


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "tests" / "test_files" / "output" / "converted"
OUTPUT_SUFFIX = "_converted"
CONVERT_URL = (
    os.getenv("TO_MARKDOWN_BASE_URL", "http://127.0.0.1:8081").rstrip("/")
    + "/convert"
)


def resolve_output_path(input_path: Path, output_argument: str | None) -> Path:
    if output_argument is None:
        output_dir = OUTPUT_DIR
        output_name = input_path.stem
    else:
        requested_path = Path(output_argument).expanduser()
        if requested_path.suffix.lower() == ".md":
            output_dir = requested_path.parent
            output_name = requested_path.stem
        else:
            output_dir = requested_path
            output_name = input_path.stem

    return output_dir / f"{output_name}{OUTPUT_SUFFIX}.md"


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit(
            "Usage: python tests/convert.py <input_file> [output_dir_or_md]"
        )

    input_path = Path(sys.argv[1]).expanduser().resolve()
    if not input_path.is_file():
        raise SystemExit(f"Input file does not exist: {input_path}")

    content_type = mimetypes.guess_type(input_path.name)[0] or "application/octet-stream"
    with input_path.open("rb") as input_file:
        # 转换入口
        response = httpx.post(
            CONVERT_URL,
            files={"file": (input_path.name, input_file, content_type)},
            timeout=None,
        )

    if not response.is_success:
        raise SystemExit(f"HTTP {response.status_code}: {response.text}")

    output_path = resolve_output_path(
        input_path,
        sys.argv[2] if len(sys.argv) == 3 else None,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(response.json()["markdown"], encoding="utf-8")
    print(f"Markdown written to: {output_path}")


if __name__ == "__main__":
    main()
