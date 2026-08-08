"""通过 HTTP 接口批量转换测试文件。"""

import mimetypes
import os
from pathlib import Path
import shutil

import httpx


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "tests" / "test_files" / "input"
OUTPUT_DIR = PROJECT_ROOT / "tests" / "test_files" / "output"
CONVERT_URL = (
    os.getenv("TO_MARKDOWN_BASE_URL", "http://127.0.0.1:8081").rstrip("/")
    + "/convert"
)


def is_test_file(path: Path) -> bool:
    """忽略 Finder 等工具生成的隐藏文件。"""

    return path.is_file() and not any(part.startswith(".") for part in path.parts)


def output_path_for(input_path: Path) -> Path:
    relative_path = input_path.relative_to(INPUT_DIR)
    return OUTPUT_DIR / relative_path.with_name(f"{relative_path.name}_converted.md")


def clear_output_dir() -> None:
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    OUTPUT_DIR.mkdir(parents=True)


def convert_file(input_path: Path) -> Path:
    content_type = mimetypes.guess_type(input_path.name)[0] or "application/octet-stream"

    try:
        with input_path.open("rb") as input_file:
            response = httpx.post(
                CONVERT_URL,
                files={"file": (input_path.name, input_file, content_type)},
                timeout=None,
            )
    except httpx.RequestError as exc:
        raise RuntimeError(f"Request failed for {input_path}: {exc}") from exc

    if not response.is_success:
        raise RuntimeError(
            f"Conversion failed for {input_path}: HTTP {response.status_code}: "
            f"{response.text}"
        )

    output_path = output_path_for(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)
    return output_path


def main() -> None:
    clear_output_dir()

    input_files = sorted(path for path in INPUT_DIR.rglob("*") if is_test_file(path))
    if not input_files:
        raise SystemExit(f"No test files found in: {INPUT_DIR}")

    for index, input_path in enumerate(input_files, start=1):
        try:
            output_path = convert_file(input_path)
        except (OSError, RuntimeError) as exc:
            raise SystemExit(str(exc)) from exc

        print(f"[{index}/{len(input_files)}] {input_path} -> {output_path}")

    print(f"Converted {len(input_files)} file(s).")


if __name__ == "__main__":
    main()
