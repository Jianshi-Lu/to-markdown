"""直接调用 oMLX，对比 OCR 重复退化与稳定生成。"""

import argparse
import base64
from collections import Counter
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil
import time

import httpx
from openai import OpenAI


EXPERIMENT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = EXPERIMENT_DIR / "input" / "degeneration_trigger.png"
DEFAULT_OUTPUT = EXPERIMENT_DIR / "output"


def bytes_to_unicode() -> dict[int, str]:
    byte_values = (
        list(range(ord("!"), ord("~") + 1))
        + list(range(ord("¡"), ord("¬") + 1))
        + list(range(ord("®"), ord("ÿ") + 1))
    )
    unicode_values = byte_values[:]
    next_value = 0

    for byte in range(256):
        if byte not in byte_values:
            byte_values.append(byte)
            unicode_values.append(256 + next_value)
            next_value += 1

    return dict(zip(byte_values, map(chr, unicode_values)))


BYTE_DECODER = {value: key for key, value in bytes_to_unicode().items()}


def decode_tokenizer_bytes(text: str) -> str:
    decoded_bytes = bytearray()
    for char in text:
        byte = BYTE_DECODER.get(char)
        if byte is None:
            decoded_bytes.extend(char.encode("utf-8"))
        else:
            decoded_bytes.append(byte)
    return decoded_bytes.decode("utf-8", errors="replace")


def longest_character_run(text: str) -> tuple[str, int]:
    longest_char = ""
    longest_length = 0
    previous = ""
    current_length = 0

    for char in text:
        if char == previous:
            current_length += 1
        else:
            previous = char
            current_length = 1

        if current_length > longest_length:
            longest_char = char
            longest_length = current_length

    return longest_char, longest_length


@dataclass(frozen=True)
class Case:
    name: str
    prompt: str
    repetition_penalty: float
    max_tokens: int


def clear_output_dir(output_dir: Path) -> None:
    """清除上一次实验生成的结果，并重新创建输出目录。"""
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)


def run_case(
    client: OpenAI,
    case: Case,
    input_path: Path,
    output_dir: Path,
    model: str,
) -> dict:
    image_base64 = base64.b64encode(input_path.read_bytes()).decode("ascii")
    data_uri = f"data:image/png;base64,{image_base64}"
    started_at = time.perf_counter()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": case.prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ],
        temperature=0,
        max_tokens=case.max_tokens,
        extra_body={"repetition_penalty": case.repetition_penalty},
    )
    elapsed_seconds = time.perf_counter() - started_at

    choice = response.choices[0]
    raw_text = choice.message.content or ""
    decoded_text = decode_tokenizer_bytes(raw_text)
    repeated_char, repeated_length = longest_character_run(decoded_text)
    common_characters = Counter(decoded_text).most_common(5)

    (output_dir / f"{case.name}.raw.txt").write_text(raw_text, encoding="utf-8")
    (output_dir / f"{case.name}.decoded.txt").write_text(
        decoded_text,
        encoding="utf-8",
    )

    summary = {
        "case": asdict(case),
        "model": model,
        "prompt": case.prompt,
        "temperature": 0,
        "finish_reason": choice.finish_reason,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "raw_character_count": len(raw_text),
        "decoded_character_count": len(decoded_text),
        "longest_character_run": {
            "character": repeated_char,
            "length": repeated_length,
        },
        "most_common_characters": common_characters,
        "degeneration_detected": repeated_length >= 32,
    }
    (output_dir / f"{case.name}.summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reproduce Unlimited-OCR repeated-token degeneration via oMLX.",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--base-url",
        default=os.getenv("OMLX_BASE_URL", "http://127.0.0.1:8000/v1"),
    )
    parser.add_argument("--api-key", default=os.getenv("OMLX_API_KEY", "20020228"))
    parser.add_argument(
        "--model",
        default=os.getenv("OMLX_MODEL", "unlimited-ocr-mxfp8-mlx"),
    )
    parser.add_argument("--prompt", default="Free OCR.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    input_path = args.input.expanduser().resolve()
    output_dir = args.output.expanduser().resolve()
    if not input_path.is_file():
        raise SystemExit(
            f"Input fixture does not exist: {input_path}\n"
            "Run: python prepare_fixture.py"
        )

    clear_output_dir(output_dir)
    client = OpenAI(
        base_url=args.base_url,
        api_key=args.api_key,
        http_client=httpx.Client(trust_env=False),
        max_retries=0,
    )

    cases = (
        Case(
            name="baseline_reproduced",
            prompt=args.prompt,
            repetition_penalty=1.0,
            max_tokens=256,
        ),
        Case(
            name="prompt_control",
            prompt="document parsing.",
            repetition_penalty=1.0,
            max_tokens=1024,
        ),
        Case(
            name="fixed_comparison",
            prompt=args.prompt,
            repetition_penalty=1.1,
            max_tokens=1024,
        ),
    )
    summaries = [
        run_case(
            client=client,
            case=case,
            input_path=input_path,
            output_dir=output_dir,
            model=args.model,
        )
        for case in cases
    ]

    (output_dir / "comparison.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for summary in summaries:
        run = summary["longest_character_run"]
        print(
            f"{summary['case']['name']}: "
            f"finish={summary['finish_reason']}, "
            f"elapsed={summary['elapsed_seconds']}s, "
            f"longest_run={run['character']!r} x {run['length']}, "
            f"degeneration={summary['degeneration_detected']}"
        )
    print(f"Artifacts written to: {output_dir}")


if __name__ == "__main__":
    main()
