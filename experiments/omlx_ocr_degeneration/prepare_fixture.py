"""复制已确认会触发退化的图片，建立独立实验输入。"""

from pathlib import Path
import shutil


EXPERIMENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXPERIMENT_DIR.parents[1]
SOURCE = PROJECT_ROOT / "tests" / "test_files" / "input" / "test_image.png"
TARGET = EXPERIMENT_DIR / "input" / "degeneration_trigger.png"


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"Source fixture does not exist: {SOURCE}")

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE, TARGET)
    print(f"Fixture copied to: {TARGET}")


if __name__ == "__main__":
    main()
